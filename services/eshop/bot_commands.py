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


def add_subscription(chat_id: int, chat_type: str, title: str) -> None:
    subs = load_json_file(SUBSCRIPTIONS_FILE, {})
    subs[str(chat_id)] = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "enabled": True,
    }
    save_json_file(SUBSCRIPTIONS_FILE, subs)


def remove_subscription(chat_id: int) -> bool:
    subs = load_json_file(SUBSCRIPTIONS_FILE, {})
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
) -> None:
    """Register eShop command handlers on TeleBot instance."""

    @bot.message_handler(commands=["eshop_help", "deals_help"])
    async def cmd_eshop_help(message: Message):
        text = (
            "🎮 <b>Nintendo eShop Deals Commands</b>\n\n"
            "• <code>/deals [N]</code> — Показати топ N знижок з порівнянням цін у регіонах (наприклад: <code>/deals 5</code>)\n"
            "• <code>/search &lt;назва&gt;</code> — Пошук гри та порівняння цін (наприклад: <code>/search Zelda</code>)\n"
            "• <code>/subscribe_deals</code> — Підписати цей чат/канал на автоматичну розсилку знижок\n"
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

        loading_msg = await bot.reply_to(message, "🔍 <i>Шукаю та аналізую найкращі знижки в Nintendo eShop...</i>", parse_mode="HTML")
        try:
            criteria = get_chat_criteria(message.chat.id, global_criteria)
            deals = await filter_engine.get_best_deals(
                criteria=criteria, limit=limit, include_regional_prices=True
            )

            if not deals:
                await bot.edit_message_text(
                    "😔 Не знайдено знижок, які відповідають поточним критеріям якості.\n"
                    "Спробуйте знизити поріг: <code>/set_min_discount 20</code> або <code>/set_min_rating 60</code>.",
                    chat_id=message.chat.id,
                    message_id=loading_msg.message_id,
                    parse_mode="HTML",
                )
                return

            await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)

            for deal in deals:
                card_text = format_eshop_deal_message(deal, language="UA")
                img = deal.banner_url or deal.image_url
                if img:
                    try:
                        await bot.send_photo(
                            chat_id=message.chat.id,
                            photo=img,
                            caption=card_text,
                            parse_mode="HTML",
                        )
                        continue
                    except Exception as err:
                        logger.debug(f"Could not send photo: {err}")

                await bot.send_message(
                    chat_id=message.chat.id,
                    text=card_text,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
        except Exception as e:
            logger.error(f"Error handling /deals: {e}")
            await bot.send_message(message.chat.id, "❌ Помилка при отриманні знижок.")

    @bot.message_handler(commands=["search", "eshop_search"])
    async def cmd_search(message: Message):
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2 or not parts[1].strip():
            await bot.reply_to(message, "ℹ️ Вкажіть назву гри, наприклад: <code>/search Mario Odyssey</code>", parse_mode="HTML")
            return

        query = parts[1].strip()
        loading = await bot.reply_to(message, f"🔍 <i>Шукаю '{query}' в Nintendo eShop...</i>", parse_mode="HTML")

        try:
            results = await eshop_service.search_games(query=query, rows=3)
            if not results:
                await bot.edit_message_text(f"❌ Нічого не знайдено за запитом '{query}'.", chat_id=message.chat.id, message_id=loading.message_id)
                return

            results = await filter_engine.enrich_batch(results, fetch_regions=True)
            await bot.delete_message(chat_id=message.chat.id, message_id=loading.message_id)

            for deal in results:
                card_text = format_eshop_deal_message(deal, language="UA")
                img = deal.banner_url or deal.image_url
                if img:
                    try:
                        await bot.send_photo(chat_id=message.chat.id, photo=img, caption=card_text, parse_mode="HTML")
                        continue
                    except Exception:
                        pass
                await bot.send_message(chat_id=message.chat.id, text=card_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Search error: {e}")
            await bot.send_message(message.chat.id, "❌ Помилка під час пошуку.")

    @bot.message_handler(commands=["subscribe_deals"])
    async def cmd_subscribe(message: Message):
        chat_title = message.chat.title or message.chat.username or f"Chat_{message.chat.id}"
        add_subscription(message.chat.id, message.chat.type, chat_title)
        await bot.reply_to(
            message,
            "✅ <b>Цей чат підписано на автоматичну розсилку знижок Nintendo eShop!</b>\n"
            "Коли з'являтимуться нові хіти зі знижками, бот надішле їх сюди.",
            parse_mode="HTML",
        )

    @bot.message_handler(commands=["unsubscribe_deals"])
    async def cmd_unsubscribe(message: Message):
        if remove_subscription(message.chat.id):
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
