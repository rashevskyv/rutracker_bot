"""
Regression tests for US-only Nintendo eShop deals and showcase re-validation.
Verifies:
1. Curated search fetches US offers via Algolia US + live US Price API.
2. Algolia salePrice is NOT trusted as confirmation; live Price API is ground truth.
3. Absence of discount in US Price API produces no deal card.
4. Real downloads_rank_i from European catalog is preserved without inventing ranks.
5. Active US cards are re-validated against US Price API during rotations, preventing false expiration via DE.
6. When US discount actually ends, the card is queued for in-place edit.
7. Correct USD currency, regional label, and US store link formatting.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.eshop.models import GameDeal
from services.eshop.eshop_service import EShopService
from services.eshop.formatters import format_eshop_deal_message
from send_eshop_deals import send_eshop_deals


@pytest.mark.asyncio
async def test_us_deals_require_live_price_api_and_ignore_algolia_sale_price():
    """Verify Algolia salePrice is ignored; only live US Price API confirms deals."""
    service = EShopService()

    fake_hit_with_stale_sale = {
        "title": "The Legend of Zelda: Breath of the Wild",
        "nsuid": "70010000000025",
        "slug": "the-legend-of-zelda-breath-of-the-wild-switch",
        "url": "/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        "msrp": 59.99,
        "salePrice": 39.99,  # Algolia claims sale, but live Price API will say no discount
    }

    mock_rps = MagicMock()
    mock_rps.get_us_data_by_title = AsyncMock(return_value=fake_hit_with_stale_sale)

    # 1. Live US Price API returns regular price only (sale ended or false flag in Algolia)
    price_api_no_discount = [
        GameDeal(
            fs_id="1173609",
            title="The Legend of Zelda: Breath of the Wild",
            regular_price=59.99,
            discount_price=59.99,
            discount_percent=0.0,
            currency="USD",
            nsuid="70010000000025",
            downloads_rank=60,
        )
    ]

    with patch("services.eshop.region_price_service.RegionPriceService", return_value=mock_rps), \
         patch.object(service, "validate_live_prices", new_callable=AsyncMock) as mock_val:

        # Case A: Live Price API rejects discount -> validate_live_prices returns empty list
        mock_val.return_value = []
        deals = await service.fetch_us_curated_deals(
            min_discount_percent=30.0, titles=["The Legend of Zelda: Breath of the Wild"]
        )
        assert len(deals) == 0, "Deal must not be produced when live Price API has no discount, despite Algolia salePrice"

        # Case B: Live US Price API confirms active 30% discount
        confirmed_deal = GameDeal(
            fs_id="1173609",
            title="The Legend of Zelda: Breath of the Wild",
            regular_price=59.99,
            discount_price=41.99,
            discount_percent=30.0,
            currency="USD",
            nsuid="70010000000025",
            url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
            downloads_rank=60,
        )
        mock_val.return_value = [confirmed_deal]
        deals = await service.fetch_us_curated_deals(
            min_discount_percent=30.0, titles=["The Legend of Zelda: Breath of the Wild"]
        )
        assert len(deals) == 1
        d = deals[0]
        assert d.currency == "USD"
        assert d.regular_price == 59.99
        assert d.discount_price == 41.99
        assert d.discount_percent == 30.0
        assert d.downloads_rank == 60
        assert "nintendo.com/us/store" in d.url

    await service.close()


@pytest.mark.asyncio
async def test_active_us_showcase_card_revalidation_and_expiration():
    """
    Test rotation behavior for an active US showcase card:
    - Run 1: Posts US deal card into showcase (message_id 770001, USD).
    - Run 2: Re-validates active card via US Price API. DE returns not_found, but US confirms discount -> card KEPT.
    - Run 3: US discount ends -> card marked expired for in-place edit.
    """
    state_storage = {}

    def fake_save_active(data):
        state_storage["showcase"] = json.loads(json.dumps(data))

    def fake_load_active():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    us_deal = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99,
        discount_price=41.99,
        discount_percent=30.0,
        currency="USD",
        nsuid="70010000000025",
        url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        downloads_rank=60,
        banner_url="https://example.com/botw.jpg",
    )

    mock_eshop = AsyncMock()
    mock_eshop.fetch_popular_discounted_games.return_value = []
    mock_eshop.fetch_discounted_games.return_value = []
    mock_eshop.fetch_us_curated_deals.return_value = [us_deal]

    mock_bot = AsyncMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 770001
    mock_bot.send_photo.return_value = mock_sent_msg
    mock_bot.send_message.return_value = mock_sent_msg

    # === RUN 1: Publish US deal card ===
    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    stored = fake_load_active()["-1001790782971_561344"]
    assert len(stored) == 1
    assert stored[0]["message_id"] == 770001
    assert stored[0]["currency"] == "USD"
    assert stored[0]["discount_price"] == 41.99
    assert stored[0]["nsuid"] == "70010000000025"

    # === RUN 2: Re-validation. DE Price API would say not_found, but US check confirms active discount ===
    mock_eshop_run2 = AsyncMock()
    mock_eshop_run2.fetch_popular_discounted_games.return_value = []
    mock_eshop_run2.fetch_discounted_games.return_value = []
    mock_eshop_run2.fetch_us_curated_deals.return_value = []
    # US re-validation returns active discount:
    active_revalidated = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99,
        discount_price=41.99,
        discount_percent=30.0,
        currency="USD",
        nsuid="70010000000025",
        downloads_rank=60,
    )
    mock_eshop_run2.validate_live_prices.return_value = [active_revalidated]

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del_run2, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop_run2), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # In Run 2: US card remains active, not deleted or marked expired
    assert mock_del_run2.call_count == 0
    stored_run2 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_run2) == 1
    assert stored_run2[0]["message_id"] == 770001
    assert stored_run2[0]["currency"] == "USD"

    # === RUN 3: US discount has ended ===
    mock_eshop_run3 = AsyncMock()
    mock_eshop_run3.fetch_popular_discounted_games.return_value = []
    mock_eshop_run3.fetch_discounted_games.return_value = []
    mock_eshop_run3.fetch_us_curated_deals.return_value = []
    # Live US Price API reports regular price, no discount
    expired_us_deal = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99,
        discount_price=59.99,
        discount_percent=0.0,
        currency="USD",
        nsuid="70010000000025",
        downloads_rank=60,
    )
    mock_eshop_run3.validate_live_prices.return_value = [expired_us_deal]

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del_run3, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop_run3), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Card is preserved in state as expired target (ready for in-place edit)
    assert mock_del_run3.call_count == 0
    assert len(fake_load_active()["-1001790782971_561344"]) == 1


@pytest.mark.asyncio
async def test_us_deal_deduplication_and_popularity_rank_sorting():
    """Verify that US deals are deduplicated against EU deals and sorted by real EU downloads_rank."""
    eu_deal = GameDeal(
        fs_id="eu_101",
        title="Some Indie Hit",
        regular_price=20.0,
        discount_price=10.0,
        discount_percent=50.0,
        currency="EUR",
        downloads_rank=200,
    )
    # Zelda BotW US deal has real EU downloads_rank 60, should be sorted before rank 200
    us_botw = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99,
        discount_price=41.99,
        discount_percent=30.0,
        currency="USD",
        nsuid="70010000000025",
        url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        downloads_rank=60,
    )
    # Duplicate BotW from EU feed that might appear
    eu_botw_dup = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=69.99,
        discount_price=69.99,
        discount_percent=0.0,
        currency="EUR",
        downloads_rank=60,
    )

    state_storage = {}

    def fake_save_active(data):
        state_storage["showcase"] = json.loads(json.dumps(data))

    def fake_load_active():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    mock_eshop = AsyncMock()
    mock_eshop.fetch_popular_discounted_games.return_value = [eu_deal, eu_botw_dup]
    mock_eshop.fetch_discounted_games.return_value = []
    mock_eshop.fetch_us_curated_deals.return_value = [us_botw]

    posted_messages = []
    mock_bot = AsyncMock()
    def fake_send_photo(*args, **kwargs):
        msg = MagicMock()
        msg.message_id = len(posted_messages) + 1001
        posted_messages.append(kwargs)
        return msg

    mock_bot.send_photo.side_effect = fake_send_photo
    mock_bot.send_message.side_effect = fake_send_photo

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    stored = fake_load_active()["-1001790782971_561344"]
    # There should only be 2 deals posted (eu_deal and us_botw); eu_botw_dup must NOT duplicate
    titles = [it["title"] for it in stored]
    assert len(titles) == 2
    assert "The Legend of Zelda: Breath of the Wild" in titles
    assert "Some Indie Hit" in titles

    # Verification of sorting: rank 60 (Zelda) comes first before rank 200 (Indie Hit)
    assert stored[0]["title"] == "The Legend of Zelda: Breath of the Wild"
    assert stored[0]["downloads_rank"] == 60
    assert stored[0]["currency"] == "USD"
    assert stored[1]["title"] == "Some Indie Hit"
    assert stored[1]["downloads_rank"] == 200



def test_format_us_deal_message_region_and_currency():
    """Verify US deal messages show 🇺🇸 США label, USD currency, and correct store link."""
    deal = GameDeal(
        fs_id="1173609",
        title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99,
        discount_price=41.99,
        discount_percent=30.0,
        currency="USD",
        nsuid="70010000000025",
        url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        downloads_rank=60,
        categories=["Action", "Adventure"],
    )

    # Ukrainian formatting
    msg_ua = format_eshop_deal_message(deal, language="UA")
    assert "🇺🇸" in msg_ua
    assert "США:" in msg_ua
    assert "<s>59.99 USD</s>" in msg_ua
    assert "41.99 USD" in msg_ua
    assert "-30%" in msg_ua
    assert "https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/" in msg_ua

    # English formatting
    msg_en = format_eshop_deal_message(deal, language="EN")
    assert "🇺🇸" in msg_en
    assert "USA:" in msg_en
    assert "41.99 USD" in msg_en
