"""
Regression tests for US-only Nintendo eShop deals and showcase re-validation.
Verifies:
1. Strict exact title matching for Nintendo first-party base games (rejects DLC/Expansion Pass).
2. Curated search fetches US offers via Algolia US + live US Price API.
3. Algolia salePrice is NOT trusted as confirmation; live Price API is ground truth.
4. Active US and Nintendo cards are re-validated against US Price API during rotations.
5. In-place price edit for Nintendo deals preserves direct eShop URL; preserved on edit failure.
6. Empty/missing live API response does NOT delete Nintendo cards.
7. Safe deletion of expired Nintendo cards and notification list update without deleted card.
"""

import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.eshop.models import GameDeal
from services.eshop.eshop_service import EShopService
from services.eshop.formatters import format_eshop_deal_message
from send_eshop_deals import send_eshop_deals, is_nintendo_first_party


@contextlib.contextmanager
def patch_send_env(fake_load, fake_save, eshop, bot, mock_del=None):
    """Reusable context manager reducing test patch boilerplate."""
    patches = [
        patch("send_eshop_deals.load_active_showcase", side_effect=fake_load),
        patch("send_eshop_deals.save_active_showcase", side_effect=fake_save),
        patch("send_eshop_deals.load_posted_deals", return_value={}),
        patch("send_eshop_deals.save_posted_deals"),
        patch("send_eshop_deals.EShopService", return_value=eshop),
        patch("send_eshop_deals.bot", bot),
        patch("send_eshop_deals.save_last_run"),
        patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None),
        patch("send_eshop_deals.RegionPriceService.get_us_data_by_title", new_callable=AsyncMock, return_value=None),
    ]
    if mock_del is not None:
        patches.append(patch("send_eshop_deals.safe_delete_showcase_message", mock_del))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


def test_is_nintendo_first_party_exact_matching():
    """Verify strict exact normalized matching against curated Nintendo first-party base titles."""
    assert is_nintendo_first_party("Super Mario Odyssey") is True
    assert is_nintendo_first_party("The Legend of Zelda: Breath of the Wild") is True
    assert is_nintendo_first_party("Super Smash Bros. Ultimate") is True
    assert is_nintendo_first_party("Super Mario Odyssey™") is True

    # Non-base packages, DLCs, and expansion passes must NOT be classified as Nintendo first-party
    assert is_nintendo_first_party("Super Mario Odyssey DLC") is False
    assert is_nintendo_first_party("The Legend of Zelda: Breath of the Wild Expansion Pass") is False
    assert is_nintendo_first_party("Super Mario Odyssey: Starter Pack") is False
    assert is_nintendo_first_party("Breath of the Wild DLC Pack 1") is False
    assert is_nintendo_first_party("Random Indie Game") is False
    assert is_nintendo_first_party("") is False
    assert is_nintendo_first_party(None) is False


