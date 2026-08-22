"""Interactive Telegram command handlers for eShop Deals in RuTracker Bot."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

from services.eshop.currency_service import CurrencyService
from services.eshop.deal_filter import DealFilterEngine
from services.eshop.eshop_service import EShopService
from services.eshop.formatters import format_eshop_deal_message
from services.eshop.banner_service import download_and_badge_cover
from services.eshop.models import QualityCriteria
from services.eshop.rating_service import RatingService
from services.eshop.region_price_service import RegionPriceService, _is_title_match
from services.eshop.wishlist_service import WishlistService
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

SUBSCRIPTIONS_FILE = os.path.join("data", "eshop_subscriptions.json")
CUSTOM_SETTINGS_FILE = os.path.join("data", "eshop_chat_settings.json")


def load_json_file(file_path: str, default: dict) -> dict:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
    return default.copy()


def save_json_file(file_path: str, data: dict) -> None:
    os.makedirs("data", exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save {file_path}: {e}")


def get_chat_criteria(chat_id: int, global_criteria: QualityCriteria) -> QualityCriteria:
    settings = load_json_file(CUSTOM_SETTINGS_FILE, {})
    chat_cfg = settings.get(str(chat_id), {})
    return QualityCriteria(
        min_discount_percent=float(chat_cfg.get("min_discount_percent", global_criteria.min_discount_percent)),
        min_metacritic_score=int(chat_cfg.get("min_metacritic_score", global_criteria.min_metacritic_score)),
        min_rawg_rating=float(chat_cfg.get("min_rawg_rating", global_criteria.min_rawg_rating)),
        max_price=chat_cfg.get("max_price", global_criteria.max_price),
        require_rating=global_criteria.require_rating,
    )


def update_chat_criteria(chat_id: int, **kwargs) -> QualityCriteria:
    settings = load_json_file(CUSTOM_SETTINGS_FILE, {})
    chat_key = str(chat_id)
    chat_cfg = settings.get(chat_key, {})
    for k, v in kwargs.items():
        if v is not None:
            chat_cfg[k] = v
    settings[chat_key] = chat_cfg
    save_json_file(CUSTOM_SETTINGS_FILE, settings)
    return QualityCriteria(**chat_cfg) if chat_cfg else QualityCriteria()


def add_subscription(
    chat_id: int, chat_type: str, title: str, topic_id: Optional[int] = None
) -> None:
    subs = load_json_file(SUBSCRIPTIONS_FILE, {})
    sub_key = f"{chat_id}_{topic_id}" if topic_id else str(chat_id)
    subs[sub_key] = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "topic_id": topic_id,
        "enabled": True,
    }
    save_json_file(SUBSCRIPTIONS_FILE, subs)


def remove_subscription(chat_id: int, topic_id: Optional[int] = None) -> bool:
    subs = load_json_file(SUBSCRIPTIONS_FILE, {})
    sub_key = f"{chat_id}_{topic_id}" if topic_id else str(chat_id)
    if sub_key in subs:
        del subs[sub_key]
        save_json_file(SUBSCRIPTIONS_FILE, subs)
        return True
    chat_key = str(chat_id)
    if chat_key in subs:
        del subs[chat_key]
        save_json_file(SUBSCRIPTIONS_FILE, subs)
        return True
    return False


async def safe_reply(
    bot: AsyncTeleBot,
    message: Message,
    text: str,
    parse_mode: str = "HTML",
    message_thread_id: Optional[int] = None,
) -> Optional[Message]:
    """Safely reply to a message, falling back to sending without reply if message is deleted/missing."""
    thread_id = message_thread_id if message_thread_id is not None else getattr(message, "message_thread_id", None)
    try:
        return await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            parse_mode=parse_mode,
            message_thread_id=thread_id,
            reply_to_message_id=message.message_id,
            allow_sending_without_reply=True,
        )
    except Exception as e:
        logger.debug(f"safe_reply with reply_to_message_id failed: {e}. Retrying without reply...")
        try:
            return await bot.send_message(
                chat_id=message.chat.id,
                text=text,
                parse_mode=parse_mode,
                message_thread_id=thread_id,
            )
        except Exception as send_err:
            logger.error(f"Failed to send message to {message.chat.id}: {send_err}")
            return None


async def safe_send_card(
    bot: AsyncTeleBot,
    chat_id: int,
    text: str,
    photo_payload: Optional[Any] = None,
    message_thread_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send photo or text deal card with robust fallbacks and allow_sending_without_reply."""
    if photo_payload:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_payload,
                caption=text,
                parse_mode="HTML",
                message_thread_id=message_thread_id,
                reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=True,
            )
            return True
        except Exception as photo_err:
            logger.debug(f"safe_send_card send_photo failed ({photo_err}), attempting without reply...")
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_payload,
                    caption=text,
                    parse_mode="HTML",
                    message_thread_id=message_thread_id,
                )
                return True
            except Exception as photo_err2:
                logger.debug(f"safe_send_card photo fallback failed ({photo_err2}), falling back to text...")

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
            message_thread_id=message_thread_id,
            reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=True,
        )
        return True
    except Exception as msg_err:
        logger.debug(f"safe_send_card send_message failed ({msg_err}), attempting without reply...")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                message_thread_id=message_thread_id,
            )
            return True
        except Exception as final_err:
            logger.error(f"safe_send_card final send_message failed: {final_err}")
            return False


