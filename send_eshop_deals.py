"""
Send Nintendo eShop Deals Script for RuTracker Bot.
Fetches top quality Nintendo Switch deals with regional price comparison
(Top 3 cheapest regions, Poland, USA) and broadcasts to configured channels/groups.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Set

from core.logger_setup import setup_logging
from core.settings_loader import (
    GROUPS,
    DIGEST_CHANNEL,
    IS_TEST_MODE,
    TEST_GROUPS,
    bot,
    load_config,
    default_settings_path,
    local_settings_path,
)
from services.eshop import (
    CurrencyService,
    DealFilterEngine,
    EShopService,
    QualityCriteria,
    RatingService,
    RegionPriceService,
    format_eshop_deal_message,
)
from services.telegram_sender import send_message_to_admin

logger = logging.getLogger("send_eshop_deals")

STATE_FILE = os.path.join("data", "eshop_posted_deals.json")
LAST_RUN_FILE = os.path.join("data", "last_eshop_deals_run.json")


def load_posted_deals() -> dict:
    """Load history of previously posted deals."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load posted deals history: {e}")
    return {}


def save_posted_deals(data: dict) -> None:
    """Save history of posted deals."""
    os.makedirs("data", exist_ok=True)
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save posted deals: {e}")


async def send_eshop_deals():
    """Main execution function for broadcasting eShop deals."""
    setup_logging()
    logger.info("Starting Nintendo eShop deals check...")

    # 1. Load config options
    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    min_discount = float(eshop_cfg.get("min_discount_percent", 30.0))
    min_metacritic = int(eshop_cfg.get("min_metacritic_score", 70))
    min_rawg = float(eshop_cfg.get("min_rawg_rating", 3.5))
    max_deals = int(eshop_cfg.get("max_deals_per_run", 5))
    rawg_key = os.environ.get("RAWG_API_KEY") or eshop_cfg.get("rawg_api_key")

    criteria = QualityCriteria(
        min_discount_percent=min_discount,
        min_metacritic_score=min_metacritic,
        min_rawg_rating=min_rawg,
    )

    # 2. Initialize Services
    currency_service = CurrencyService()
    await currency_service.refresh_rates()

    region_price_service = RegionPriceService(currency_service=currency_service)
    eshop_service = EShopService()
    rating_service = RatingService(api_key=rawg_key)

    filter_engine = DealFilterEngine(
        eshop_service=eshop_service,
        rating_service=rating_service,
        region_price_service=region_price_service,
    )

    try:
        # 3. Fetch candidate deals
        logger.info(f"Fetching top deals (min discount: {min_discount}%, min rating: {min_metacritic})...")
        deals = await filter_engine.get_best_deals(
            criteria=criteria, limit=max_deals * 2, fetch_rows=40, include_regional_prices=True
        )

        if not deals:
            logger.info("No deals found matching the current quality criteria.")
            return

        # 4. Filter out recently posted deals (7-day cooldown)
        posted_history = load_posted_deals()
        now_ts = datetime.now(timezone.utc).timestamp()
        cooldown_seconds = 7 * 86400

        # Clean old entries
        fresh_history = {
            fs_id: ts for fs_id, ts in posted_history.items() if (now_ts - ts) < (30 * 86400)
        }

        new_deals = []
        for d in deals:
            last_posted = fresh_history.get(d.fs_id)
            if last_posted and (now_ts - last_posted) < cooldown_seconds:
                continue
            new_deals.append(d)
            if len(new_deals) >= max_deals:
                break

        if not new_deals:
            logger.info("All found deals have already been posted recently.")
            return

        logger.info(f"Prepared {len(new_deals)} fresh deal(s) to send.")

        # 5. Determine target destinations
        target_groups = []
        if IS_TEST_MODE:
            logger.info("TEST MODE: Sending to TEST_GROUPS only")
            target_groups = TEST_GROUPS or []
        else:
            if DIGEST_CHANNEL and DIGEST_CHANNEL.get("enabled", True):
                target_groups.append(DIGEST_CHANNEL)
            if GROUPS:
                target_groups.extend(GROUPS)

            # Also load dynamic subscriptions from /subscribe_deals command
            subs_file = os.path.join("data", "eshop_subscriptions.json")
            if os.path.exists(subs_file):
                try:
                    with open(subs_file, "r", encoding="utf-8") as f:
                        dyn_subs = json.load(f)
                        existing_chat_ids = {str(g.get("chat_id")) for g in target_groups if g.get("chat_id")}
                        for s_id, s_info in dyn_subs.items():
                            if str(s_info.get("chat_id")) not in existing_chat_ids and s_info.get("enabled", True):
                                target_groups.append({
                                    "group_name": s_info.get("title", f"Chat_{s_id}"),
                                    "chat_id": s_info.get("chat_id"),
                                    "topic_id": s_info.get("topic_id"),
                                    "language": s_info.get("language", "UA"),
                                })
                except Exception as sub_err:
                    logger.warning(f"Could not load dynamic subscriptions: {sub_err}")

        if not target_groups:
            logger.warning("No target channels or groups configured in settings.json.")
            return

        # 6. Send deals to targets
        sent_deals_count = 0
        for group in target_groups:
            chat_id = group.get("chat_id")
            topic_id = group.get("topic_id")
            lang = group.get("language", "UA")

            if not chat_id:
                continue

            try:
                chat_id_int = int(chat_id)
                topic_id_int = int(topic_id) if topic_id else None
            except ValueError:
                continue

            for deal in new_deals:
                msg_text = format_eshop_deal_message(deal, language=lang)
                img = deal.banner_url or deal.image_url

                try:
                    if img:
                        await bot.send_photo(
                            chat_id=chat_id_int,
                            message_thread_id=topic_id_int,
                            photo=img,
                            caption=msg_text,
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_message(
                            chat_id=chat_id_int,
                            message_thread_id=topic_id_int,
                            text=msg_text,
                            parse_mode="HTML",
                            disable_web_page_preview=False,
                        )
                    await asyncio.sleep(1)
                except Exception as send_err:
                    logger.error(f"Error sending deal '{deal.title}' to chat {chat_id}: {send_err}")

        # 7. Record posted history
        for deal in new_deals:
            fresh_history[deal.fs_id] = now_ts
        save_posted_deals(fresh_history)

        logger.info(f"Successfully posted {len(new_deals)} eShop deal(s).")

    finally:
        await eshop_service.close()
        await rating_service.close()
        await region_price_service.close()
        await currency_service.close()


if __name__ == "__main__":
    asyncio.run(send_eshop_deals())