@pytest.mark.asyncio
async def test_us_deals_require_live_price_api_and_ignore_algolia_sale_price():
    """Verify Algolia salePrice is ignored; only live US Price API confirms deals."""
    service = EShopService()
    fake_hit = {
        "title": "The Legend of Zelda: Breath of the Wild",
        "nsuid": "70010000000025",
        "slug": "the-legend-of-zelda-breath-of-the-wild-switch",
        "url": "/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        "msrp": 59.99,
        "salePrice": 39.99,
    }
    mock_rps = MagicMock()
    mock_rps.get_us_data_by_title = AsyncMock(return_value=fake_hit)

    with patch("services.eshop.region_price_service.RegionPriceService", return_value=mock_rps), \
         patch.object(service, "validate_live_prices", new_callable=AsyncMock) as mock_val:

        mock_val.return_value = []
        deals = await service.fetch_us_curated_deals(
            min_discount_percent=30.0, titles=["The Legend of Zelda: Breath of the Wild"]
        )
        assert len(deals) == 0, "Deal must not be produced when live Price API has no discount"

        confirmed_deal = GameDeal(
            fs_id="1173609", title="The Legend of Zelda: Breath of the Wild",
            regular_price=59.99, discount_price=41.99, discount_percent=30.0,
            currency="USD", nsuid="70010000000025", downloads_rank=60,
            url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
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
        assert "nintendo.com/us/store" in d.url

    await service.close()


@pytest.mark.asyncio
async def test_active_us_showcase_card_revalidation_and_expiration():
    """Test rotation behavior for an active US showcase card across 3 cycles."""
    state_storage = {}
    def fake_save_active(data):
        state_storage["showcase"] = json.loads(json.dumps(data))
    def fake_load_active():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    us_deal = GameDeal(
        fs_id="1173609", title="Shin Megami Tensei V: Vengeance",
        regular_price=59.99, discount_price=41.99, discount_percent=30.0,
        currency="USD", nsuid="70010000000025", downloads_rank=60,
        url="https://www.nintendo.com/us/store/products/shin-megami-tensei-v-vengeance-switch/",
        banner_url="https://example.com/smtv.jpg",
    )

    mock_eshop = AsyncMock()
    mock_eshop.fetch_popular_discounted_games.return_value = []
    mock_eshop.fetch_discounted_games.return_value = []
    mock_eshop.fetch_us_curated_deals.return_value = [us_deal]

    mock_bot = AsyncMock()
    mock_sent_msg = MagicMock(message_id=770001)
    mock_bot.send_photo.return_value = mock_sent_msg
    mock_bot.send_message.return_value = mock_sent_msg

    # === RUN 1: Publish US deal card ===
    with patch_send_env(fake_load_active, fake_save_active, mock_eshop, mock_bot):
        await send_eshop_deals(force=True, reset=False)

    stored = fake_load_active()["-1001790782971_561344"]
    assert len(stored) == 1
    assert stored[0]["message_id"] == 770001
    assert stored[0]["currency"] == "USD"
    assert stored[0]["discount_price"] == 41.99

    # === RUN 2: Re-validation confirms active discount -> card KEPT ===
    mock_eshop_run2 = AsyncMock()
    mock_eshop_run2.fetch_popular_discounted_games.return_value = []
    mock_eshop_run2.fetch_discounted_games.return_value = []
    mock_eshop_run2.fetch_us_curated_deals.return_value = []
    active_revalidated = GameDeal(
        fs_id="1173609", title="Shin Megami Tensei V: Vengeance",
        regular_price=59.99, discount_price=41.99, discount_percent=30.0,
        currency="USD", nsuid="70010000000025", downloads_rank=60,
    )
    mock_eshop_run2.validate_live_prices.return_value = [active_revalidated]
    mock_del_run2 = AsyncMock(return_value=True)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_run2, mock_bot, mock_del_run2):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del_run2.call_count == 0
    stored_run2 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_run2) == 1
    assert stored_run2[0]["message_id"] == 770001

    # === RUN 3: US discount has ended -> queued for in-place edit ===
    mock_eshop_run3 = AsyncMock()
    mock_eshop_run3.fetch_popular_discounted_games.return_value = []
    mock_eshop_run3.fetch_discounted_games.return_value = []
    mock_eshop_run3.fetch_us_curated_deals.return_value = []
    expired_us_deal = GameDeal(
        fs_id="1173609", title="Shin Megami Tensei V: Vengeance",
        regular_price=59.99, discount_price=59.99, discount_percent=0.0,
        currency="USD", nsuid="70010000000025", downloads_rank=60,
    )
    mock_eshop_run3.validate_live_prices.return_value = [expired_us_deal]
    mock_del_run3 = AsyncMock(return_value=True)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_run3, mock_bot, mock_del_run3):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del_run3.call_count == 0
    assert len(fake_load_active()["-1001790782971_561344"]) == 1


@pytest.mark.asyncio
async def test_us_deal_deduplication_and_popularity_rank_sorting():
    """Verify that US deals are deduplicated against EU deals and sorted by real EU downloads_rank."""
    eu_deal = GameDeal(
        fs_id="eu_101", title="Some Indie Hit",
        regular_price=20.0, discount_price=10.0, discount_percent=50.0,
        currency="EUR", downloads_rank=200,
    )
    us_botw = GameDeal(
        fs_id="1173609", title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99, discount_price=41.99, discount_percent=30.0,
        currency="USD", nsuid="70010000000025", downloads_rank=60,
        url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
    )
    eu_botw_dup = GameDeal(
        fs_id="1173609", title="The Legend of Zelda: Breath of the Wild",
        regular_price=69.99, discount_price=69.99, discount_percent=0.0,
        currency="EUR", downloads_rank=60,
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
    def fake_send(*args, **kwargs):
        msg = MagicMock(message_id=len(posted_messages) + 1001)
        posted_messages.append(kwargs)
        return msg

    mock_bot.send_photo.side_effect = fake_send
    mock_bot.send_message.side_effect = fake_send

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop, mock_bot):
        await send_eshop_deals(force=True, reset=False)

    stored = fake_load_active()["-1001790782971_561344"]
    titles = [it["title"] for it in stored]
    assert len(titles) == 2
    assert "The Legend of Zelda: Breath of the Wild" in titles
    assert "Some Indie Hit" in titles
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

    msg_ua = format_eshop_deal_message(deal, language="UA")
    assert "🇺🇸" in msg_ua
    assert "США:" in msg_ua
    assert "<s>59.99 USD</s>" in msg_ua
    assert "41.99 USD" in msg_ua
    assert "-30%" in msg_ua
    assert "https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/" in msg_ua

    msg_en = format_eshop_deal_message(deal, language="EN")
    assert "🇺🇸" in msg_en
    assert "USA:" in msg_en
    assert "41.99 USD" in msg_en