def parse_deal_command_args(
    text: str,
    default_limit: int = 5,
    is_random: bool = False,
) -> tuple:
    """
    Parse command arguments for /deals or /random:
    [count] [rank_range] [price_range] [sort_order]

    Returns:
        (count, rank_range, price_range, sort_order)
    """
    import re
    parts = text.split()[1:] if text else []

    count = default_limit
    rank_range = None
    price_range = None
    sort_order = "random" if is_random else "popularity"

    SORT_KEYWORDS = {
        "cheap": "price_asc", "cheapest": "price_asc", "price_asc": "price_asc",
        "дешеві": "price_asc", "дешево": "price_asc", "дешевле": "price_asc", "min": "price_asc",
        "expensive": "price_desc", "price_desc": "price_desc", "дорогі": "price_desc", "дорого": "price_desc", "max": "price_desc",
        "discount": "discount", "disc": "discount", "%": "discount", "знижка": "discount", "знижки": "discount", "скидка": "discount",
        "rating": "rating", "score": "rating", "meta": "rating", "rawg": "rating", "рейтинг": "rating", "топ": "rating", "оцінка": "rating",
        "new": "new", "latest": "new", "recent": "new", "date": "new", "нові": "new", "новые": "new", "новинки": "new",
        "pop": "popularity", "popular": "popularity", "popularity": "popularity", "популярні": "popularity", "хіти": "popularity",
    }

    range_tokens = []

    for token in parts:
        token_clean = token.strip().lower()
        if not token_clean:
            continue

        # 1. Check sort keyword
        if token_clean in SORT_KEYWORDS:
            if not is_random:
                sort_order = SORT_KEYWORDS[token_clean]
            continue

        # 2. Check single integer for count (1 <= int <= 15)
        if token_clean.isdigit():
            val = int(token_clean)
            if 1 <= val <= 15 and count == default_limit:
                count = val
                continue
            elif val > 15:
                range_tokens.append(token_clean)
                continue

        # 3. Check range tokens like 1000-2000, 1-100, 100-500грн
        range_match = re.match(r"^[#rRpP]?(\d+)(?:[-–—:](\d+))?([a-zA-Zа-яА-Я₴$€]+)?$", token_clean)
        if range_match:
            range_tokens.append(token_clean)
            continue

    # Process range tokens
    for idx, r_tok in enumerate(range_tokens):
        has_currency = bool(re.search(r"(грн|uah|eur|€|\$|usd|p:|price:)", r_tok))
        m = re.search(r"(\d+)(?:[-–—:](\d+))?", r_tok)
        if not m:
            continue
        v1 = float(m.group(1))
        v2 = float(m.group(2)) if m.group(2) else v1
        low, high = min(v1, v2), max(v1, v2)

        if has_currency:
            price_range = (low, high)
        else:
            if rank_range is None and (idx < len(range_tokens) - 1 or low >= 500 or (low <= 100 and high >= 200 and not price_range)):
                rank_range = (int(low), int(high))
            elif rank_range is None and not price_range:
                if high >= 500 or low <= 50:
                    rank_range = (int(low), int(high))
                else:
                    if is_random:
                        rank_range = (int(low), int(high))
                    else:
                        price_range = (low, high)
            elif price_range is None:
                price_range = (low, high)

    return (count, rank_range, price_range, sort_order)


def format_search_description(count: int, rank_range: Optional[tuple], price_range: Optional[tuple], sort_order: str, is_random: bool = False) -> str:
    """Helper to format descriptive loading status message."""
    sort_labels = {
        "popularity": "за популярністю",
        "price_asc": "від найдешевших",
        "price_desc": "від найдорожчих",
        "discount": "за розміром знижки %",
        "rating": "за рейтингом якості",
        "new": "найновіші релізи",
        "random": "випадковий вибір",
    }
    label = sort_labels.get(sort_order, sort_order)
    details = []
    if rank_range:
        details.append(f"ранг #{rank_range[0]}–{rank_range[1]}")
    if price_range:
        details.append(f"ціна {price_range[0]:.0f}–{price_range[1]:.0f} грн")
    if not is_random:
        details.append(label)

    details_str = f" ({', '.join(details)})" if details else ""
    icon = "🎲" if is_random else "🔍"
    action = f"Шукаю {count} випадкові ігри" if is_random else f"Шукаю топ-{count} знижок"
    return f"{icon} <i>{action}{details_str}...</i>"


