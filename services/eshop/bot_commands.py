"""Interactive Telegram command handlers for eShop Deals in RuTracker Bot."""

import json
import logging
import os
from typing import Dict, List, Optional
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


def register_eshop_handlers(
    bot: AsyncTeleBot,
    filter_engine: DealFilterEngine,
    eshop_service: EShopService,
    global_criteria: QualityCriteria,
    currency_service: Optional[CurrencyService] = None,
    wishlist_service: Optional[WishlistService] = None,
) -> None:
    """Register eShop command handlers on TeleBot instance."""
    wl_service = wishlist_service or WishlistService()

    @bot.message_handler(commands=["help", "start", "eshop_help", "deals_help"])
    async def cmd_eshop_help(message: Message):
        text = (
            "🎮 <b>Nintendo eShop Deals & Wishlist Commands</b>\n\n"
            "• <code>/deals [N]</code> — Показати топ N знижок з порівнянням цін у регіонах (наприклад: <code>/deals 5</code>)\n"
            "• <code>/search &lt;назва&gt;</code> — Пошук гри та порівняння цін (наприклад: <code>/search Zelda</code>)\n\n"
            "🎁 <b>Список бажань (Wishlist):</b>\n"
            "• <code>/wishlist</code> — Переглянути свій Wishlist та актуальні ціни/знижки\n"
            "• <code>/wishlist add &lt;назва&gt;</code> — Додати гру до списку бажань (наприклад: <code>/wishlist add Hollow Knight</code>)\n"
            "• <code>/wishlist remove &lt;назва&gt;</code> — Видалити гру зі списку\n"
            "• <code>/wishlist clear</code> — Очистити список бажань\n\n"
            "⚙️ <b>Налаштування та підписка:</b>\n"
            "• <code>/subscribe_deals</code> — Підписати цей чат/канал/гілку на автоматичну розсилку знижок\n"
            "• <code>/unsubscribe_deals</code> — Відписати чат від розсилки\n"
            "• <code>/deals_settings</code> — Переглянути активні фільтри якості\n"
            "• <code>/set_min_discount &lt;%&gt;</code> — Встановити мін. % знижки (наприклад: <code>/set_min_discount 40</code>)\n"
            "• <code>/set_min_rating &lt;бал&gt;</code> — Встановити мін. бал Metacritic (наприклад: <code>/set_min_rating 75</code>)\n"
        )
        await bot.reply_to(message, text, parse_mode="HTML")

    @bot.message_handler(commands=["deals", "eshop_deals"])
    async def cmd_deals(message: Message):
        args = message.text.split()[1:] if message.text else []
        limit = 5
        if args and args[0].isdigit():
            limit = max(1, min(10, int(args[0])))

        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id

        loading_msg = await bot.reply_to(
            message,
            f"🔍 <i>Шукаю топ-{limit} знижок серед найпопулярніших хітів Nintendo Switch...</i>",
            parse_mode="HTML",
        )
        try:
            criteria = get_chat_criteria(message.chat.id, global_criteria)
            candidates = await filter_engine.get_candidate_deals(criteria=criteria, limit=limit)

            if not candidates:
                await bot.edit_message_text(
                    "😔 Не знайдено знижок на популярні ігри за поточними критеріями.\n"
                    "Спробуйте знизити поріг: <code>/set_min_discount 20</code>",
                    chat_id=message.chat.id,
                    message_id=loading_msg.message_id,
                    parse_mode="HTML",
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

                if is_first:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
                    except Exception:
                        pass
                    is_first = False

                sent = False
                if photo_payload:
                    try:
                        await bot.send_photo(
                            chat_id=message.chat.id,
                            photo=photo_payload,
                            caption=card_text,
                            parse_mode="HTML",
                            message_thread_id=thread_id,
                            reply_to_message_id=reply_id,
                        )
                        sent = True
                    except Exception as err:
                        logger.debug(f"Could not send photo for '{deal.title}': {err}")

                if not sent:
                    await bot.send_message(
                        chat_id=message.chat.id,
                        text=card_text,
                        parse_mode="HTML",
                        disable_web_page_preview=False,
                        message_thread_id=thread_id,
                        reply_to_message_id=reply_id,
                    )
                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Error handling /deals: {e}")
            await bot.send_message(
                message.chat.id,
                "❌ Помилка при отриманні знижок.",
                message_thread_id=thread_id,
                reply_to_message_id=reply_id,
            )

    @bot.message_handler(commands=["search", "eshop_search"])
    async def cmd_search(message: Message):
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2 or not parts[1].strip():
            await bot.reply_to(message, "ℹ️ Вкажіть назву гри, наприклад: <code>/search Mario Odyssey</code>", parse_mode="HTML")
            return

        query = parts[1].strip()
        thread_id = getattr(message, "message_thread_id", None)
        reply_id = message.message_id
        loading_msg = await bot.reply_to(message, f"🔍 <i>Шукаю '{query}' в Nintendo eShop...</i>", parse_mode="HTML")

        try:
            results = await eshop_service.search_games(query=query, rows=3)
            if not results:
                await bot.edit_message_text(f"❌ Нічого не знайдено за запитом '{query}'.", chat_id=message.chat.id, message_id=loading_msg.message_id)
                return

            if hasattr(currency_service, "refresh_rates"):
                await currency_service.refresh_rates()

            is_first = True
            for deal in results:
                enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                card_text = format_eshop_deal_message(enriched, language="UA", currency_service=currency_service)
                badged_img = await download_and_badge_cover(enriched)
                photo_payload = badged_img.getvalue() if badged_img else (enriched.banner_url or enriched.image_url)

                if is_first:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
                    except Exception:
                        pass
                    is_first = False

                sent = False
                if photo_payload:
                    try:
                        await bot.send_photo(
                            chat_id=message.chat.id,
                            photo=photo_payload,
                            caption=card_text,
                            parse_mode="HTML",
                            message_thread_id=thread_id,
                            reply_to_message_id=reply_id,
                        )
                        sent = True
                    except Exception as err:
                        logger.debug(f"Could not send photo for '{deal.title}': {err}")

                if not sent:
                    await bot.send_message(
                        chat_id=message.chat.id,
                        text=card_text,
                        parse_mode="HTML",
                        message_thread_id=thread_id,
                        reply_to_message_id=reply_id,
                    )
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Search error: {e}")
            await bot.send_message(
                message.chat.id,
                "❌ Помилка під час пошуку.",
                message_thread_id=thread_id,
                reply_to_message_id=reply_id,
            )

    @bot.message_handler(commands=["subscribe_deals"])
    async def cmd_subscribe(message: Message):
        chat_title = message.chat.title or message.chat.username or f"Chat_{message.chat.id}"
        topic_id = getattr(message, "message_thread_id", None)
        add_subscription(message.chat.id, message.chat.type, chat_title, topic_id=topic_id)
        await bot.reply_to(
            message,
            "✅ <b>Цей чат/гілку підписано на автоматичну розсилку знижок Nintendo eShop!</b>\n"
            "Коли з'являтимуться нові хіти зі знижками, бот надішле їх у цю тему/чат.",
            parse_mode="HTML",
        )

    @bot.message_handler(commands=["unsubscribe_deals"])
    async def cmd_unsubscribe(message: Message):
        topic_id = getattr(message, "message_thread_id", None)
        if remove_subscription(message.chat.id, topic_id=topic_id):
            await bot.reply_to(message, "🛑 <b>Відписано від розсилки знижок eShop.</b>", parse_mode="HTML")
        else:
            await bot.reply_to(message, "ℹ️ Цей чат не був підписаний на розсилку.", parse_mode="HTML")

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
        await bot.reply_to(message, text, parse_mode="HTML")

    @bot.message_handler(commands=["set_min_discount"])
    async def cmd_set_discount(message: Message):
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].replace(".", "", 1).isdigit():
            await bot.reply_to(message, "Вкажіть число, наприклад: <code>/set_min_discount 40</code>", parse_mode="HTML")
            return
        val = float(parts[1])
        update_chat_criteria(message.chat.id, min_discount_percent=val)
        await bot.reply_to(message, f"✅ Мінімальну знижку встановлено на <b>{val:.0f}%</b>", parse_mode="HTML")

    @bot.message_handler(commands=["set_min_rating"])
    async def cmd_set_rating(message: Message):
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await bot.reply_to(message, "Вкажіть число від 0 до 100, наприклад: <code>/set_min_rating 75</code>", parse_mode="HTML")
            return
        val = int(parts[1])
        update_chat_criteria(message.chat.id, min_metacritic_score=val)
        await bot.reply_to(message, f"✅ Мінімальний рейтинг Metacritic встановлено на <b>{val}/100</b>", parse_mode="HTML")

    @bot.message_handler(commands=["wishlist"])
    async def cmd_wishlist(message: Message):
        thread_id = getattr(message, "message_thread_id", None)
        parts = message.text.split(maxsplit=2) if message.text else []
        subcmd = parts[1].lower() if len(parts) > 1 else "list"
        query = parts[2].strip() if len(parts) > 2 else ""

        # --- Subcommand: ADD ---
        if subcmd in ["add", "+"]:
            if not query:
                await bot.reply_to(
                    message,
                    "ℹ️ Вкажіть назву гри, наприклад: <code>/wishlist add Hollow Knight</code>",
                    parse_mode="HTML",
                    message_thread_id=thread_id,
                )
                return

            loading = await bot.reply_to(
                message,
                f"🔍 <i>Шукаю '{query}' для додавання до списку бажань...</i>",
                parse_mode="HTML",
                message_thread_id=thread_id,
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
                    await bot.edit_message_text(
                        f"✅ Гру <b>{deal.title}</b> успішно додано до вашого Wishlist!\n\n{status_text}\n\n"
                        "<i>Бот автоматично сповістить вас, щойно з'явиться знижка!</i>",
                        chat_id=message.chat.id,
                        message_id=loading.message_id,
                        parse_mode="HTML",
                    )
                else:
                    wl_service.add_game(message.chat.id, title=query, topic_id=thread_id)
                    await bot.edit_message_text(
                        f"✅ Гру <b>{query}</b> додано до Wishlist!\n"
                        "<i>Бот автоматично сповістить вас про знижки.</i>",
                        chat_id=message.chat.id,
                        message_id=loading.message_id,
                        parse_mode="HTML",
                    )
            except Exception as err:
                logger.error(f"Wishlist add error: {err}")
                wl_service.add_game(message.chat.id, title=query, topic_id=thread_id)
                await bot.edit_message_text(
                    f"✅ Гру <b>{query}</b> додано до Wishlist!",
                    chat_id=message.chat.id,
                    message_id=loading.message_id,
                    parse_mode="HTML",
                )
            return

        # --- Subcommand: REMOVE / DEL ---
        if subcmd in ["remove", "del", "delete", "-"]:
            if not query:
                await bot.reply_to(
                    message,
                    "ℹ️ Вкажіть назву гри для видалення, наприклад: <code>/wishlist remove Hollow Knight</code>",
                    parse_mode="HTML",
                    message_thread_id=thread_id,
                )
                return

            if wl_service.remove_game(message.chat.id, title=query, topic_id=thread_id):
                await bot.reply_to(
                    message,
                    f"🗑 Гру <b>{query}</b> видалено з вашого Wishlist.",
                    parse_mode="HTML",
                    message_thread_id=thread_id,
                )
            else:
                await bot.reply_to(
                    message,
                    f"ℹ️ Гру '{query}' не знайдено у вашому Wishlist.",
                    parse_mode="HTML",
                    message_thread_id=thread_id,
                )
            return

        # --- Subcommand: CLEAR ---
        if subcmd == "clear":
            wl_service.clear_wishlist(message.chat.id, topic_id=thread_id)
            await bot.reply_to(
                message,
                "🧹 <b>Ваш Wishlist повністю очищено.</b>",
                parse_mode="HTML",
                message_thread_id=thread_id,
            )
            return

        # --- Subcommand: LIST (Default) ---
        items = wl_service.get_wishlist(message.chat.id, topic_id=thread_id)
        if not items:
            await bot.reply_to(
                message,
                "🎁 <b>Ваш Wishlist порожній.</b>\n\n"
                "Щоб додати гру та отримувати сповіщення про знижки:\n"
                "• <code>/wishlist add &lt;назва гри&gt;</code>\n"
                "<i>Наприклад: <code>/wishlist add Hollow Knight</code> або <code>/wishlist add Persona 5</code></i>",
                parse_mode="HTML",
                message_thread_id=thread_id,
            )
            return

        loading = await bot.reply_to(
            message,
            "🔍 <i>Перевіряю актуальні ціни та знижки для ігор із вашого Wishlist...</i>",
            parse_mode="HTML",
            message_thread_id=thread_id,
        )

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
        await bot.edit_message_text(
            "\n".join(lines),
            chat_id=message.chat.id,
            message_id=loading.message_id,
            parse_mode="HTML",
        )
