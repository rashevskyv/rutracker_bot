"""
Send Nintendo eShop Deals Script for RuTracker Bot.
Fetches top quality Nintendo Switch deals with regional price comparison
(Top 3 cheapest regions, Poland, USA) and broadcasts to configured channels/groups.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Set

from core.logger_setup import setup_logging
from core.settings_loader import (
    GROUPS,
    IS_TEST_MODE,
    TEST_GROUPS,
    bot,
    close_clients,
    load_config,
    default_settings_path,
    local_settings_path,
)
from services.eshop import (
    CurrencyService,
    DealFilterEngine,
    EShopService,
    GameDeal,
    QualityCriteria,
    RatingService,
    RegionPriceService,
    format_eshop_deal_message,
    download_and_badge_cover,
)
from services.telegram_sender import send_message_to_admin

logger = logging.getLogger("send_eshop_deals")

STATE_FILE = os.path.join("data", "eshop_posted_deals.json")
LAST_RUN_FILE = os.path.join("data", "last_eshop_deals_run.json")


def _normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _get_entry_timestamp(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("posted_at", 0))
    return 0.0


def _is_deal_already_posted(deal: GameDeal, history: dict, cooldown_seconds: float, now_ts: float) -> bool:
    """Check if the game was posted recently by fs_id, nsuid, or normalized title."""
    keys_to_check = []
    if deal.fs_id:
        keys_to_check.append(str(deal.fs_id))
    if deal.nsuid:
        keys_to_check.append(f"nsuid_{deal.nsuid}")
    norm_title = _normalize_title_key(deal.title)
    if norm_title:
        keys_to_check.append(f"title_{norm_title}")

    for k in keys_to_check:
        if k in history:
            ts = _get_entry_timestamp(history[k])
            if (now_ts - ts) < cooldown_seconds:
                return True
    return False


def _record_deal_in_history(history: dict, deal: GameDeal, now_ts: float) -> None:
    """Record deal into history under fs_id, nsuid, and title keys."""
    entry = {
        "title": deal.title,
        "posted_at": now_ts,
        "discount_percent": deal.discount_percent,
        "discount_price": deal.discount_price,
        "currency": deal.currency,
    }
    if deal.fs_id:
        history[str(deal.fs_id)] = entry
    if deal.nsuid:
        history[f"nsuid_{deal.nsuid}"] = entry
    norm_title = _normalize_title_key(deal.title)
    if norm_title:
        history[f"title_{norm_title}"] = entry


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


def load_last_run() -> dict:
    """Load timestamp of last execution."""
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_last_run(data: dict) -> None:
    """Save execution timestamp."""
    os.makedirs("data", exist_ok=True)
    try:
        with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def send_eshop_deals(force: bool = False):
    """Main execution function for broadcasting eShop deals."""
    setup_logging()
    logger.info("Starting Nintendo eShop deals check...")

    # 1. Load config options
    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    if not eshop_cfg.get("enabled", True) and not force:
        logger.info("eShop deals broadcast is disabled in config.")
        return

    interval_hours = float(eshop_cfg.get("interval_hours", 2.0))
    min_discount = float(eshop_cfg.get("min_discount_percent", 30.0))
    min_metacritic = int(eshop_cfg.get("min_metacritic_score", 70))
    min_rawg = float(eshop_cfg.get("min_rawg_rating", 3.5))
    max_deals = int(eshop_cfg.get("max_deals_per_run", 5))
    cooldown_days = float(eshop_cfg.get("cooldown_days", 14.0))
    rawg_key = os.environ.get("RAWG_API_KEY") or eshop_cfg.get("rawg_api_key")

    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()

    # Check interval since last run unless forced
    last_run_info = load_last_run()
    last_ts = last_run_info.get("last_run_timestamp", 0)
    if not force and last_ts > 0:
        elapsed_hours = (now_ts - last_ts) / 3600.0
        if elapsed_hours < interval_hours:
            logger.info(f"Skipping run: only {elapsed_hours:.2f}h elapsed since last run (interval: {interval_hours}h).")
            return

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
            criteria=criteria, limit=max_deals * 3, fetch_rows=50, include_regional_prices=True
        )

        if not deals:
            logger.info("No deals found matching the current quality criteria.")
            return

        # 4. Filter out recently posted deals (configurable cooldown, default 14 days)
        posted_history = load_posted_deals()
        cooldown_seconds = cooldown_days * 86400

        # Clean old entries older than 60 days
        fresh_history = {
            k: v for k, v in posted_history.items() if (now_ts - _get_entry_timestamp(v)) < (60 * 86400)
        }

        new_deals = []
        for d in deals:
            if _is_deal_already_posted(d, fresh_history, cooldown_seconds, now_ts):
                logger.info(f"Skipping already posted deal '{d.title}' (posted within {cooldown_days:.0f} days).")
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
            if eshop_cfg.get("chat_id"):
                target_groups.append({
                    "group_name": "eShop_Deals_Destination",
                    "chat_id": eshop_cfg.get("chat_id"),
                    "topic_id": eshop_cfg.get("topic_id", "561344"),
                    "language": eshop_cfg.get("language", "UA"),
                })
            else:
                digest_channel = cfg.get("DIGEST_CHANNEL")
                if digest_channel and digest_channel.get("enabled", True):
                    target_groups.append(digest_channel)
                groups = cfg.get("GROUPS") or GROUPS
                if groups:
                    target_groups.extend(groups)

                # If topic_id is configured for deals (e.g. 561344), route Ukrainian groups to that topic
                deals_topic = str(eshop_cfg.get("topic_id", "561344"))
                for g in target_groups:
                    if g.get("language", "UA") == "UA" or not g.get("topic_id"):
                        g["topic_id"] = deals_topic

            # Also load dynamic subscriptions from SubscriptionService and legacy eshop_subscriptions
            existing_chat_ids = {str(g.get("chat_id")) for g in target_groups if g.get("chat_id")}
            try:
                from services.subscription_service import SubscriptionService
                sub_service = SubscriptionService()
                for sub in sub_service.get_subscribers_for("deals"):
                    if str(sub.get("chat_id")) not in existing_chat_ids:
                        target_groups.append({
                            "group_name": sub.get("title", f"Chat_{sub['chat_id']}"),
                            "chat_id": sub.get("chat_id"),
                            "topic_id": sub.get("topic_id"),
                            "language": sub.get("language", "UA"),
                        })
                        existing_chat_ids.add(str(sub.get("chat_id")))
            except Exception as sub_err:
                logger.warning(f"Could not load user subscriptions: {sub_err}")

            subs_file = os.path.join("data", "eshop_subscriptions.json")
            if os.path.exists(subs_file):
                try:
                    with open(subs_file, "r", encoding="utf-8") as f:
                        dyn_subs = json.load(f)
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
                msg_text = format_eshop_deal_message(deal, language=lang, currency_service=currency_service)
                badged_img = await download_and_badge_cover(deal)
                photo_payload = badged_img.getvalue() if badged_img else (deal.banner_url or deal.image_url)

                try:
                    if photo_payload:
                        await bot.send_photo(
                            chat_id=chat_id_int,
                            message_thread_id=topic_id_int,
                            photo=photo_payload,
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

        # 7. Record posted history (multi-key by fs_id, nsuid, and normalized title)
        for deal in new_deals:
            _record_deal_in_history(fresh_history, deal, now_ts)
        save_posted_deals(fresh_history)
        save_last_run({"last_run_timestamp": now_ts, "last_run_iso": now_dt.isoformat(), "posted_count": len(new_deals)})

        # 8. Check Wishlists and send direct alerts for discounted games
        try:
            from services.eshop.wishlist_service import WishlistService
            wl_service = WishlistService()
            all_wishlists = wl_service.get_all_wishlists()
            for wl_key, wl_data in all_wishlists.items():
                w_chat_id = wl_data.get("chat_id")
                w_topic_id = wl_data.get("topic_id")
                w_items = wl_data.get("items", [])
                if not w_chat_id or not w_items:
                    continue

                for item in w_items:
                    w_title = item.get("title")
                    if not w_title:
                        continue
                    try:
                        results = await eshop_service.search_games(query=w_title, rows=1)
                        if not results:
                            continue
                        w_deal = results[0]
                        if w_deal.discount_percent > 0:
                            last_notified = item.get("last_notified_discount")
                            if last_notified is None or w_deal.discount_percent > (float(last_notified) + 5.0):
                                enriched_deal = await filter_engine.enrich_deal(w_deal, fetch_regions=True)
                                alert_prefix = "🔔 <b>Знижка на гру з вашого списку бажань (Wishlist)!</b>\n\n"
                                alert_text = alert_prefix + format_eshop_deal_message(
                                    enriched_deal, language="UA", currency_service=currency_service
                                )
                                badged_img = await download_and_badge_cover(enriched_deal)
                                photo_payload = badged_img.getvalue() if badged_img else (enriched_deal.banner_url or enriched_deal.image_url)

                                if photo_payload:
                                    await bot.send_photo(
                                        chat_id=int(w_chat_id),
                                        message_thread_id=int(w_topic_id) if w_topic_id else None,
                                        photo=photo_payload,
                                        caption=alert_text,
                                        parse_mode="HTML",
                                    )
                                else:
                                    await bot.send_message(
                                        chat_id=int(w_chat_id),
                                        message_thread_id=int(w_topic_id) if w_topic_id else None,
                                        text=alert_text,
                                        parse_mode="HTML",
                                    )
                                wl_service.update_notification(wl_key, w_title, w_deal.discount_percent)
                                logger.info(f"Sent wishlist alert for '{w_deal.title}' to {w_chat_id}")
                                await asyncio.sleep(1)
                    except Exception as wl_item_err:
                        logger.debug(f"Error checking wishlist item '{w_title}': {wl_item_err}")
        except Exception as wl_err:
            logger.warning(f"Error processing wishlists in cron: {wl_err}")

        logger.info(f"Successfully posted {len(new_deals)} eShop deal(s).")

    finally:
        await eshop_service.close()
        await rating_service.close()
        await region_price_service.close()
        await currency_service.close()
        try:
            await close_clients()
        except Exception:
            pass


if __name__ == "__main__":
    force_run = "--force" in sys.argv or os.environ.get("FORCE_ESHOP_DEALS", "").lower() == "true"
    asyncio.run(send_eshop_deals(force=force_run))
