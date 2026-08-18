"""Unit tests for the integrated eShop Deals module in RuTracker Bot."""

import pytest
from services.eshop import (
    CurrencyService,
    DealFilterEngine,
    EShopService,
    GameDeal,
    QualityCriteria,
    RegionalPrice,
    format_eshop_deal_message,
)


def test_eshop_currency_conversion():
    cs = CurrencyService()
    cs._rates = {"USD": 1.0, "EUR": 0.9, "PLN": 4.0, "UAH": 41.50}
    assert cs.convert_to_usd(40.0, "PLN") == 10.0
    assert cs.convert_to_usd(90.0, "EUR") == 100.0
    assert cs.convert_to_uah(40.0, "PLN") == 415.0  # 10 USD * 41.5


def test_eshop_regional_formatting():
    p1 = RegionalPrice(
        country_code="PL",
        country_name="Poland",
        currency="PLN",
        regular_price=40.0,
        discount_price=20.0,
        discount_percent=50.0,
        converted_usd=5.0,
        converted_uah=207.5,
        is_discount=True,
    )
    p2 = RegionalPrice(
        country_code="ZA",
        country_name="South Africa",
        currency="ZAR",
        regular_price=100.0,
        discount_price=60.0,
        discount_percent=40.0,
        converted_usd=3.0,
        converted_uah=124.5,
        is_discount=True,
    )
    p3 = RegionalPrice(
        country_code="TH",
        country_name="Thailand",
        currency="THB",
        regular_price=500.0,
        discount_price=250.0,
        discount_percent=50.0,
        converted_usd=6.5,
        converted_uah=269.75,
        is_discount=True,
    )
    p4 = RegionalPrice(
        country_code="NO",
        country_name="Norway",
        currency="NOK",
        regular_price=200.0,
        discount_price=100.0,
        discount_percent=50.0,
        converted_usd=9.5,
        converted_uah=394.25,
        is_discount=True,
    )
    p5 = RegionalPrice(
        country_code="US",
        country_name="USA",
        currency="USD",
        regular_price=20.0,
        discount_price=10.0,
        discount_percent=50.0,
        converted_usd=10.0,
        converted_uah=415.0,
        is_discount=True,
    )

    deal = GameDeal(
        fs_id="123",
        title="Test Game",
        regular_price=30.0,
        discount_price=15.0,
        discount_percent=50.0,
        categories=["Puzzle", "Action-Adventure"],
        regional_prices=[p1, p2, p3, p4, p5],
    )

    msg_ua = format_eshop_deal_message(deal, language="UA")
    assert "Test Game" in msg_ua
    assert "#Puzzle" in msg_ua
    assert "#ActionAdventure" in msg_ua
    assert "Польща" in msg_ua
    assert "ПАР" in msg_ua
    assert "Тайланд" in msg_ua
    assert "Норвегія" in msg_ua
    assert "Ціни в регіонах eShop" in msg_ua
    assert "грн" in msg_ua
    assert "-50%" in msg_ua


def test_no_discount_formatting():
    from services.eshop.formatters import format_eshop_deal_message
    from services.eshop.models import GameDeal

    deal_no_sale = GameDeal(
        fs_id="cadence_123",
        title="Cadence of Hyrule",
        regular_price=22.49,
        discount_price=22.49,
        discount_percent=0.0,
        currency="EUR",
    )
    msg = format_eshop_deal_message(deal_no_sale, language="UA")
    assert "22.49 EUR" in msg
    assert "<s>" not in msg
    assert "➡️" not in msg
    assert "-0%" not in msg


