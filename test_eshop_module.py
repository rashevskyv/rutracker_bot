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
async def test_showcase_expired_sale_deleted_and_refilled():
    """Verify that expired deals are deleted and exactly the vacated slots are refilled."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    active_showcase = {
        "-1001790782971_561344": [
            # Game A: Sale expired (0% discount, price == regular)
            {
                "fs_id": "game_a",
                "title": "Game A",
                "message_id": 101,
                "discount_percent": 50.0,
                "discount_price": 10.0,
                "regular_price": 20.0,
                "currency": "EUR",
            },
            # Game B: Sale still active
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

    candidate_game_c = GameDeal(fs_id="game_c", title="Game C", regular_price=50.0, discount_price=25.0, discount_percent=50.0, currency="EUR")

    saved_showcase = {}
    deleted_msgs = []

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    async def fake_delete(chat_id, topic_id, message_id, title=""):
        deleted_msgs.append(message_id)
        return True

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game_by_fs_id
    mock_eshop.fetch_popular_discounted_games.return_value = [candidate_game_c]
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

    # 1. Game A (101) was deleted
    assert 101 in deleted_msgs
    assert 102 not in deleted_msgs

    # 2. Saved showcase keeps Game B and adds Game C (vacated slot refilled)
    items = saved_showcase.get("-1001790782971_561344", [])
    titles = [it["title"] for it in items]
    assert "Game A" not in titles
    assert "Game B" in titles
    assert "Game C" in titles


@pytest.mark.asyncio
async def test_failed_telegram_delete_keeps_tracking_and_blocks_refill():
    """Full showcase + refused delete must keep tracking and post 0 (no silent slot free / no growth)."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    items = []
    for i in range(1, 31):
        items.append(
            {
                "fs_id": f"game_{i}",
                "title": f"Game {i}",
                "message_id": 5000 + i,
                "discount_percent": 50.0,
                "discount_price": 10.0,
                "regular_price": 20.0,
                "currency": "EUR",
            }
        )
    # game_1 is expired; games 2..30 still on sale
    active_showcase = {"-1001790782971_561344": items}

    async def mock_get_game(fs_id: str):
        if fs_id == "game_1":
            return GameDeal(
                fs_id="game_1",
                title="Game 1",
                regular_price=20.0,
                discount_price=20.0,
                discount_percent=0.0,
                currency="EUR",
            )
        return GameDeal(
            fs_id=fs_id,
            title=fs_id,
            regular_price=20.0,
            discount_price=10.0,
            discount_percent=50.0,
            currency="EUR",
        )

    saved_showcase = {}

    def fake_save_active(data):
        nonlocal saved_showcase
        saved_showcase = dict(data)

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = [
        GameDeal(fs_id="cand", title="Should Not Post", regular_price=40.0, discount_price=10.0, discount_percent=75.0, currency="EUR")
    ]
    mock_eshop.fetch_discounted_games.return_value = []

    mock_bot = AsyncMock()

    with patch("send_eshop_deals.load_active_showcase", return_value=active_showcase), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message", new_callable=AsyncMock, return_value=False), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    saved_items = saved_showcase.get("-1001790782971_561344", [])
    assert len(saved_items) == 30
    assert any(it.get("message_id") == 5001 for it in saved_items)
    assert mock_bot.send_photo.call_count == 0
    assert mock_bot.send_message.call_count == 0


@pytest.mark.asyncio
async def test_full_showcase_posts_zero_new_cards():
    """Verify that when showcase is at max capacity and all sales are active, 0 new cards are posted."""
    from send_eshop_deals import send_eshop_deals
    from services.eshop.models import GameDeal
    from unittest.mock import AsyncMock, patch, MagicMock

    # 30 active deals
    full_showcase_items = [
        {
            "fs_id": f"game_{i}",
            "title": f"Game {i}",
            "message_id": 1000 + i,
            "discount_percent": 50.0,
            "discount_price": 10.0,
            "regular_price": 20.0,
            "currency": "EUR",
        }
        for i in range(1, 31)
    ]
    active_showcase = {"-1001790782971_561344": full_showcase_items}

    async def mock_get_game(fs_id: str):
        return GameDeal(fs_id=fs_id, title=f"Game {fs_id}", regular_price=20.0, discount_price=10.0, discount_percent=50.0, currency="EUR")

    mock_eshop = AsyncMock()
    mock_eshop.get_game_by_fs_id.side_effect = mock_get_game
    mock_eshop.fetch_popular_discounted_games.return_value = [
        GameDeal(fs_id="cand_1", title="Candidate 1", regular_price=30.0, discount_price=15.0, discount_percent=50.0, currency="EUR")
    ]

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

    # Zero deletions and zero posts
    assert mock_del.call_count == 0
    assert mock_bot.send_photo.call_count == 0
    assert mock_bot.send_message.call_count == 0


@pytest.mark.asyncio
async def test_persist_message_ids_across_consecutive_runs():
    """Verify that newly posted message IDs persist and are correctly deleted on subsequent runs if expired."""
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

    # RUN 2: Game X sale has ended -> must delete message 565315
    expired_game_x = GameDeal(fs_id="gx_1", title="Game X", regular_price=20.0, discount_price=20.0, discount_percent=0.0, currency="EUR")
    mock_eshop_run2 = AsyncMock()
    mock_eshop_run2.get_game_by_fs_id.return_value = expired_game_x
    mock_eshop_run2.fetch_popular_discounted_games.return_value = []
    mock_eshop_run2.fetch_discounted_games.return_value = []

    deleted_run2 = []

    async def fake_delete_run2(chat_id, topic_id, message_id, title=""):
        deleted_run2.append(message_id)
        return True

    with patch("send_eshop_deals.load_active_showcase", side_effect=fake_load_active), \
         patch("send_eshop_deals.save_active_showcase", side_effect=fake_save_active), \
         patch("send_eshop_deals.load_posted_deals", return_value={}), \
         patch("send_eshop_deals.save_posted_deals"), \
         patch("send_eshop_deals.safe_delete_showcase_message", side_effect=fake_delete_run2), \
         patch("send_eshop_deals.EShopService", return_value=mock_eshop_run2), \
         patch("send_eshop_deals.bot", mock_bot), \
         patch("send_eshop_deals.save_last_run"):

        await send_eshop_deals(force=True, reset=False)

    # Deletion was executed on the exact message ID 565315 from Run 1
    assert 565315 in deleted_run2
    assert len(fake_load_active()["-1001790782971_561344"]) == 0


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