@pytest.mark.asyncio
async def test_nintendo_first_party_out_of_order_lifecycle():
    """Comprehensive test for Nintendo first-party deals out-of-order lifecycle."""
    state_storage = {}
    def fake_save_active(data):
        state_storage["showcase"] = json.loads(json.dumps(data))
    def fake_load_active():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    # Prepare 30 initial regular cards
    initial_regular_cards = [
        {
            "fs_id": f"reg_{i}", "title": f"Regular Hit {i}",
            "message_id": 1000 + i, "discount_percent": 40.0,
            "discount_price": 12.0, "regular_price": 20.0,
            "currency": "EUR", "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    fake_save_active({"-1001790782971_561344": initial_regular_cards})

    botw_deal = GameDeal(
        fs_id="1173609", title="The Legend of Zelda: Breath of the Wild",
        regular_price=59.99, discount_price=41.99, discount_percent=30.0,
        currency="USD", nsuid="70010000000025", downloads_rank=60,
        url="https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/",
        banner_url="https://example.com/botw.jpg",
    )
    mario_deal = GameDeal(
        fs_id="1173610", title="Super Mario Odyssey",
        regular_price=59.99, discount_price=39.99, discount_percent=33.0,
        currency="USD", nsuid="70010000000001", downloads_rank=50,
        url="https://www.nintendo.com/us/store/products/super-mario-odyssey-switch/",
        banner_url="https://example.com/odyssey.jpg",
    )

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("reg_", ""))
        return GameDeal(
            fs_id=fs_id, title=f"Regular Hit {idx}", regular_price=20.0,
            discount_price=12.0, discount_percent=40.0, currency="EUR", downloads_rank=idx * 10,
        )

    mock_bot = AsyncMock()
    next_msg_id = 5000
    def fake_send(*args, **kwargs):
        nonlocal next_msg_id
        next_msg_id += 1
        return MagicMock(message_id=next_msg_id)
    mock_bot.send_photo.side_effect = fake_send
    mock_bot.send_message.side_effect = fake_send

    # === CYCLE 1: Initial run with 30 regular cards + 2 Nintendo deals ===
    mock_eshop_c1 = AsyncMock()
    mock_eshop_c1.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop_c1.fetch_popular_discounted_games.return_value = []
    mock_eshop_c1.fetch_discounted_games.return_value = []
    mock_eshop_c1.fetch_us_curated_deals.return_value = [botw_deal, mario_deal]
    mock_del_c1 = AsyncMock(return_value=True)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_c1, mock_bot, mock_del_c1):
        await send_eshop_deals(force=True, reset=False)

    stored_c1 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_c1) == 32
    assert len([it for it in stored_c1 if not it.get("is_nintendo")]) == 30
    assert len([it for it in stored_c1 if it.get("is_nintendo")]) == 2
    assert mock_del_c1.call_count == 0

    # === CYCLE 2: Repeat run (no duplicates) ===
    send_photo_count_before_c2 = mock_bot.send_photo.call_count
    mock_eshop_c2 = AsyncMock()
    mock_eshop_c2.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop_c2.fetch_popular_discounted_games.return_value = []
    mock_eshop_c2.fetch_discounted_games.return_value = []
    mock_eshop_c2.fetch_us_curated_deals.return_value = [botw_deal, mario_deal]

    async def mock_validate_c2(deals, country="DE", require_discount=True):
        res = []
        for d in deals:
            if "Zelda" in d.title or str(d.nsuid) == "70010000000025":
                res.append(botw_deal)
            elif "Mario" in d.title or str(d.nsuid) == "70010000000001":
                res.append(mario_deal)
            else:
                res.append(d)
        return res
    mock_eshop_c2.validate_live_prices.side_effect = mock_validate_c2
    mock_del_c2 = AsyncMock(return_value=True)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_c2, mock_bot, mock_del_c2):
        await send_eshop_deals(force=True, reset=False)

    stored_c2 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_c2) == 32
    assert mock_bot.send_photo.call_count == send_photo_count_before_c2
    assert mock_del_c2.call_count == 0

    # === CYCLE 3: Zelda BotW discount ends -> safely deleted; Mario still active ===
    mock_eshop_c3 = AsyncMock()
    mock_eshop_c3.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop_c3.fetch_popular_discounted_games.return_value = []
    mock_eshop_c3.fetch_discounted_games.return_value = []
    mock_eshop_c3.fetch_us_curated_deals.return_value = []

    async def mock_validate_c3(deals, country="DE", require_discount=True):
        res = []
        for d in deals:
            if "Zelda" in d.title:
                res.append(GameDeal(
                    fs_id=d.fs_id, title=d.title, regular_price=59.99,
                    discount_price=59.99, discount_percent=0.0, currency="USD", nsuid=d.nsuid
                ))
            elif "Mario" in d.title:
                res.append(mario_deal)
        return res
    mock_eshop_c3.validate_live_prices.side_effect = mock_validate_c3
    mock_del_c3 = AsyncMock(return_value=True)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_c3, mock_bot, mock_del_c3):
        await send_eshop_deals(force=True, reset=False)

    stored_c3 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_c3) == 31
    assert len([it for it in stored_c3 if not it.get("is_nintendo")]) == 30
    assert len([it for it in stored_c3 if it.get("is_nintendo")]) == 1
    assert stored_c3[-1]["title"] == "Super Mario Odyssey"
    assert mock_del_c3.call_count == 1

    # === CYCLE 4: Mario Odyssey discount ends, but Telegram deletion fails ===
    mock_eshop_c4 = AsyncMock()
    mock_eshop_c4.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop_c4.fetch_popular_discounted_games.return_value = []
    mock_eshop_c4.fetch_discounted_games.return_value = []
    mock_eshop_c4.fetch_us_curated_deals.return_value = []

    async def mock_validate_c4(deals, country="DE", require_discount=True):
        return [GameDeal(
            fs_id=d.fs_id, title=d.title, regular_price=59.99,
            discount_price=59.99, discount_percent=0.0, currency="USD", nsuid=d.nsuid
        ) for d in deals]
    mock_eshop_c4.validate_live_prices.side_effect = mock_validate_c4
    mock_del_c4 = AsyncMock(return_value=False)

    with patch_send_env(fake_load_active, fake_save_active, mock_eshop_c4, mock_bot, mock_del_c4):
        await send_eshop_deals(force=True, reset=False)

    stored_c4 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_c4) == 31, "Failed deletion must NOT lose state; card kept for retry"
    assert len([it for it in stored_c4 if it.get("is_nintendo")]) == 1
    assert mock_del_c4.call_count == 1


