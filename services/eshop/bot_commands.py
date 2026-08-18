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
from services.eshop.region_price_service import RegionPriceService
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

    @bot.message_handler(commands=["help", "start", "eshop_help", "deals_help"])
    async def cmd_eshop_help(message: Message):
        text = (
            "🎮 <b>RuTracker Bot — Меню команд</b>\n\n"
            "🔥 <b>Знижки Nintendo eShop:</b>\n"
            "• <code>/deals [N]</code> — Показати топ N знижок з порівнянням цін у регіонах (наприклад: <code>/deals 5</code>)\n"
            "• <code>/search &lt;назва&gt;</code> — Пошук гри та порівняння цін (наприклад: <code>/search Zelda</code>)\n\n"
            "🎁 <b>Список бажань (Wishlist):</b>\n"
            "• <code>/wishlist</code> — Переглянути свій Wishlist та актуальні ціни/знижки\n"
            "• <code>/wishlist add &lt;назва&gt;</code> — Додати гру до списку бажань (наприклад: <code>/wishlist add Hollow Knight</code>)\n"
            "• <code>/wishlist remove &lt;назва&gt;</code> — Видалити гру зі списку\n"
            "• <code>/wishlist clear</code> — Очистити список бажань\n\n"
            "🔔 <b>Автоматичні підписки (в приватних або групах):</b>\n"
            "• <code>/subscriptions</code> або <code>/settings</code> — Переглянути статус своїх підписок\n"
            "• <code>/sub &lt;deals | rutracker | digests | all&gt;</code> — Увімкнути авто-розсилку\n"
            "• <code>/unsub &lt;deals | rutracker | digests | all&gt;</code> — Вимкнути авто-розсилку\n\n"
            "⚙️ <b>Фільтри якості eShop:</b>\n"
            "• <code>/deals_settings</code> — Переглянути активні фільтри якості\n"
            "• <code>/set_min_discount &lt;%&gt;</code> — Встановити мін. % знижки (наприклад: <code>/set_min_discount 40</code>)\n"
            "• <code>/set_min_rating &lt;бал&gt;</code> — Встановити мін. бал Metacritic (наприклад: <code>/set_min_rating 75</code>)\n"
        )
        await safe_reply(bot, message, text)

    @bot.message_handler(commands=["deals", "eshop_deals"])
    async def cmd_deals(message: Message):
        args = message.text.split()[1:] if message.text else []
        limit = 5
        if args and args[0].isdigit():
            limit = max(1, min(10, int(args[0])))

        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id

        loading_msg = await safe_reply(
            bot,
            message,
            f"🔍 <i>Шукаю топ-{limit} знижок серед найпопулярніших хітів Nintendo Switch...</i>",
        )
        try:
            criteria = get_chat_criteria(message.chat.id, global_criteria)
            candidates = await filter_engine.get_candidate_deals(criteria=criteria, limit=limit)

            if not candidates:
                if loading_msg:
                    try:
                        await bot.edit_message_text(
                            "😔 Не знайдено знижок на популярні ігри за поточними критеріями.\n"
                            "Спробуйте знизити поріг: <code>/set_min_discount 20</code>",
                            chat_id=message.chat.id,
                            message_id=loading_msg.message_id,
                            parse_mode="HTML",
                        )
                        return
                    except Exception:
                        pass
                await safe_reply(
                    bot,
                    message,
                    "😔 Не знайдено знижок на популярні ігри за поточними критеріями.\n"
                    "Спробуйте знизити поріг: <code>/set_min_discount 20</code>",
                )
                return

            if hasattr(currency_service, "refresh_rates"):
                await currency_service.refresh_rates()

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

    @bot.message_handler(commands=["search", "eshop_search"])
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

    @bot.message_handler(commands=["wishlist"])
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

    @bot.message_handler(commands=["subscriptions", "settings", "notify"])
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

    @bot.message_handler(commands=["sub", "subscribe"])
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

    @bot.message_handler(commands=["unsub", "unsubscribe"])
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