def register_eshop_handlers(
    bot: AsyncTeleBot,
    filter_engine: DealFilterEngine,
    eshop_service: EShopService,
    global_criteria: QualityCriteria,
    currency_service: Optional[CurrencyService] = None,
    wishlist_service: Optional[WishlistService] = None,
    subscription_service: Optional[SubscriptionService] = None,
) -> None:
    """Register eShop command handlers on TeleBot instance."""
    wl_service = wishlist_service or WishlistService()
    sub_service = subscription_service or SubscriptionService()

    @bot.message_handler(
        commands=["help", "start", "eshop_help", "deals_help", "menu"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/help", "/start", "/допомога", "/старт", "/хелп", "/меню", "допомога", "хелп", "меню"))),
    )
    async def cmd_eshop_help(message: Message):
        text = (
            "🎮 <b>RuTracker Bot — Меню команд</b>\n\n"
            "🔥 <b>Знижки Nintendo eShop:</b>\n"
            "• <code>/deals [N] [ранг] [ціна] [сортування]</code> — Топ знижок з гнучкими фільтрами\n"
            "  <i>Приклади:</i>\n"
            "  - <code>/deals 5</code> — топ 5 популярних знижок\n"
            "  - <code>/deals 5 cheap</code> — 5 найдешевших ігор\n"
            "  - <code>/deals 5 discount</code> — 5 ігор з найбільшим % знижки\n"
            "  - <code>/deals 4 1-100 100-500</code> — 4 гри з топ 1-100 за ціною 100-500 грн\n\n"
            "🎲 <b>Рандомна гра зі знижкою (Рулетка):</b>\n"
            "• <code>/random [N] [ранг] [ціна]</code> — Випадкові ігри зі знижкою\n"
            "  <i>Приклади:</i>\n"
            "  - <code>/random</code> — 1 випадкова гра зі знижкою\n"
            "  - <code>/random 4 1000-2000</code> — 4 випадкові гри з рангу 1000–2000\n"
            "  - <code>/random 3 1-500 100-300</code> — 3 випадкові гри з топ-500 за 100–300 грн\n\n"
            "🔍 <b>Пошук конкретної гри:</b>\n"
            "• <code>/search &lt;назва&gt;</code> — Пошук гри та порівняння цін (наприклад: <code>/search Zelda</code>)\n\n"
            "🎁 <b>Список бажань (Wishlist):</b>\n"
            "• <code>/wishlist</code> — Переглянути свій Wishlist та актуальні ціни/знижки\n"
            "• <code>/wishlist add &lt;назва&gt;</code> — Додати гру до списку бажань\n"
            "• <code>/wishlist remove &lt;назва&gt;</code> — Видалити гру зі списку\n"
            "• <code>/wishlist clear</code> — Очистити список бажань\n\n"
            "🔔 <b>Автоматичні підписки (в приватних або групах):</b>\n"
            "• <code>/subscriptions</code> або <code>/settings</code> — Переглянути статус своїх підписок\n"
            "• <code>/sub &lt;deals | rutracker | digests | all&gt;</code> — Увімкнути авто-розсилку\n"
            "• <code>/unsub &lt;deals | rutracker | digests | all&gt;</code> — Вимкнути авто-розсилку\n\n"
            "⚙️ <b>Керування вітриною та фільтрами:</b>\n"
            "• <code>/showcase</code> або <code>/вітрина</code> — Список усіх активних ігор у вітрині\n"
            "• <code>/remove [N | all | назва]</code> — Видалити повідомлення вітрини в топіку знижок\n"
            "• <code>/deals_settings</code> — Переглянути активні фільтри якості\n"
            "• <code>/set_min_discount &lt;%&gt;</code> — Встановити мін. % знижки (наприклад: <code>/set_min_discount 40</code>)\n"
        )
        await safe_reply(bot, message, text)

    @bot.message_handler(
        commands=["deals", "eshop_deals", "top_deals", "знижки", "знижка"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/deals", "/eshop_deals", "/top_deals", "/знижки", "/знижка"))),
    )
    async def cmd_deals(message: Message):
        count, rank_range, price_range, sort_order = parse_deal_command_args(
            message.text or "", default_limit=5, is_random=False
        )

        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id
        loading_text = format_search_description(count, rank_range, price_range, sort_order, is_random=False)
        loading_msg = await safe_reply(bot, message, loading_text)

        try:
            criteria = get_chat_criteria(message.chat.id, global_criteria)
            if hasattr(currency_service, "refresh_rates"):
                await currency_service.refresh_rates()

            candidates = await filter_engine.get_flexible_deals(
                limit=count,
                rank_range=rank_range,
                price_range_uah=price_range,
                sort_by=sort_order,
                is_random=False,
                criteria=criteria,
                currency_service=currency_service,
            )

            if not candidates:
                err_text = "😔 Не знайдено знижок за вказаними фільтрами.\nСпробуйте змінити діапазон цін чи рангу або знизити поріг знижки: <code>/set_min_discount 20</code>"
                if loading_msg:
                    try:
                        await bot.edit_message_text(err_text, chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")
                        return
                    except Exception:
                        pass
                await safe_reply(bot, message, err_text)
                return

            is_first = True
            for deal in candidates:
                enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                card_text = format_eshop_deal_message(enriched, language="UA", currency_service=currency_service)
                badged_img = await download_and_badge_cover(enriched)
                photo_payload = badged_img.getvalue() if badged_img else (enriched.banner_url or enriched.image_url)

                if is_first and loading_msg:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
                    except Exception:
                        pass
                    is_first = False

                await safe_send_card(
                    bot=bot,
                    chat_id=message.chat.id,
                    text=card_text,
                    photo_payload=photo_payload,
                    message_thread_id=thread_id,
                    reply_to_message_id=reply_id,
                )
                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Error handling /deals: {e}")
            await safe_reply(bot, message, "❌ Помилка при отриманні знижок.")

    @bot.message_handler(
        commands=["random", "random_deal", "рандом", "рулетка", "випадкова_гра", "випадкова"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/random", "/random_deal", "/рандом", "/рулетка", "/випадкова_гра", "/випадкова"))),
    )
    async def cmd_random(message: Message):
        count, rank_range, price_range, sort_order = parse_deal_command_args(
            message.text or "", default_limit=1, is_random=True
        )

        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id
        loading_text = format_search_description(count, rank_range, price_range, sort_order, is_random=True)
        loading_msg = await safe_reply(bot, message, loading_text)

        try:
            criteria = get_chat_criteria(message.chat.id, global_criteria)
            if hasattr(currency_service, "refresh_rates"):
                await currency_service.refresh_rates()

            candidates = await filter_engine.get_flexible_deals(
                limit=count,
                rank_range=rank_range,
                price_range_uah=price_range,
                sort_by="random",
                is_random=True,
                criteria=criteria,
                currency_service=currency_service,
            )

            if not candidates:
                err_text = "😔 Не знайдено випадкових ігор за вказаними фільтрами.\nСпробуйте розширити діапазон цін чи рангу: <code>/random 3 1-1000</code>"
                if loading_msg:
                    try:
                        await bot.edit_message_text(err_text, chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")
                        return
                    except Exception:
                        pass
                await safe_reply(bot, message, err_text)
                return

            is_first = True
            for deal in candidates:
                enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                card_text = format_eshop_deal_message(enriched, language="UA", currency_service=currency_service)
                badged_img = await download_and_badge_cover(enriched)
                photo_payload = badged_img.getvalue() if badged_img else (enriched.banner_url or enriched.image_url)

                if is_first and loading_msg:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
                    except Exception:
                        pass
                    is_first = False

                await safe_send_card(
                    bot=bot,
                    chat_id=message.chat.id,
                    text=card_text,
                    photo_payload=photo_payload,
                    message_thread_id=thread_id,
                    reply_to_message_id=reply_id,
                )
                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Error handling /random: {e}")
            await safe_reply(bot, message, "❌ Помилка при виборі випадкової гри.")

    @bot.message_handler(
        commands=["search", "eshop_search", "find", "game", "пошук", "знайти", "гра"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/search", "/eshop_search", "/find", "/game", "/пошук", "/знайти", "/гра"))),
    )
    async def cmd_search(message: Message):
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2 or not parts[1].strip():
            await safe_reply(bot, message, "ℹ️ Вкажіть назву гри, наприклад: <code>/search Mario Odyssey</code>")
            return

        query = parts[1].strip()
        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id
        loading_msg = await safe_reply(bot, message, f"🔍 <i>Шукаю '{query}' в Nintendo eShop...</i>")

        try:
            results = await eshop_service.search_games(query=query, rows=3)
            if not results:
                if loading_msg:
                    try:
                        await bot.edit_message_text(
                            f"❌ Нічого не знайдено за запитом '{query}'.",
                            chat_id=message.chat.id,
                            message_id=loading_msg.message_id,
                        )
                        return
                    except Exception:
                        pass
                await safe_reply(bot, message, f"❌ Нічого не знайдено за запитом '{query}'.")
                return

            if hasattr(currency_service, "refresh_rates"):
                await currency_service.refresh_rates()

            is_first = True
            for deal in results:
                enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                card_text = format_eshop_deal_message(enriched, language="UA", currency_service=currency_service)
                badged_img = await download_and_badge_cover(enriched)
                photo_payload = badged_img.getvalue() if badged_img else (enriched.banner_url or enriched.image_url)

                if is_first and loading_msg:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
                    except Exception:
                        pass
                    is_first = False

                await safe_send_card(
                    bot=bot,
                    chat_id=message.chat.id,
                    text=card_text,
                    photo_payload=photo_payload,
                    message_thread_id=thread_id,
                    reply_to_message_id=reply_id,
                )
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Search error: {e}")
            await safe_reply(bot, message, "❌ Помилка під час пошуку.")

    @bot.message_handler(commands=["subscribe_deals"])
    async def cmd_subscribe(message: Message):
        chat_title = message.chat.title or message.chat.username or f"Chat_{message.chat.id}"
        topic_id = getattr(message, "message_thread_id", None)
        add_subscription(message.chat.id, message.chat.type, chat_title, topic_id=topic_id)
        await safe_reply(
            bot,
            message,
            "✅ <b>Цей чат/гілку підписано на автоматичну розсилку знижок Nintendo eShop!</b>\n"
            "Коли з'являтимуться нові хіти зі знижками, бот надішле їх у цю тему/чат.",
        )

    @bot.message_handler(commands=["unsubscribe_deals"])
    async def cmd_unsubscribe(message: Message):
        topic_id = getattr(message, "message_thread_id", None)
        if remove_subscription(message.chat.id, topic_id=topic_id):
            await safe_reply(bot, message, "🛑 <b>Відписано від розсилки знижок eShop.</b>")
        else:
            await safe_reply(bot, message, "ℹ️ Цей чат не був підписаний на розсилку.")

    @bot.message_handler(commands=["deals_settings"])
    async def cmd_settings(message: Message):
        crit = get_chat_criteria(message.chat.id, global_criteria)
        text = (
            f"⚙️ <b>Поточні фільтри якості eShop для цього чату:</b>\n\n"
            f"📉 <b>Мін. знижка:</b> {crit.min_discount_percent:.0f}%\n"
            f"⭐ <b>Мін. бал Metacritic:</b> {crit.min_metacritic_score}/100\n"
            f"🌟 <b>Мін. рейтинг RAWG:</b> {crit.min_rawg_rating:.1f}/5.0\n\n"
            f"<i>Щоб змінити:</i>\n"
            f"• <code>/set_min_discount 40</code>\n"
            f"• <code>/set_min_rating 75</code>\n"
        )
        await safe_reply(bot, message, text)

    @bot.message_handler(commands=["set_min_discount"])
    async def cmd_set_discount(message: Message):
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].replace(".", "", 1).isdigit():
            await safe_reply(bot, message, "Вкажіть число, наприклад: <code>/set_min_discount 40</code>")
            return
        val = float(parts[1])
        update_chat_criteria(message.chat.id, min_discount_percent=val)
        await safe_reply(bot, message, f"✅ Мінімальну знижку встановлено на <b>{val:.0f}%</b>")

    @bot.message_handler(commands=["set_min_rating"])
    async def cmd_set_rating(message: Message):
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await safe_reply(bot, message, "Вкажіть число від 0 до 100, наприклад: <code>/set_min_rating 75</code>")
            return
        val = int(parts[1])
        update_chat_criteria(message.chat.id, min_metacritic_score=val)
        await safe_reply(bot, message, f"✅ Мінімальний рейтинг Metacritic встановлено на <b>{val}/100</b>")

    @bot.message_handler(
        commands=["wishlist", "wl", "вішліст", "бажане"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/wishlist", "/wl", "/вішліст", "/бажане"))),
    )
    async def cmd_wishlist(message: Message):
        thread_id = getattr(message, "message_thread_id", None)
        parts = message.text.split(maxsplit=2) if message.text else []
        subcmd = parts[1].lower() if len(parts) > 1 else "list"
        query = parts[2].strip() if len(parts) > 2 else ""

        # --- Subcommand: ADD ---
        if subcmd in ["add", "+"]:
            if not query:
                await safe_reply(
                    bot,
                    message,
                    "ℹ️ Вкажіть назву гри, наприклад: <code>/wishlist add Hollow Knight</code>",
                )
                return

            loading = await safe_reply(
                bot,
                message,
                f"🔍 <i>Шукаю '{query}' для додавання до списку бажань...</i>",
            )
            try:
                results = await eshop_service.search_games(query=query, rows=1)
                if results:
                    deal = results[0]
                    wl_service.add_game(
                        message.chat.id,
                        title=deal.title,
                        nsuid=deal.nsuid,
                        fs_id=deal.fs_id,
                        topic_id=thread_id,
                    )
                    status_text = (
                        f"🔥 <b>Зараз зі знижкою:</b> <s>{deal.regular_price:.2f} {deal.currency}</s> ➡️ "
                        f"<b>{deal.discount_price:.2f} {deal.currency} (-{deal.discount_percent:.0f}%)</b>"
                        if deal.discount_percent > 0
                        else f"💵 Поточна ціна: <b>{deal.regular_price:.2f} {deal.currency}</b> (без знижки)"
                    )
                    resp_text = (
                        f"✅ Гру <b>{deal.title}</b> успішно додано до вашого Wishlist!\n\n{status_text}\n\n"
                        "<i>Бот автоматично сповістить вас, щойно з'явиться знижка!</i>"
                    )
                    if loading:
                        try:
                            await bot.edit_message_text(resp_text, chat_id=message.chat.id, message_id=loading.message_id, parse_mode="HTML")
                            return
                        except Exception:
                            pass
                    await safe_reply(bot, message, resp_text)
                else:
                    wl_service.add_game(message.chat.id, title=query, topic_id=thread_id)
                    resp_text = f"✅ Гру <b>{query}</b> додано до Wishlist!\n<i>Бот автоматично сповістить вас про знижки.</i>"
                    if loading:
                        try:
                            await bot.edit_message_text(resp_text, chat_id=message.chat.id, message_id=loading.message_id, parse_mode="HTML")
                            return
                        except Exception:
                            pass
                    await safe_reply(bot, message, resp_text)
            except Exception as err:
                logger.error(f"Wishlist add error: {err}")
                wl_service.add_game(message.chat.id, title=query, topic_id=thread_id)
                resp_text = f"✅ Гру <b>{query}</b> додано до Wishlist!"
                if loading:
                    try:
                        await bot.edit_message_text(resp_text, chat_id=message.chat.id, message_id=loading.message_id, parse_mode="HTML")
                        return
                    except Exception:
                        pass
                await safe_reply(bot, message, resp_text)
            return

        # --- Subcommand: REMOVE / DEL ---
        if subcmd in ["remove", "del", "delete", "-"]:
            if not query:
                await safe_reply(
                    bot,
                    message,
                    "ℹ️ Вкажіть назву гри для видалення, наприклад: <code>/wishlist remove Hollow Knight</code>",
                )
                return

            if wl_service.remove_game(message.chat.id, title=query, topic_id=thread_id):
                await safe_reply(bot, message, f"🗑 Гру <b>{query}</b> видалено з вашого Wishlist.")
            else:
                await safe_reply(bot, message, f"ℹ️ Гру '{query}' не знайдено у вашому Wishlist.")
            return

        # --- Subcommand: CLEAR ---
        if subcmd == "clear":
            wl_service.clear_wishlist(message.chat.id, topic_id=thread_id)
            await safe_reply(bot, message, "🧹 <b>Ваш Wishlist повністю очищено.</b>")
            return

        # --- Subcommand: LIST (Default) ---
        items = wl_service.get_wishlist(message.chat.id, topic_id=thread_id)
        if not items:
            await safe_reply(
                bot,
                message,
                "🎁 <b>Ваш Wishlist порожній.</b>\n\n"
                "Щоб додати гру та отримувати сповіщення про знижки:\n"
                "• <code>/wishlist add &lt;назва гри&gt;</code>\n"
                "<i>Наприклад: <code>/wishlist add Hollow Knight</code> або <code>/wishlist add Persona 5</code></i>",
            )
            return

        loading = await safe_reply(bot, message, "🔍 <i>Перевіряю актуальні ціни та знижки для ігор із вашого Wishlist...</i>")

        lines = ["🎁 <b>Ваш список бажань (Wishlist):</b>\n"]
        for idx, it in enumerate(items, 1):
            title = it.get("title", "Unknown")
            try:
                found = await eshop_service.search_games(query=title, rows=1)
                if found:
                    deal = found[0]
                    if deal.discount_percent > 0:
                        uah_conv = f" (~{currency_service.convert_to_uah(deal.discount_price, deal.currency):.0f} грн)" if currency_service else ""
                        lines.append(
                            f"{idx}. 🔥 <b>{deal.title}</b> — <s>{deal.regular_price:.2f}</s> ➡️ "
                            f"<b>{deal.discount_price:.2f} {deal.currency} (-{deal.discount_percent:.0f}%)</b>{uah_conv}"
                        )
                    else:
                        lines.append(f"{idx}. <b>{deal.title}</b> — {deal.regular_price:.2f} {deal.currency} <i>(без знижки)</i>")
                else:
                    lines.append(f"{idx}. <b>{title}</b>")
            except Exception:
                lines.append(f"{idx}. <b>{title}</b>")

        lines.append("\n<i>Керування: <code>/wishlist add &lt;гра&gt;</code> | <code>/wishlist remove &lt;гра&gt;</code></i>")
        summary_text = "\n".join(lines)
        if loading:
            try:
                await bot.edit_message_text(
                    summary_text,
                    chat_id=message.chat.id,
                    message_id=loading.message_id,
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
        await safe_reply(bot, message, summary_text)

    @bot.message_handler(
        commands=["subscriptions", "settings", "notify", "sub_status", "підписки", "налаштування"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/subscriptions", "/settings", "/notify", "/sub_status", "/підписки", "/налаштування"))),
    )
    async def cmd_subscriptions(message: Message):
        thread_id = getattr(message, "message_thread_id", None)
        subs = sub_service.get_subscriptions(message.chat.id, topic_id=thread_id)

        deals_status = "✅ <b>Увімкнено</b>" if subs.get("deals") else "❌ <b>Вимкнено</b>"
        rutracker_status = "✅ <b>Увімкнено</b>" if subs.get("rutracker") else "❌ <b>Вимкнено</b>"
        digests_status = "✅ <b>Увімкнено</b>" if subs.get("digests") else "❌ <b>Вимкнено</b>"

        text = (
            "⚙️ <b>Налаштування автоматичних сповіщень:</b>\n\n"
            "<i>За замовченням усі автоматичні повідомлення у приватних вимкнено.\n"
            "Бот пише лише тоді, коли ви самі звертаєтесь до нього командами.</i>\n\n"
            "<b>Ваші поточні підписки:</b>\n"
            f"• 🎮 <b>Знижки Nintendo eShop:</b> {deals_status}\n"
            f"• 📥 <b>Нові роздачі RuTracker:</b> {rutracker_status}\n"
            f"• 📰 <b>Щоденні дайджести (релізи, homebrew, swuk):</b> {digests_status}\n\n"
            "<b>Як увімкнути/вимкнути:</b>\n"
            "• <code>/sub deals</code> / <code>/unsub deals</code> — знижки eShop\n"
            "• <code>/sub rutracker</code> / <code>/unsub rutracker</code> — репост роздач з трекера\n"
            "• <code>/sub digests</code> / <code>/unsub digests</code> — щоденні дайджести\n"
            "• <code>/sub all</code> / <code>/unsub all</code> — увімкнути/вимкнути все\n\n"
            "ℹ️ <i>Команди (/deals, /search, /wishlist) завжди доступні вручну незалежно від підписок.</i>"
        )
        await safe_reply(bot, message, text)

    @bot.message_handler(
        commands=["sub", "subscribe", "підписатися", "підписка"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/sub", "/subscribe", "/підписатися", "/підписка"))),
    )
    async def cmd_sub(message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            await safe_reply(
                bot,
                message,
                "ℹ️ Вкажіть категорію для підписки:\n"
                "• <code>/sub deals</code> — знижки Nintendo eShop\n"
                "• <code>/sub rutracker</code> — репост роздач RuTracker\n"
                "• <code>/sub digests</code> — щоденні дайджести\n"
                "• <code>/sub all</code> — увімкнути все",
            )
            return

        category = parts[1].lower().strip()
        chat_title = message.chat.title or message.chat.username or f"User_{message.chat.id}"
        thread_id = getattr(message, "message_thread_id", None)
        try:
            sub_service.set_subscription(
                chat_id=message.chat.id,
                sub_type=category,
                enabled=True,
                chat_type=message.chat.type,
                title=chat_title,
                topic_id=thread_id,
            )
            cat_names = {
                "deals": "🎮 Знижки Nintendo eShop",
                "rutracker": "📥 Нові роздачі RuTracker",
                "digests": "📰 Щоденні дайджести",
                "all": "Всі категорії",
            }
            cat_label = cat_names.get(category, category)
            await safe_reply(
                bot,
                message,
                f"✅ <b>Підписку на '{cat_label}' успішно увімкнено!</b>\n\n"
                "Перевірити статус усіх підписок: <code>/subscriptions</code>",
            )
        except ValueError:
            await safe_reply(
                bot,
                message,
                "❌ Невідома категорія. Доступні: <code>deals</code>, <code>rutracker</code>, <code>digests</code>, <code>all</code>",
            )

    @bot.message_handler(
        commands=["unsub", "unsubscribe", "відписатися", "відписка"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/unsub", "/unsubscribe", "/відписатися", "/відписка"))),
    )
    async def cmd_unsub(message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            await safe_reply(
                bot,
                message,
                "ℹ️ Вкажіть категорію для відписки:\n"
                "• <code>/unsub deals</code> — знижки Nintendo eShop\n"
                "• <code>/unsub rutracker</code> — репост роздач RuTracker\n"
                "• <code>/unsub digests</code> — щоденні дайджести\n"
                "• <code>/unsub all</code> — вимкнути все",
            )
            return

        category = parts[1].lower().strip()
        chat_title = message.chat.title or message.chat.username or f"User_{message.chat.id}"
        thread_id = getattr(message, "message_thread_id", None)
        try:
            sub_service.set_subscription(
                chat_id=message.chat.id,
                sub_type=category,
                enabled=False,
                chat_type=message.chat.type,
                title=chat_title,
                topic_id=thread_id,
            )
            cat_names = {
                "deals": "🎮 Знижки Nintendo eShop",
                "rutracker": "📥 Нові роздачі RuTracker",
                "digests": "📰 Щоденні дайджести",
                "all": "Всі категорії",
            }
            cat_label = cat_names.get(category, category)
            await safe_reply(
                bot,
                message,
                f"🛑 <b>Підписку на '{cat_label}' вимкнено.</b>\n\n"
                "Перевірити статус усіх підписок: <code>/subscriptions</code>",
            )
        except ValueError:
            await safe_reply(
                bot,
                message,
                "❌ Невідома категорія. Доступні: <code>deals</code>, <code>rutracker</code>, <code>digests</code>, <code>all</code>",
            )

    @bot.message_handler(
        commands=["showcase", "deals_list", "list_deals", "showcase_list", "вітрина", "список"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/showcase", "/deals_list", "/list_deals", "/вітрина", "/список", "вітрина", "список"))),
    )
    async def cmd_list_showcase(message: Message):
        """Display the complete list of active games currently in the showcase database."""
        thread_id = getattr(message, "message_thread_id", None)
        from send_eshop_deals import load_active_showcase

        showcase_key = f"{message.chat.id}_{thread_id}" if thread_id else str(message.chat.id)
        showcase_data = load_active_showcase()
        items = showcase_data.get(showcase_key, [])
        if not items:
            for k, it_list in showcase_data.items():
                if str(message.chat.id) in k and it_list:
                    showcase_key = k
                    items = it_list
                    break

        if not items:
            await safe_reply(
                bot,
                message,
                "ℹ️ <b>У базі даних вітрини зараз 0 активних ігор.</b>\n\n"
                "Щоб заповнити вітрину 30 актуальними хітами прямо зараз, запустіть на сервері:\n"
                "<code>python send_eshop_deals.py --force</code>",
            )
            return

        lines = [f"🎮 <b>Активна вітрина знижок у топіку ({len(items)}/30):</b>\n"]
        for idx, it in enumerate(items, 1):
            title = it.get("title", "Unknown")
            disc = it.get("discount_percent", 0)
            price = it.get("discount_price", 0)
            curr = it.get("currency", "EUR")
            lines.append(f"{idx}. <b>{title}</b> — {price} {curr} (<b>-{disc:.0f}%</b>)")

        text = "\n".join(lines)
        await safe_reply(bot, message, text)

    @bot.message_handler(
        commands=["remove_deals", "remove", "clean_deals", "clear_deals", "видалити", "очистити"],
        func=lambda m: bool(m.text and m.text.lower().startswith(("/remove", "/clean_deals", "/clear_deals", "/видалити", "/очистити"))),
    )
    async def cmd_remove_deals(message: Message):
        """Remove specified number of deals, specific game by title, or all from current chat/topic showcase."""
        parts = message.text.split(maxsplit=1)
        target_arg = parts[1].strip().lower() if len(parts) > 1 else "all"

        remove_all = target_arg == "all"
        is_title_search = not remove_all and not target_arg.isdigit()

        thread_id = getattr(message, "message_thread_id", None)
        from send_eshop_deals import load_active_showcase, save_active_showcase, safe_delete_showcase_message, IS_TEST_MODE

        # Strictly only allow in dedicated topic 561344 of chat -1001790782971
        is_authorized = (
            bool(IS_TEST_MODE)
            or (str(message.chat.id) == "-1001790782971" and str(thread_id) == "561344")
        )
        if not is_authorized:
            await safe_reply(
                bot,
                message,
                "⚠️ Видалення повідомлень вітрини дозволено виключно в призначеному топіку eShop (561344):\n"
                "https://t.me/kefir_ukr/561344",
            )
            return

        # 1. Direct deletion if user replies to any bot message with /remove
        if message.reply_to_message:
            target_msg = message.reply_to_message
            deleted = await safe_delete_showcase_message(
                chat_id=message.chat.id,
                topic_id=thread_id,
                message_id=target_msg.message_id,
                title="replied_message",
            )
            # Delete user command message itself
            await safe_delete_showcase_message(
                chat_id=message.chat.id,
                topic_id=thread_id,
                message_id=message.message_id,
                title="user_command",
            )
            # Purge from showcase database if present
            showcase_data = load_active_showcase()
            for k, it_list in showcase_data.items():
                if str(message.chat.id) in k:
                    showcase_data[k] = [it for it in it_list if it.get("message_id") != target_msg.message_id]
            save_active_showcase(showcase_data)
            return

        # 2. Retrieve items across all matching chat showcase keys
        showcase_key = f"{message.chat.id}_{thread_id}" if thread_id else str(message.chat.id)
        showcase_data = load_active_showcase()
        items = showcase_data.get(showcase_key, [])
        if not items:
            for k, it_list in showcase_data.items():
                if str(message.chat.id) in k and it_list:
                    showcase_key = k
                    items = it_list
                    break

        if not items:
            await safe_reply(
                bot,
                message,
                "ℹ️ <b>У топіку наразі 0 активних повідомлень вітрини в базі даних.</b>\n"
                "<i>Підказка: щоб видалити будь-яке конкретне повідомлення, просто відповідайте на нього командою <code>/remove</code> (або видаліть вручну в Telegram).</i>",
            )
            return

        if is_title_search:
            target_title_norm = target_arg.lower()
            to_delete = [
                it for it in items
                if target_title_norm in it.get("title", "").lower() or _is_title_match(target_title_norm, it.get("title", ""))
            ]
            surviving = [it for it in items if it not in to_delete]
            if not to_delete:
                await safe_reply(
                    bot,
                    message,
                    f"ℹ️ Гру '<b>{parts[1]}</b>' не знайдено серед активних повідомлень вітрини.\n"
                    f"<i>Підказка: дайте відповідь (reply) на повідомлення з цією грою командою <code>/remove</code>.</i>",
                )
                return
        elif remove_all:
            to_delete = items[:]
            surviving = []
        else:
            try:
                remove_count = max(1, int(target_arg))
                to_delete = items[:remove_count]
                surviving = items[remove_count:]
            except ValueError:
                await safe_reply(
                    bot,
                    message,
                    "ℹ️ Вкажіть назву гри, кількість повідомлень або <code>all</code>:\n"
                    "• <code>/remove Hogwarts Legacy</code> — видалити конкретну гру\n"
                    "• <code>/remove 20</code> — видалити 20 повідомлень\n"
                    "• <code>/remove all</code> — видалити всі повідомлення\n"
                    "• або просто надішліть <code>/remove</code> у відповідь (reply) на картку гри",
                )
                return

        deleted_msg_ids = set()
        deleted_count = 0

        # Delete user command message itself
        try:
            await safe_delete_showcase_message(
                chat_id=message.chat.id,
                topic_id=thread_id,
                message_id=message.message_id,
                title="user_command",
            )
            deleted_msg_ids.add(message.message_id)
        except Exception:
            pass

        for it in to_delete:
            msg_id = it.get("message_id")
            title = it.get("title", "")
            if msg_id and msg_id not in deleted_msg_ids:
                deleted = await safe_delete_showcase_message(
                    chat_id=message.chat.id,
                    topic_id=thread_id,
                    message_id=int(msg_id),
                    title=title,
                )
                if deleted:
                    deleted_count += 1
                    deleted_msg_ids.add(msg_id)
                await asyncio.sleep(0.08)

        # Clear/update showcase state and release cooldown history for deleted games
        showcase_data[showcase_key] = surviving
        save_active_showcase(showcase_data)

        from send_eshop_deals import load_posted_deals, save_posted_deals, _normalize_title_key
        posted_history = load_posted_deals()
        for it in to_delete:
            fs_id = it.get("fs_id")
            title = it.get("title")
            if fs_id and str(fs_id) in posted_history:
                posted_history.pop(str(fs_id), None)
            norm = _normalize_title_key(title)
            if norm and f"title_{norm}" in posted_history:
                posted_history.pop(f"title_{norm}", None)
        save_posted_deals(posted_history)

        # Send temporary confirmation
        try:
            status_msg = f"🗑 <b>Успішно видалено {deleted_count} повідомлень вітрини.</b>"
            conf = await bot.send_message(
                chat_id=message.chat.id,
                text=status_msg,
                message_thread_id=thread_id,
                parse_mode="HTML",
            )
            await asyncio.sleep(4.0)
            await bot.delete_message(chat_id=message.chat.id, message_id=conf.message_id)
        except Exception:
            pass