@pytest.mark.asyncio
async def test_nintendo_active_discount_price_update_and_expiration_notification():
    """
    Verify that:
    1. If live API confirms an active Nintendo discount with changed price, the card
       is NOT deleted; its caption is edited in-place preserving direct store URL and state updated.
    2. Empty API response (no confirmation) does NOT delete the card.
    3. If Telegram edit fails, the card is preserved in state for retry next cycle.
    4. When a Nintendo deal's sale confirms ended, it is safely deleted and the
       showcase list notification is refreshed without referencing the deleted card.
    """
    state_storage = {}
    def fake_save(data):
        state_storage["showcase"] = json.loads(json.dumps(data))
    def fake_load():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    mario_store_url = "https://www.nintendo.com/us/store/products/super-mario-odyssey-switch/"
    initial_card = {
        "fs_id": "us_70010000000001",
        "nsuid": "70010000000001",
        "title": "Super Mario Odyssey",
        "url": mario_store_url,
        "message_id": 9901,
        "discount_percent": 33.0,
        "discount_price": 39.99,
        "regular_price": 59.99,
        "currency": "USD",
        "country": "US",
        "is_nintendo": True,
    }
    fake_save({"-1001790782971_561344": [initial_card]})

    # --- Scenario 1: Price changed, discount still active -> in-place edit with direct URL ---
    price_updated_deal = GameDeal(
        fs_id="us_70010000000001", title="Super Mario Odyssey",
        regular_price=59.99, discount_price=29.99, discount_percent=50.0,
        currency="USD", nsuid="70010000000001", url=mario_store_url,
    )
    mock_eshop_s1 = AsyncMock()
    mock_eshop_s1.validate_live_prices.return_value = [price_updated_deal]
    mock_eshop_s1.fetch_popular_discounted_games.return_value = []
    mock_eshop_s1.fetch_discounted_games.return_value = []
    mock_eshop_s1.fetch_us_curated_deals.return_value = []

    mock_bot = AsyncMock()
    mock_bot.edit_message_caption.return_value = MagicMock(message_id=9901)
    mock_del = AsyncMock(return_value=True)

    with patch_send_env(fake_load, fake_save, mock_eshop_s1, mock_bot, mock_del):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del.call_count == 0, "Card with active discount must NOT be deleted"
    assert mock_bot.edit_message_caption.call_count == 1
    caption = mock_bot.edit_message_caption.call_args.kwargs.get("caption", "")
    assert mario_store_url in caption, "Direct eShop link must be preserved in edited caption"
    assert f"href='{mario_store_url}'>Nintendo eShop</a>" in caption
    assert "search/#q=Super+Mario+Odyssey'>Nintendo eShop" not in caption
    cards_s1 = fake_load()["-1001790782971_561344"]
    assert len(cards_s1) == 1
    assert cards_s1[0]["discount_price"] == 29.99
    assert cards_s1[0]["discount_percent"] == 50.0
    assert cards_s1[0]["url"] == mario_store_url

    # --- Scenario 2: Empty API response -> card is NOT deleted and state is preserved ---
    mock_eshop_empty = AsyncMock()
    mock_eshop_empty.validate_live_prices.return_value = []
    mock_eshop_empty.fetch_popular_discounted_games.return_value = []
    mock_eshop_empty.fetch_discounted_games.return_value = []
    mock_eshop_empty.fetch_us_curated_deals.return_value = []

    with patch_send_env(fake_load, fake_save, mock_eshop_empty, mock_bot, mock_del):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del.call_count == 0, "Empty API response must NOT delete the Nintendo card"
    assert len(fake_load()["-1001790782971_561344"]) == 1, "Card must be preserved for retry"

    # --- Scenario 3: Price changed again, but Telegram edit fails -> card preserved for retry ---
    price_updated_deal2 = GameDeal(
        fs_id="us_70010000000001", title="Super Mario Odyssey",
        regular_price=59.99, discount_price=35.99, discount_percent=40.0,
        currency="USD", nsuid="70010000000001", url=mario_store_url,
    )
    mock_eshop_s3 = AsyncMock()
    mock_eshop_s3.validate_live_prices.return_value = [price_updated_deal2]
    mock_eshop_s3.fetch_popular_discounted_games.return_value = []
    mock_eshop_s3.fetch_discounted_games.return_value = []
    mock_eshop_s3.fetch_us_curated_deals.return_value = []

    mock_bot_fail = AsyncMock()
    mock_bot_fail.edit_message_caption.side_effect = Exception("Telegram edit caption timeout")
    mock_bot_fail.edit_message_text.side_effect = Exception("Telegram edit text timeout")

    with patch_send_env(fake_load, fake_save, mock_eshop_s3, mock_bot_fail, mock_del):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del.call_count == 0
    cards_s3 = fake_load()["-1001790782971_561344"]
    assert len(cards_s3) == 1
    assert cards_s3[0]["discount_price"] == 29.99, "State preserved with previous price on edit failure"

    # --- Scenario 4: Sale confirmed ended -> safely deleted, notification triggered without deleted card ---
    sale_ended_deal = GameDeal(
        fs_id="us_70010000000001", title="Super Mario Odyssey",
        regular_price=59.99, discount_price=59.99, discount_percent=0.0,
        currency="USD", nsuid="70010000000001", url=mario_store_url,
    )
    mock_eshop_s4 = AsyncMock()
    mock_eshop_s4.validate_live_prices.return_value = [sale_ended_deal]
    mock_eshop_s4.fetch_popular_discounted_games.return_value = []
    mock_eshop_s4.fetch_discounted_games.return_value = []
    mock_eshop_s4.fetch_us_curated_deals.return_value = []

    mock_bot_s4 = AsyncMock()
    sent_notif_mock = MagicMock(message_id=9999)
    mock_bot_s4.send_message.return_value = sent_notif_mock

    with patch_send_env(fake_load, fake_save, mock_eshop_s4, mock_bot_s4, mock_del):
        await send_eshop_deals(force=True, reset=False)

    assert mock_del.call_count == 1, "safe_delete_showcase_message must be called when discount ended"
    cards_s4 = fake_load()["-1001790782971_561344"]
    assert len(cards_s4) == 0, "Deleted card must be removed from state"
    assert mock_bot_s4.send_message.call_count >= 1, "Notification must be sent after deleting expired card"
    notif_call_kwargs = mock_bot_s4.send_message.call_args.kwargs
    assert "Super Mario Odyssey" not in notif_call_kwargs.get("text", "")
