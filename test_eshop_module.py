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
    assert "nintendo.com/es-ar" in get_region_eshop_url("AR", "Celeste")
    assert "nintendo.com/pt-br" in get_region_eshop_url("BR", "Celeste")
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


@pytest.mark.asyncio
async def test_safe_delete_cannot_delete_is_failure_not_success():
    """Telegram 'message can't be deleted' means the message still exists — must return False."""
    from send_eshop_deals import safe_delete_showcase_message
    from unittest.mock import AsyncMock, patch

    with patch("send_eshop_deals.IS_TEST_MODE", False):
        with patch("send_eshop_deals.bot") as mock_bot:
            mock_bot.delete_message = AsyncMock(
                side_effect=Exception("Bad Request: message can't be deleted")
            )
            result = await safe_delete_showcase_message(
                chat_id=-1001790782971,
                topic_id=561344,
                message_id=564561,
                title="Persona 5 Royal",
            )
            assert result is False

            mock_bot.delete_message = AsyncMock(
                side_effect=Exception("Bad Request: message to delete not found")
            )
            result_absent = await safe_delete_showcase_message(
                chat_id=-1001790782971,
                topic_id=561344,
                message_id=564947,
                title="Gone",
            )
            assert result_absent is True


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
    mock_currency.convert_to_uah.side_effect = lambda val, c_from: val * 45.0 if c_from == "EUR" else val
    mock_currency.convert.side_effect = lambda val, c_from, c_to: val * 45.0 if c_from == "EUR" else val

    # Prepare dummy candidate deals
    deals = [
        GameDeal(fs_id="1", title="Game 1", regular_price=20.0, discount_price=5.0, discount_percent=75.0, currency="EUR", downloads_rank=10),
        GameDeal(fs_id="2", title="Game 2", regular_price=40.0, discount_price=10.0, discount_percent=75.0, currency="EUR", downloads_rank=20),
        GameDeal(fs_id="3", title="Game 3", regular_price=60.0, discount_price=30.0, discount_percent=50.0, currency="EUR", downloads_rank=30),
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


def test_title_similarity_guardrail():
    from services.eshop.region_price_service import _is_title_match

    # 1. Must reject completely different titles sharing a common word like 'Legacy'
    assert _is_title_match("Hogwarts Legacy", "Unstrong Legacy") is False
    assert _is_title_match("Hogwarts Legacy", "Dice Legacy") is False
    assert _is_title_match("Hogwarts Legacy", "Alwa's Legacy") is False

    # 2. Must accept exact and legitimate edition variants
    assert _is_title_match("Hogwarts Legacy", "Hogwarts Legacy: Digital Deluxe Edition") is True
    assert _is_title_match("Sonic Origins", "Sonic Origins Plus") is True
    assert _is_title_match("Celeste", "Celeste") is True
    assert _is_title_match("Super Mario Odyssey", "Mario Odyssey") is True


@pytest.mark.asyncio
async def test_cmd_remove_deals():
    from telebot.async_telebot import AsyncTeleBot
    from telebot.types import Message, Chat
    from services.eshop.bot_commands import register_eshop_handlers
    from unittest.mock import AsyncMock, patch

    bot = AsyncTeleBot("123456:dummy_token")
    mock_eshop = AsyncMock()
    mock_engine = AsyncMock()
    mock_criteria = AsyncMock()
    register_eshop_handlers(bot, mock_engine, mock_eshop, mock_criteria)

    msg = Message(
        message_id=555,
        from_user=None,
        date=1234567,
        chat=Chat(id=-1001790782971, type="supergroup"),
        content_type="text",
        options={},
        json_string="",
    )
    msg.text = "/remove Hogwarts Legacy"
    msg.message_thread_id = 561344

    with patch("telebot.async_telebot.AsyncTeleBot.reply_to", new_callable=AsyncMock) as mock_reply:
        with patch("send_eshop_deals.load_active_showcase", return_value={"-1001790782971_561344": [{"title": "Hogwarts Legacy", "message_id": 999}]}):
            with patch("send_eshop_deals.safe_delete_showcase_message", new_callable=AsyncMock) as mock_del:
                mock_del.return_value = True
                for handler in bot.message_handlers:
                    cmds = handler.get("filters", {}).get("commands", [])
                    if "remove" in cmds:
                        await handler["function"](msg)
                        break
                assert mock_del.called

    # Test 2: Remove by reply to message
    msg_reply = Message(
        message_id=556,
        from_user=None,
        date=1234567,
        chat=Chat(id=-1001790782971, type="supergroup"),
        content_type="text",
        options={},
        json_string="",
    )
    msg_reply.text = "/remove"
    msg_reply.message_thread_id = 561344
    msg_reply.reply_to_message = Message(
        message_id=999,
        from_user=None,
        date=1234560,
        chat=Chat(id=-1001790782971, type="supergroup"),
        content_type="text",
        options={},
        json_string="",
    )

    with patch("send_eshop_deals.safe_delete_showcase_message", new_callable=AsyncMock) as mock_del2:
        mock_del2.return_value = True
        for handler in bot.message_handlers:
            cmds = handler.get("filters", {}).get("commands", [])
            if "remove" in cmds:
                await handler["function"](msg_reply)
                break
        assert mock_del2.called

    # Test 3: List showcase command
    msg_list = Message(
        message_id=557,
        from_user=None,
        date=1234567,
        chat=Chat(id=-1001790782971, type="supergroup"),
        content_type="text",
        options={},
        json_string="",
    )
    msg_list.text = "/showcase"
    msg_list.message_thread_id = 561344

    with patch("send_eshop_deals.load_active_showcase", return_value={"-1001790782971_561344": [{"title": "Zelda", "message_id": 100, "discount_percent": 30, "discount_price": 40.0, "currency": "EUR"}]}):
        with patch("services.eshop.bot_commands.safe_reply", new_callable=AsyncMock) as mock_safe_reply:
            for handler in bot.message_handlers:
                cmds = handler.get("filters", {}).get("commands", [])
                if "showcase" in cmds:
                    await handler["function"](msg_list)
                    break
            assert mock_safe_reply.called


def test_cli_list_showcase(capsys):
    from send_eshop_deals import list_showcase_deals
    from unittest.mock import patch

    with patch("send_eshop_deals.load_active_showcase", return_value={"-1001790782971_561344": [{"title": "Mario Odyssey", "message_id": 101, "discount_percent": 33, "discount_price": 39.99, "currency": "EUR"}]}):
        list_showcase_deals()
        captured = capsys.readouterr()
        assert "Mario Odyssey" in captured.out
        assert "1/30" in captured.out


@pytest.mark.asyncio
async def test_showcase_keeps_active_sale_not_in_top_candidates():
    """Verify that a tracked game with an active sale is KEPT even if NOT in today's top candidate pool."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    # Tracked in showcase: Hollow Knight (fs_id "hk_1", msg_id 501, 50% off)
    active_showcase = {
        "-1001790782971_561344": [
            {
                "fs_id": "hk_1",
                "title": "Hollow Knight",
                "message_id": 501,
                "discount_percent": 50.0,
                "discount_price": 7.49,
                "regular_price": 14.99,
                "currency": "EUR",
            }
        ]
    }

    # Live check confirms Hollow Knight is still on sale
    hk_live_deal = GameDeal(
        fs_id="hk_1",
        title="Hollow Knight",
        regular_price=14.99,
        discount_price=7.49,
        discount_percent=50.0,
        currency="EUR",
    )

    # Fresh candidates pool does NOT contain Hollow Knight (only new game Fresh Candidate)
    new_candidate = GameDeal(
        fs_id="fresh_cand_1",
        title="Fresh Unique Candidate",
        regular_price=19.99,
        discount_price=4.99,
        discount_percent=75.0,
        currency="EUR",
    )

    saved_showcase = {}
    deleted_msgs = []

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    async def fake_delete(chat_id, topic_id, message_id, title=""):
        deleted_msgs.append(message_id)
        return True

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.return_value = hk_live_deal
    mock_eshop.fetch_popular_discounted_games.return_value = [new_candidate]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 999
    mock_bot.send_photo.return_value = mock_sent_msg
    mock_bot.send_message.return_value = mock_sent_msg

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message", side_effect=fake_delete), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Hollow Knight was NOT deleted
    assert 501 not in deleted_msgs

    # Hollow Knight remains in saved showcase along with newly added Fresh Unique Candidate
    items = saved_showcase.get("-1001790782971_561344", [])
    titles = [it["title"] for it in items]
    assert "Hollow Knight" in titles
    assert "Fresh Unique Candidate" in titles


@pytest.mark.asyncio
async def test_expired_sale_edited_in_place_not_deleted():
    """Verify that expired deals are edited in place rather than deleted."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    active_showcase = {
        "-1001790782971_561344": [
            # Game A: Sale expired
            {
                "fs_id": "game_a",
                "title": "Game A",
                "message_id": 101,
                "discount_percent": 50.0,
                "discount_price": 10.0,
                "regular_price": 20.0,
                "currency": "EUR",
            },
            # Game B: Sale active
            {
                "fs_id": "game_b",
                "title": "Game B",
                "message_id": 102,
                "discount_percent": 50.0,
                "discount_price": 15.0,
                "regular_price": 30.0,
                "currency": "EUR",
            },
        ]
    }

    async def mock_get_game_by_fs_id(fs_id: str):
        if fs_id == "game_a":
            return GameDeal(fs_id="game_a", title="Game A", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR")
        if fs_id == "game_b":
            return GameDeal(fs_id="game_b", title="Game B", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR")
        return None

    candidate_game_c = GameDeal(
        fs_id="game_c",
        title="Game C",
        regular_price=50.0,
        discount_price=25.0,
        discount_percent=50.0,
        currency="EUR",
        banner_url="https://example.com/game_c.jpg",
    )

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game_by_fs_id
    mock_eshop.fetch_popular_discounted_games.return_value = [candidate_game_c]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_bot.edit_message_media.return_value = MagicMock()
    mock_bot.edit_message_text.return_value = MagicMock()
    mock_notif = MagicMock()
    mock_notif.message_id = 999
    mock_bot.send_message.return_value = mock_notif
    mock_bot.send_photo.return_value = mock_notif

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # 1. No deletion was called
    assert mock_del.call_count == 0

    # 2. Game A's message_id (101) was edited
    assert mock_bot.edit_message_media.call_count == 1
    assert mock_bot.edit_message_media.call_args.kwargs.get("message_id") == 101

    # 3. Saved showcase has Game C with message_id 101 and Game B with message_id 102
    items = saved_showcase.get("-1001790782971_561344", [])
    titles = [it["title"] for it in items]
    assert "Game A" not in titles
    assert "Game B" in titles
    assert "Game C" in titles
    c_item = next(it for it in items if it["title"] == "Game C")
    assert c_item["message_id"] == 101


@pytest.mark.asyncio
async def test_full_showcase_posts_zero_new_cards():
    """Verify that when showcase is at max capacity, candidates with worse or unknown rank cause no churn."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    # 30 active deals with known downloads_rank (10, 20, ..., 300)
    full_showcase_items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 1000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": full_showcase_items}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    # Candidates with worse rank (500 > 300) and unknown rank (None)
    mock_eshop.fetch_popular_discounted_games.return_value = [
        GameDeal(fs_id="cand_worse", title="Candidate Worse", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR", downloads_rank=500),
        GameDeal(fs_id="cand_no_rank", title="Candidate No Rank", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR", downloads_rank=None),
    ]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase"), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Zero deletions and zero posts (no churn)
    assert mock_del.call_count == 0
    assert mock_bot.send_photo.call_count == 0
    assert mock_bot.send_message.call_count == 0
    assert mock_bot.edit_message_media.call_count == 0
    assert mock_bot.edit_message_text.call_count == 0


@pytest.mark.asyncio
async def test_full_showcase_rotates_by_editing_worst_card():
    """
    1. Повна вітрина з кращим кандидатом:
       - викликається edit існуючої найгіршої картки;
       - її message_id лишається тим самим;
       - не викликається видалення картки й не створюється нова картка;
       - state оновлений новою грою;
       - створюється рівно один notification;
       - caption/text містить посилання на змінену картку.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    # 30 active deals with known ranks: game_1 (rank 10, best) ... game_30 (rank 300, worst)
    full_showcase_items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 1000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": full_showcase_items}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    cand_top = GameDeal(
        fs_id="cand_top",
        title="Top Candidate",
        regular_price=40.0,
        discount_price=20.0,
        discount_percent=50.0,
        currency="EUR",
        downloads_rank=5,
        banner_url="https://example.com/top.jpg",
    )

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = [cand_top]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_edit_msg = MagicMock()
    mock_edit_msg.message_id = 1030
    mock_bot.edit_message_media.return_value = mock_edit_msg
    mock_bot.edit_message_text.return_value = mock_edit_msg

    mock_notif_msg = MagicMock()
    mock_notif_msg.message_id = 77777
    mock_bot.send_message.return_value = mock_notif_msg
    mock_bot.send_photo.return_value = mock_notif_msg

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # 1. safe_delete_showcase_message was NOT called for rotation
    assert mock_del.call_count == 0

    # 2. edit_message_media was called on the worst card's message_id (1030)
    assert mock_bot.edit_message_media.call_count == 1
    call_kwargs = mock_bot.edit_message_media.call_args.kwargs
    assert call_kwargs.get("message_id") == 1030

    # 3. No new game card was posted (only 1 notification message sent)
    assert mock_bot.send_photo.call_count == 0
    assert mock_bot.send_message.call_count == 1  # exactly one notification

    # 4. State is updated: Game 30 replaced by Top Candidate, message_id remains 1030
    items = saved_showcase.get("-1001790782971_561344", [])
    assert len(items) == 30
    titles = [it["title"] for it in items]
    assert "Game 30" not in titles
    assert "Top Candidate" in titles
    cand_item = next(it for it in items if it["title"] == "Top Candidate")
    assert cand_item["message_id"] == 1030
    assert cand_item["downloads_rank"] == 5

    # 5. Notification text contains clickable link to changed card (message_id 1030)
    notif_call_kwargs = mock_bot.send_message.call_args.kwargs
    notif_text = notif_call_kwargs.get("text", "")
    assert "https://t.me/kefir_ukr/561344/1030" in notif_text
    assert "Top Candidate" in notif_text


@pytest.mark.asyncio
async def test_multiple_successful_rotations_notification_lists_all():
    """
    2. Кілька успішних замін:
       - notification містить посилання на КОЖНУ замінену картку, не лише на чотири з колажу.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    # 30 items in showcase
    full_showcase_items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 2000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": full_showcase_items}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    # 6 new candidates with ranks 1..6 (better than worst 6 cards with ranks 250..300)
    candidates = [
        GameDeal(
            fs_id=f"top_cand_{i}",
            title=f"Top Candidate {i}",
            regular_price=40.0,
            discount_price=20.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=i,
            banner_url=f"https://example.com/top_{i}.jpg",
        )
        for i in range(1, 7)
    ]

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = candidates
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_edit_msg = MagicMock()
    mock_bot.edit_message_media.return_value = mock_edit_msg
    mock_bot.edit_message_text.return_value = mock_edit_msg

    mock_notif = MagicMock()
    mock_notif.message_id = 88888
    mock_bot.send_photo.return_value = mock_notif
    mock_bot.send_message.return_value = mock_notif

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # 6 cards were edited
    assert mock_bot.edit_message_media.call_count == 6

    # Exactly 1 notification was sent
    assert mock_bot.send_message.call_count == 1
    notif_text = mock_bot.send_message.call_args.kwargs.get("text", "")

    # Notification must contain links to ALL 6 changed cards (message_ids 2025..2030)
    for i in range(1, 7):
        target_mid = 2030 - (i - 1)
        assert f"https://t.me/kefir_ukr/561344/{target_mid}" in notif_text
        assert f"Top Candidate {i}" in notif_text


@pytest.mark.asyncio
async def test_edit_failure_preserves_state_no_duplicates_no_notification():
    """
    3. Помилка edit:
       - state не змінюється;
       - картка не дублюється;
       - notification не включає невдалу заміну.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 3000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": [dict(it) for it in items]}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    cand_top = GameDeal(
        fs_id="cand_fail",
        title="Candidate Fail",
        regular_price=40.0,
        discount_price=20.0,
        discount_percent=50.0,
        currency="EUR",
        downloads_rank=5,
        banner_url="https://example.com/fail.jpg",
    )

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = [cand_top]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    # All edit methods fail
    mock_bot.edit_message_media.side_effect = Exception("Telegram API error: media cannot be edited")
    mock_bot.edit_message_caption.side_effect = Exception("Telegram API error: caption cannot be edited")
    mock_bot.edit_message_text.side_effect = Exception("Telegram API error: text cannot be edited")

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # 1. State was NOT modified: original items preserved
    saved_items = saved_showcase.get("-1001790782971_561344", [])
    assert len(saved_items) == 30
    saved_titles = [it["title"] for it in saved_items]
    assert "Game 30" in saved_titles
    assert "Candidate Fail" not in saved_titles

    # 2. All edit methods were tried and failed
    assert mock_bot.edit_message_media.call_count == 1
    assert mock_bot.edit_message_caption.call_count == 1
    assert mock_bot.edit_message_text.call_count == 1

    # 3. No card was duplicated, no deletion occurred
    assert mock_del.call_count == 0

    # 4. No notification was sent because 0 cards were updated
    assert mock_bot.send_message.call_count == 0
    assert mock_bot.send_photo.call_count == 0