def test_overlay_platform_badge():
    from PIL import Image
    import io
    from services.eshop.banner_service import overlay_platform_badge

    img = Image.new("RGB", (600, 400), color=(50, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    deal1 = GameDeal(
        fs_id="1",
        title="Switch 1 Game",
        regular_price=50.0,
        discount_price=25.0,
        discount_percent=50.0,
        system_names=["Nintendo Switch"],
    )
    out1 = overlay_platform_badge(raw_bytes, deal1)
    assert out1 is not None
    assert len(out1.getvalue()) > 0

    deal2 = GameDeal(
        fs_id="2",
        title="Switch 2 Game",
        regular_price=60.0,
        discount_price=30.0,
        discount_percent=50.0,
        system_names=["Nintendo Switch 2"],
    )
    out2 = overlay_platform_badge(raw_bytes, deal2)
    assert out2 is not None
    assert len(out2.getvalue()) > 0


def test_wishlist_service(tmp_path):
    from services.eshop.wishlist_service import WishlistService
    test_file = str(tmp_path / "test_wishlist.json")
    wl = WishlistService(filepath=test_file)

    # 1. Add game
    item = wl.add_game(chat_id=12345, title="Hollow Knight", nsuid="70010000003208", topic_id=561344)
    assert item["title"] == "Hollow Knight"
    assert item["nsuid"] == "70010000003208"

    # 2. Get wishlist
    items = wl.get_wishlist(chat_id=12345, topic_id=561344)
    assert len(items) == 1
    assert items[0]["title"] == "Hollow Knight"

    # 3. Add duplicate (should not duplicate)
    wl.add_game(chat_id=12345, title="hollow knight", topic_id=561344)
    assert len(wl.get_wishlist(chat_id=12345, topic_id=561344)) == 1

    # 4. Update notification
    wl.update_notification("12345_561344", "Hollow Knight", 50.0)
    items = wl.get_wishlist(chat_id=12345, topic_id=561344)
    assert items[0]["last_notified_discount"] == 50.0

    # 5. Remove game
    removed = wl.remove_game(chat_id=12345, title="Hollow", topic_id=561344)
    assert removed is True
    assert len(wl.get_wishlist(chat_id=12345, topic_id=561344)) == 0


def test_subscription_service(tmp_path):
    from services.subscription_service import SubscriptionService
    test_file = str(tmp_path / "test_user_subscriptions.json")
    srv = SubscriptionService(filepath=test_file)

    # 1. Default should be all False
    subs = srv.get_subscriptions(chat_id=99999)
    assert subs == {"deals": False, "rutracker": False, "digests": False}

    # 2. Enable rutracker
    updated = srv.set_subscription(chat_id=99999, sub_type="rutracker", enabled=True)
    assert updated["rutracker"] is True
    assert updated["deals"] is False
    assert updated["digests"] is False

    # 3. Check subscribers list
    rutracker_subs = srv.get_subscribers_for("rutracker")
    assert len(rutracker_subs) == 1
    assert rutracker_subs[0]["chat_id"] == 99999

    digest_subs = srv.get_subscribers_for("digests")
    assert len(digest_subs) == 0

    # 4. Enable all
    srv.set_subscription(chat_id=99999, sub_type="all", enabled=True)
    all_subs = srv.get_subscriptions(chat_id=99999)
    assert all_subs == {"deals": True, "rutracker": True, "digests": True}

    # 5. Disable deals
    srv.set_subscription(chat_id=99999, sub_type="deals", enabled=False)
    assert srv.get_subscriptions(chat_id=99999)["deals"] is False


def test_cron_deals_deduplication():
    from send_eshop_deals import _is_deal_already_posted, _record_deal_in_history
    from services.eshop.models import GameDeal

    history = {}
    now_ts = 1787050000.0
    cooldown = 14 * 86400.0

    deal1 = GameDeal(
        fs_id="fs_persona5",
        nsuid="70010000012345",
        title="Persona 5 Royal",
        regular_price=59.99,
        discount_price=23.99,
        discount_percent=60.0,
    )

    # 1. Initially not posted
    assert not _is_deal_already_posted(deal1, history, cooldown, now_ts)

    # 2. Record deal in history
    _record_deal_in_history(history, deal1, now_ts)

    # 3. Now should be detected as already posted by fs_id
    assert _is_deal_already_posted(deal1, history, cooldown, now_ts + 3600)

    # 4. Should also be detected even if fs_id is missing but title matches
    deal1_no_fsid = GameDeal(
        fs_id=None,
        nsuid=None,
        title="Persona 5 Royal",
        regular_price=59.99,
        discount_price=23.99,
        discount_percent=60.0,
    )
    assert _is_deal_already_posted(deal1_no_fsid, history, cooldown, now_ts + 3600)

    # 5. Different game is NOT detected as posted
    deal2 = GameDeal(
        fs_id="fs_zelda",
        title="The Legend of Zelda: Tears of the Kingdom",
        regular_price=69.99,
        discount_price=49.99,
        discount_percent=28.0,
    )
    assert not _is_deal_already_posted(deal2, history, cooldown, now_ts + 3600)

    # 6. After cooldown period expires (15 days later), it can be posted again
    assert not _is_deal_already_posted(deal1, history, cooldown, now_ts + (15 * 86400))


def test_showcase_state_management():
    from send_eshop_deals import load_active_showcase, save_active_showcase
    import os

    test_data = {
        "-100123456_561344": [
            {
                "fs_id": "fs_test",
                "title": "Celeste",
                "message_id": 999,
                "posted_at": 1787050000.0,
                "discount_percent": 75.0,
                "discount_price": 4.99,
                "regular_price": 19.99,
            }
        ]
    }
    save_active_showcase(test_data)
    loaded = load_active_showcase()
    assert "-100123456_561344" in loaded
    assert loaded["-100123456_561344"][0]["title"] == "Celeste"
    assert loaded["-100123456_561344"][0]["message_id"] == 999


def test_clickable_regional_store_links():
    from services.eshop.formatters import get_region_eshop_url
    assert "nintendo.com/us" in get_region_eshop_url("US", "Sonic Origins")
    assert "store.nintendo.com.ar" in get_region_eshop_url("AR", "Celeste")
    assert "nintendo.com/en-gb" in get_region_eshop_url("PL", "Persona 5")


@pytest.mark.asyncio
async def test_strict_deletion_guardrail():
    from send_eshop_deals import safe_delete_showcase_message
    from unittest.mock import AsyncMock, patch

    # 1. Attempt delete on unauthorized chat -> MUST BE BLOCKED
    with patch("send_eshop_deals.IS_TEST_MODE", False):
        result_blocked = await safe_delete_showcase_message(
            chat_id=-1001277664260,  # Kefir_new_games (RuTracker chat)
            topic_id=29459,
            message_id=12345,
            title="Test Game",
        )
        assert result_blocked is False

        # 2. Attempt delete on unauthorized topic in Kefir_ukr -> MUST BE BLOCKED
        result_topic_blocked = await safe_delete_showcase_message(
            chat_id=-1001790782971,  # Kefir_ukr
            topic_id=25501,          # RuTracker topic, NOT deals topic
            message_id=12345,
            title="Test Game",
        )
        assert result_topic_blocked is False


def test_parse_deal_command_args():
    from services.eshop.bot_commands import parse_deal_command_args

    # 1. Default /random
    cnt, r_range, p_range, sort = parse_deal_command_args("/random", default_limit=1, is_random=True)
    assert cnt == 1
    assert r_range is None
    assert p_range is None
    assert sort == "random"

    # 2. /random 4 1000-2000
    cnt, r_range, p_range, sort = parse_deal_command_args("/random 4 1000-2000", default_limit=1, is_random=True)
    assert cnt == 4
    assert r_range == (1000, 2000)
    assert p_range is None
    assert sort == "random"

    # 3. /random 4 1000-2000 100-500
    cnt, r_range, p_range, sort = parse_deal_command_args("/random 4 1000-2000 100-500", default_limit=1, is_random=True)
    assert cnt == 4
    assert r_range == (1000, 2000)
    assert p_range == (100.0, 500.0)
    assert sort == "random"

    # 4. /deals 5 cheap
    cnt, r_range, p_range, sort = parse_deal_command_args("/deals 5 cheap", default_limit=5, is_random=False)
    assert cnt == 5
    assert r_range is None
    assert p_range is None
    assert sort == "price_asc"

    # 5. /deals 4 1-100 200-800 discount
    cnt, r_range, p_range, sort = parse_deal_command_args("/deals 4 1-100 200-800 discount", default_limit=5, is_random=False)
    assert cnt == 4
    assert r_range == (1, 100)
    assert p_range == (200.0, 800.0)
    assert sort == "discount"

    # 6. Cyrillic command aliases
    cnt, r_range, p_range, sort = parse_deal_command_args("/знижки 3 дешеві 50-300грн", default_limit=5, is_random=False)
    assert cnt == 3
    assert p_range == (50.0, 300.0)
    assert sort == "price_asc"


@pytest.mark.asyncio
async def test_get_flexible_deals():
    from services.eshop.deal_filter import DealFilterEngine
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, MagicMock

    mock_eshop = AsyncMock()
    mock_ratings = AsyncMock()
    mock_currency = MagicMock()
    mock_currency.convert.side_effect = lambda val, c_from, c_to: val * 45.0 if c_from == "EUR" else val

    # Prepare dummy candidate deals
    deals = [
        GameDeal(fs_id="1", title="Game 1", regular_price=20.0, discount_price=5.0, discount_percent=75.0, currency="EUR"),
        GameDeal(fs_id="2", title="Game 2", regular_price=40.0, discount_price=10.0, discount_percent=75.0, currency="EUR"),
        GameDeal(fs_id="3", title="Game 3", regular_price=60.0, discount_price=30.0, discount_percent=50.0, currency="EUR"),
    ]
    mock_eshop.fetch_discounted_games.return_value = deals
    mock_eshop.fetch_popular_discounted_games.return_value = []

    engine = DealFilterEngine(eshop_service=mock_eshop, rating_service=mock_ratings)

    # 1. Query with price filter (5.0 EUR = 225 UAH, 10.0 EUR = 450 UAH, 30.0 EUR = 1350 UAH)
    # Price range 200 - 500 UAH should return Game 1 and Game 2
    res = await engine.get_flexible_deals(
        limit=5,
        rank_range=(1, 50),
        price_range_uah=(200.0, 500.0),
        sort_by="price_asc",
        currency_service=mock_currency,
    )
    assert len(res) == 2
    assert res[0].title == "Game 1"
    assert res[1].title == "Game 2"

    # 2. Query random
    res_rnd = await engine.get_flexible_deals(
        limit=1,
        rank_range=(1, 50),
        is_random=True,
        currency_service=mock_currency,
    )
    assert len(res_rnd) == 1




