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
        country_code="TR",
        country_name="Turkey",
        currency="TRY",
        regular_price=300.0,
        discount_price=150.0,
        discount_percent=50.0,
        converted_usd=4.5,
        converted_uah=186.75,
        is_discount=True,
    )

    deal = GameDeal(
        fs_id="123",
        title="Test Game",
        regular_price=30.0,
        discount_price=15.0,
        discount_percent=50.0,
        categories=["Puzzle", "Action-Adventure"],
        regional_prices=[p1, p2, p3, p4],
    )

    msg_ua = format_eshop_deal_message(deal, language="UA")
    assert "Test Game" in msg_ua
    assert "#Puzzle" in msg_ua
    assert "#ActionAdventure" in msg_ua
    assert "Польща" in msg_ua
    assert "ПАР" in msg_ua
    assert "Таїланд" in msg_ua
    assert "Туреччина" in msg_ua
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