@pytest.mark.asyncio
async def test_edit_fallback_media_to_caption_success():
    """
    Fallback edit_message_media -> edit_message_caption:
    - edit_message_media fails, but edit_message_caption succeeds;
    - card is updated in-place keeping the same message_id;
    - edit_message_text is not called;
    - notification is sent with the updated card link.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 5000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": [dict(it) for it in items]}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    cand_top = GameDeal(
        fs_id="cand_caption",
        title="Candidate Caption",
        regular_price=40.0,
        discount_price=20.0,
        discount_percent=50.0,
        currency="EUR",
        downloads_rank=5,
        banner_url="https://example.com/banner.jpg",
    )

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = [cand_top]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    # media edit fails
    mock_bot.edit_message_media.side_effect = Exception("Telegram API error: media cannot be edited")
    # caption edit succeeds
    mock_edit_caption_msg = MagicMock()
    mock_edit_caption_msg.message_id = 5030
    mock_bot.edit_message_caption.return_value = mock_edit_caption_msg
    mock_bot.edit_message_text.return_value = mock_edit_caption_msg

    mock_notif = MagicMock()
    mock_notif.message_id = 99991
    mock_bot.send_message.return_value = mock_notif
    mock_bot.send_photo.return_value = mock_notif

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # 1. edit_message_media failed and fell back to edit_message_caption
    assert mock_bot.edit_message_media.call_count == 1
    assert mock_bot.edit_message_caption.call_count == 1
    assert mock_bot.edit_message_text.call_count == 0
    assert mock_del.call_count == 0

    # 2. State is updated with Candidate Caption replacing Game 30 at message_id 5030
    saved_items = saved_showcase.get("-1001790782971_561344", [])
    assert len(saved_items) == 30
    saved_titles = [it["title"] for it in saved_items]
    assert "Game 30" not in saved_titles
    assert "Candidate Caption" in saved_titles
    item = next(it for it in saved_items if it["title"] == "Candidate Caption")
    assert item["message_id"] == 5030

    # 3. Notification was sent with link to changed card
    assert mock_bot.send_message.call_count == 1
    notif_text = mock_bot.send_message.call_args.kwargs.get("text", "")
    assert "https://t.me/kefir_ukr/561344/5030" in notif_text
    assert "Candidate Caption" in notif_text


@pytest.mark.asyncio
async def test_edit_without_new_cover_updates_existing_photo_caption():
    """A coverless candidate still replaces an existing photo card by editing its caption."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, MagicMock, patch

    active_showcase = {
        "-1001790782971_561344": [{
            "fs_id": "old", "title": "Old", "message_id": 901,
            "discount_percent": 50.0, "discount_price": 10.0,
            "regular_price": 20.0, "currency": "EUR", "downloads_rank": 100,
        }]
    }
    candidate = GameDeal(
        fs_id="new", title="No Cover", regular_price=20.0, discount_price=10.0,
        discount_percent=50.0, currency="EUR", downloads_rank=10,
    )
    current_deal = GameDeal(
        fs_id="old", title="Old", regular_price=20.0, discount_price=20.0,
        discount_percent=0.0, currency="EUR", downloads_rank=100,
    )
    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.return_value = current_deal
    mock_eshop.fetch_popular_discounted_games.return_value = [candidate]
    mock_eshop.fetch_discounted_games.return_value = []
    mock_bot = AsyncMock()
    mock_bot.edit_message_caption.return_value = MagicMock()
    notification = MagicMock()
    notification.message_id = 902
    mock_bot.send_message.return_value = notification

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase"), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):
        await send_eshop_deals(force=True, reset=False)

    assert mock_bot.edit_message_media.call_count == 0
    assert mock_bot.edit_message_caption.call_count == 1
    assert mock_bot.edit_message_caption.call_args.kwargs["message_id"] == 901
    assert mock_bot.edit_message_text.call_count == 0


@pytest.mark.asyncio
async def test_no_changes_sends_no_notification():
    """
    4. Відсутність змін:
       - notification не надсилається.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 4000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
            "downloads_rank": i * 10,
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": items}

    async def mock_get_game(fs_id: str):
        idx = int(fs_id.replace("game_", ""))
        return GameDeal(
            fs_id=fs_id,
            title=f"Game {fs_id}",
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
            downloads_rank=idx * 10,
        )

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    # No candidates better than existing cards (ranks 500, 600 > 300)
    mock_eshop.fetch_popular_discounted_games.return_value = [
        GameDeal(fs_id="cand_worse", title="Candidate Worse", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR", downloads_rank=500),
    ]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase"), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Zero edits and zero notifications
    assert mock_bot.edit_message_media.call_count == 0
    assert mock_bot.edit_message_text.call_count == 0
    assert mock_bot.send_photo.call_count == 0
    assert mock_bot.send_message.call_count == 0
    assert mock_del.call_count == 0


@pytest.mark.asyncio
async def test_notification_sends_photo_collage_when_covers_available():
    """Verify that notification uses send_photo with a Pillow collage when covers are available."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock
    import io
    from PIL import Image

    active_showcase = {
        "-1001790782971_561344": [
            {"fs_id": "g1", "title": "G1", "message_id": 901, "discount_percent": 50.0, "discount_price": 10.0, "regular_price": 20.0, "currency": "EUR", "downloads_rank": 100}
        ]
    }

    cand = GameDeal(fs_id="g2", title="G2", regular_price=20.0, discount_price=10.0, discount_percent=50.0, currency="EUR", downloads_rank=10, banner_url="https://example.com/g2.jpg")

    # Mock badged cover with a real test Image
    test_img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    buf.seek(0)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.return_value = GameDeal(fs_id="g1", title="G1", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR", downloads_rank=100)
    mock_eshop.fetch_popular_discounted_games.return_value = [cand]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_bot.edit_message_media.return_value = MagicMock()
    mock_bot.edit_message_text.return_value = MagicMock()
    mock_notif = MagicMock()
    mock_notif.message_id = 12345
    mock_bot.send_photo.return_value = mock_notif

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase"), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=buf), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # send_photo was called for the notification with caption and collage bytes
    assert mock_bot.send_photo.call_count == 1
    photo_kwargs = mock_bot.send_photo.call_args.kwargs
    assert "https://t.me/kefir_ukr/561344/901" in photo_kwargs.get("caption", "")
    assert len(photo_kwargs.get("photo")) > 0


@pytest.mark.asyncio
async def test_previous_notification_cleanup_before_new():
    """Verify that previous notification (< 48h) is deleted before sending a new one."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock
    import time

    active_showcase = {
        "-1001790782971_561344": [
            {"fs_id": "g1", "title": "G1", "message_id": 901, "discount_percent": 50.0, "discount_price": 10.0, "regular_price": 20.0, "currency": "EUR", "downloads_rank": 100}
        ]
    }
    cand = GameDeal(fs_id="g2", title="G2", regular_price=20.0, discount_price=10.0, discount_percent=50.0, currency="EUR", downloads_rank=10, banner_url="https://example.com/g2.jpg")

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.return_value = GameDeal(fs_id="g1", title="G1", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR", downloads_rank=100)
    mock_eshop.fetch_popular_discounted_games.return_value = [cand]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_bot.edit_message_media.return_value = MagicMock()
    mock_bot.edit_message_text.return_value = MagicMock()
    mock_notif = MagicMock()
    mock_notif.message_id = 99999
    mock_bot.send_message.return_value = mock_notif

    deleted_msgs = []
    async def fake_delete(chat_id, topic_id, message_id, title=""):
        deleted_msgs.append(message_id)
        return True

    now_ts = time.time()
    last_run_mock = {
        "last_run_timestamp": now_ts - 3600,
        "last_notification_message_id": 88888,
        "last_notification_timestamp": now_ts - 3600,
    }

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase"), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message", side_effect=fake_delete), \
         patch("send_eshop_deals.load_last_run", return_value=last_run_mock), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Previous notification 88888 was deleted
    assert 88888 in deleted_msgs
    assert mock_bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_notification_skipped_if_previous_notification_delete_fails():
    """
    safe_delete of previous notification returns False:
    - card is still successfully updated in-place in active showcase;
    - new notification is NOT sent (preventing duplicates);
    - previous notification metadata is preserved in last_run state.
    """
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock
    import time

    active_showcase = {
        "-1001790782971_561344": [
            {"fs_id": "g1", "title": "G1", "message_id": 901, "discount_percent": 50.0, "discount_price": 10.0, "regular_price": 20.0, "currency": "EUR", "downloads_rank": 100}
        ]
    }
    cand = GameDeal(fs_id="g2", title="G2", regular_price=20.0, discount_price=10.0, discount_percent=50.0, currency="EUR", downloads_rank=10, banner_url="https://example.com/g2.jpg")

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.return_value = GameDeal(fs_id="g1", title="G1", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR", downloads_rank=100)
    mock_eshop.fetch_popular_discounted_games.return_value = [cand]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()
    mock_edit_msg = MagicMock()
    mock_edit_msg.message_id = 901
    mock_bot.edit_message_media.return_value = mock_edit_msg
    mock_bot.edit_message_caption.return_value = mock_edit_msg
    mock_bot.edit_message_text.return_value = mock_edit_msg

    now_ts = time.time()
    last_run_mock = {
        "last_run_timestamp": now_ts - 3600,
        "last_notification_message_id": 88888,
        "last_notification_timestamp": now_ts - 3600,
    }

    saved_showcase = {}
    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    saved_last_run = {}
    def fake_save_last_run(data):
        nonlocal saved_last_run
        saved_last_run = dict(data)

    # safe_delete returns False (deletion failed)
    mock_del = AsyncMock(return_value=False)

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message", mock_del), \
         patch("send_eshop_deals.load_last_run", return_value=last_run_mock), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run", side_effect=fake_save_last_run):

        await send_eshop_deals(force=True, reset=False)

    # 1. safe_delete was attempted for previous notification 88888
    assert mock_del.call_count == 1
    assert mock_del.call_args.kwargs.get("message_id") == 88888

    # 2. In-place card edit succeeded and active showcase is validly updated
    items = saved_showcase.get("-1001790782971_561344", [])
    assert len(items) == 1
    assert items[0]["title"] == "G2"
    assert items[0]["message_id"] == 901

    # 3. New notification was NOT sent
    assert mock_bot.send_message.call_count == 0
    assert mock_bot.send_photo.call_count == 0

    # 4. Previous notification metadata is preserved in saved last run
    assert saved_last_run.get("last_notification_message_id") == 88888
    assert saved_last_run.get("last_notification_timestamp") == now_ts - 3600


@pytest.mark.asyncio
async def test_persist_message_ids_across_consecutive_runs():
    """Verify that newly posted message IDs persist and are edited in place on subsequent runs when replaced."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock
    import json

    state_storage = {}

    def fake_save_active(data):
        state_storage["showcase"] = json.loads(json.dumps(data))

    def fake_load_active():
        return state_storage.get("showcase", {"-1001790782971_561344": []})

    # RUN 1: Empty showcase -> post Game X with message_id 565315
    game_x = GameDeal(fs_id="gx_1", title="Game X", regular_price=20.0, discount_price=10.0, discount_percent=50.0, currency="EUR")

    mock_eshop = AsyncMock()
    mock_eshop.fetch_popular_discounted_games.return_value = [game_x]
    mock_eshop.fetch_discounted_games.return_value = []
    mock_eshop.get_game_by_fs_id.return_value = game_x

    mock_bot = AsyncMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 565315
    mock_bot.send_photo.return_value = mock_sent_msg
    mock_bot.send_message.return_value = mock_sent_msg

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Verify Run 1 stored message_id 565315
    stored = fake_load_active()["-1001790782971_561344"]
    assert len(stored) == 1
    assert stored[0]["message_id"] == 565315

    # RUN 2: Game X sale has ended, no new candidates -> Game X remains in state awaiting replacement
    expired_game_x = GameDeal(fs_id="gx_1", title="Game X", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR")
    mock_eshop_run2 = AsyncMock()
    mock_eshop_run2.get_game_by_fs_id.return_value = expired_game_x
    mock_eshop_run2.fetch_popular_discounted_games.return_value = []
    mock_eshop_run2.fetch_discounted_games.return_value = []

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del_run2, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop_run2), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # In Run 2, Game X is NOT deleted
    assert mock_del_run2.call_count == 0
    assert len(fake_load_active()["-1001790782971_561344"]) == 1
    assert fake_load_active()["-1001790782971_561344"][0]["message_id"] == 565315

    # RUN 3: New candidate Game Y arrives -> Game X (565315) is EDITED into Game Y
    game_y = GameDeal(fs_id="gy_1", title="Game Y", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR", banner_url="https://example.com/gy.jpg")
    mock_eshop_run3 = AsyncMock()
    mock_eshop_run3.get_game_by_fs_id.return_value = expired_game_x
    mock_eshop_run3.fetch_popular_discounted_games.return_value = [game_y]
    mock_eshop_run3.fetch_discounted_games.return_value = []

    mock_bot.edit_message_media.return_value = MagicMock()
    mock_bot.edit_message_text.return_value = MagicMock()

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message") as mock_del_run3, \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop_run3), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.download_and_badge_cover", new_callable=AsyncMock, return_value=None), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    assert mock_del_run3.call_count == 0
    assert mock_bot.edit_message_media.call_count >= 1
    stored_run3 = fake_load_active()["-1001790782971_561344"]
    assert len(stored_run3) == 1
    assert stored_run3[0]["title"] == "Game Y"
    assert stored_run3[0]["message_id"] == 565315


def test_parse_message_id_targets():
    from send_eshop_deals import parse_message_id_targets
    # Test range and single ID parsing
    res = parse_message_id_targets("564561-564563, 564947, 564949-564950")
    assert res == [564561, 564562, 564563, 564947, 564949, 564950]


def test_gist_merge_eshop_active_showcase():
    import json
    from sync_gist_state import merge_json_files

    local_data = {
        "-1001790782971_561344": [
            {"title": "Game 1", "message_id": 565315, "posted_at": 1788000000.0},
            {"title": "Game 2", "message_id": 565316, "posted_at": 1788000100.0},
        ]
    }
    gist_stale_data = {
        "-1001790782971_561344": [
            {"title": "Old Game", "message_id": 561432, "posted_at": 1787000000.0}
        ]
    }

    merged = merge_json_files(
        "eshop_active_showcase.json",
        json.dumps(local_data),
        json.dumps(gist_stale_data),
    )
    res = json.loads(merged)
    assert len(res["-1001790782971_561344"]) == 2
    assert res["-1001790782971_561344"][0]["message_id"] == 565315






