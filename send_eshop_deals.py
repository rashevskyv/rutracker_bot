"""
Send Nintendo eShop Deals Script for RuTracker Bot.

Maintains an active Live Showcase of up to N deals (default 30):
- each tracked card is kept while its live Nintendo discount is still valid;
- expired/changed cards are deleted by stored message_id, then only vacated slots are refilled;
- showcase state is persisted atomically under PROJECT_ROOT/data after every change;
- if Telegram refuses deletion, the card stays tracked (no silent orphans / no extra posts);
- after every showcase mutation, state is force-uploaded to Gist so digest sync cannot revive stale cards.
"""

import asyncio
import json
import logging
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_ROOT, "data", "eshop_posted_deals.json")
SHOWCASE_FILE = os.path.join(PROJECT_ROOT, "data", "eshop_active_showcase.json")
LAST_RUN_FILE = os.path.join(PROJECT_ROOT, "data", "last_eshop_deals_run.json")

# Strict Security Lock: Deletions are hard-locked to this exact chat and topic
AUTHORIZED_SHOWCASE_CHAT_ID = -1001790782971
AUTHORIZED_SHOWCASE_TOPIC_ID = 561344


def log_showcase_diagnostics() -> None:
    """Log diagnostic information about the showcase state file at run start."""
    if os.path.exists(SHOWCASE_FILE):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(SHOWCASE_FILE), tz=timezone.utc).isoformat()
            showcase = load_active_showcase()
            if not showcase:
                logger.info(f"📂 [SHOWCASE DIAGNOSTIC] Path: {os.path.abspath(SHOWCASE_FILE)} | mtime: {mtime} | Content: empty")
            for key, items in showcase.items():
                count = len(items) if isinstance(items, list) else 0
                first_msg = items[0].get("message_id") if count > 0 and isinstance(items[0], dict) else None
                last_msg = items[-1].get("message_id") if count > 0 and isinstance(items[-1], dict) else None
                logger.info(
                    f"📂 [SHOWCASE DIAGNOSTIC] Path: {os.path.abspath(SHOWCASE_FILE)} | mtime: {mtime} | "
                    f"Key: {key} | Count: {count} | First msg_id: {first_msg} | Last msg_id: {last_msg}"
                )
        except Exception as e:
            logger.warning(f"Could not log showcase diagnostics: {e}")
    else:
        logger.info(f"📂 [SHOWCASE DIAGNOSTIC] Path: {os.path.abspath(SHOWCASE_FILE)} does not exist yet.")


async def safe_delete_showcase_message(
    chat_id: int,
    topic_id: Optional[int],
    message_id: int,
    title: str = "",
) -> bool:
    """
    Strict security guardrail:
    ABSOLUTELY PREVENTS deleting any message outside https://t.me/kefir_ukr/561344.
    """
    is_authorized = (
        IS_TEST_MODE
        or (int(chat_id) == AUTHORIZED_SHOWCASE_CHAT_ID and (topic_id is None or int(topic_id) in [AUTHORIZED_SHOWCASE_TOPIC_ID, 0]))
    )
    if not is_authorized:
        logger.error(
            f"🚫 [SECURITY BLOCK] Refusing to delete message {message_id} in chat {chat_id}, topic {topic_id}! "
            f"Deletion is strictly restricted to chat {AUTHORIZED_SHOWCASE_CHAT_ID}, topic {AUTHORIZED_SHOWCASE_TOPIC_ID} (https://t.me/kefir_ukr/561344)."
        )
        return False

    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
        logger.info(f"🗑 [SAFE DELETE] Deleted showcase message {message_id} ('{title}') from topic {topic_id} in chat {chat_id}")
        return True
    except Exception as e:
        err_str = str(e).lower()
        # Only treat truly-absent messages as success. "message can't be deleted" means the
        # message still exists but Telegram refused deletion — must NOT count as cleaned up.
        if any(
            w in err_str
            for w in [
                "message to delete not found",
                "message_id_invalid",
                "message not found",
            ]
        ):
            logger.info(f"🗑 [SAFE DELETE] Message {message_id} ('{title}') already absent from Telegram: {e}")
            return True
        logger.warning(f"⚠️ Could not delete message {message_id} ('{title}') in chat {chat_id}: {e}")
        return False


def _normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower()) if title else ""


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


def _atomic_write_json(path: str, data: Any) -> None:
    """Atomically write JSON under PROJECT_ROOT so partial writes / wrong cwd cannot corrupt state."""
    directory = os.path.dirname(path) or PROJECT_ROOT
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


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
    try:
        _atomic_write_json(STATE_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save posted deals: {e}")


def load_active_showcase() -> dict:
    """Load currently active showcase messages."""
    if os.path.exists(SHOWCASE_FILE):
        try:
            with open(SHOWCASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load active showcase: {e}")
    return {}


def save_active_showcase(data: dict) -> None:
    """Save active showcase messages."""
    try:
        _atomic_write_json(SHOWCASE_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save active showcase: {e}")


def prune_showcase_to_keys(showcase_data: dict, keep_keys: Set[str]) -> dict:
    """Drop stale destination keys so old topic leftovers cannot revive via Gist."""
    if not keep_keys:
        return showcase_data
    pruned = {k: v for k, v in showcase_data.items() if k in keep_keys}
    dropped = sorted(set(showcase_data.keys()) - set(pruned.keys()))
    if dropped:
        logger.info(f"Pruned stale showcase keys: {dropped}")
    return pruned


def sync_eshop_state_after_change(reason: str = "") -> None:
    """Push Live Showcase state to Gist immediately after local changes."""
    try:
        from sync_gist_state import sync_eshop_state_to_gist

        ok = sync_eshop_state_to_gist(force=True)
        if ok:
            logger.info(f"eShop state force-uploaded to Gist ({reason or 'update'}).")
        else:
            logger.error(
                f"eShop state Gist upload failed ({reason or 'update'}). "
                "Local showcase is saved, but digest download could revive stale Gist until upload succeeds."
            )
    except Exception as e:
        logger.error(f"eShop state Gist upload error ({reason or 'update'}): {e}")


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
    try:
        _atomic_write_json(LAST_RUN_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save last run state: {e}")


async def send_eshop_deals(force: bool = False, reset: bool = False):
    """Main execution function for broadcasting eShop deals with Live Showcase rotation."""
    setup_logging()
    if reset:
        force = True
    logger.info(f"Starting Nintendo eShop deals check with Live Showcase Rotation (force={force}, reset={reset})...")
    log_showcase_diagnostics()

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
    max_active_showcase = int(eshop_cfg.get("max_active_showcase", eshop_cfg.get("max_deals_per_run", 30)))
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
        # 3. Determine target destinations
        target_groups = []
        if IS_TEST_MODE:
            logger.info("TEST MODE: Sending to TEST_GROUPS only")
            target_groups = TEST_GROUPS or []
        else:
            if eshop_cfg.get("chat_id"):
                target_groups.append({
                    "group_name": "eShop_Deals_Destination",
                    "chat_id": eshop_cfg.get("chat_id"),
                    "topic_id": str(eshop_cfg.get("topic_id", "561344")),
                    "language": eshop_cfg.get("language", "UA"),
                })
            else:
                deals_topic = str(eshop_cfg.get("topic_id", "561344"))
                ua_groups = [g for g in (cfg.get("GROUPS") or GROUPS or []) if g.get("language", "UA") == "UA"]
                if ua_groups:
                    main_g = dict(ua_groups[0])
                    main_g["topic_id"] = deals_topic
                    target_groups.append(main_g)
                else:
                    groups = cfg.get("GROUPS") or GROUPS or []
                    if groups:
                        main_g = dict(groups[0])
                        main_g["topic_id"] = deals_topic
                        target_groups.append(main_g)

            # Dynamic subscriptions
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

        if not target_groups:
            logger.warning("No target channels or groups configured in settings.json.")
            return

        # 4. Load history and showcase data
        posted_history = load_posted_deals()
        showcase_data = load_active_showcase()

        cooldown_seconds = cooldown_days * 86400
        fresh_history = {
            k: v for k, v in posted_history.items() if (now_ts - _get_entry_timestamp(v)) < (60 * 86400)
        }
        total_posted_this_run = 0

        # 5. Process each target destination with Expiration-based Showcase verification
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

            showcase_key = f"{chat_id}_{topic_id}" if topic_id else str(chat_id)
            current_showcase_items = showcase_data.get(showcase_key, [])
            surviving_items = []

            # Step A: Reset or check and delete expired deals
            if reset:
                logger.info(f"🔄 [RESET] Purging {len(current_showcase_items)} active showcase deals from {showcase_key}...")
                for item in current_showcase_items:
                    msg_id = item.get("message_id")
                    title = item.get("title", "")
                    if msg_id:
                        await safe_delete_showcase_message(
                            chat_id=chat_id_int,
                            topic_id=topic_id_int,
                            message_id=int(msg_id),
                            title=title,
                        )
                        await asyncio.sleep(0.08)
                current_showcase_items = []
                surviving_items = []
                showcase_data[showcase_key] = []
                save_active_showcase(showcase_data)
                fresh_history = {}
                posted_history = {}
                save_posted_deals(fresh_history)
            else:
                logger.info(f"Checking {len(current_showcase_items)} active showcase deals in {showcase_key} for discount expiration...")
                for item in current_showcase_items:
                    item_title = item.get("title", "")
                    msg_id = item.get("message_id")
                    fs_id = item.get("fs_id")
                    is_still_discounted = False
                    game_check = None

                    try:
                        if fs_id:
                            game_check = await eshop_service.get_game_by_fs_id(str(fs_id))
                        if not game_check and item_title:
                            results = await eshop_service.search_games(query=item_title, rows=1)
                            if results:
                                game_check = results[0]

                        if game_check:
                            has_discount = (
                                game_check.discount_percent > 0
                                and (game_check.regular_price is None or game_check.regular_price > game_check.discount_price)
                            )
                            old_disc_price = float(item.get("discount_price") or 0.0)
                            old_disc_pct = float(item.get("discount_percent") or 0.0)

                            price_changed = False
                            if old_disc_price > 0 and abs(game_check.discount_price - old_disc_price) > 0.05:
                                price_changed = True
                            if old_disc_pct > 0 and abs(game_check.discount_percent - old_disc_pct) > 1.0:
                                price_changed = True

                            if has_discount and not price_changed:
                                is_still_discounted = True
                    except Exception as check_err:
                        logger.debug(f"Could not verify discount for '{item_title}': {check_err}")
                        is_still_discounted = True

                    if is_still_discounted:
                        kept = dict(item)
                        # Refresh stored live prices so tiny API drift does not force churn next run.
                        if game_check is not None:
                            kept["discount_price"] = game_check.discount_price
                            kept["discount_percent"] = game_check.discount_percent
                            if game_check.regular_price is not None:
                                kept["regular_price"] = game_check.regular_price
                            if game_check.currency:
                                kept["currency"] = game_check.currency
                        surviving_items.append(kept)
                    else:
                        deleted = True
                        if msg_id:
                            deleted = await safe_delete_showcase_message(
                                chat_id=chat_id_int,
                                topic_id=topic_id_int,
                                message_id=int(msg_id),
                                title=item_title,
                            )
                            await asyncio.sleep(0.08)

                        if deleted:
                            print(f"  🗑 [Видалено] {item_title} (ID: {msg_id}) — знижка завершилась або змінилась")
                            if fs_id and str(fs_id) in posted_history:
                                posted_history.pop(str(fs_id), None)
                                fresh_history.pop(str(fs_id), None)
                            nsuid = item.get("nsuid")
                            if nsuid and f"nsuid_{nsuid}" in posted_history:
                                posted_history.pop(f"nsuid_{nsuid}", None)
                                fresh_history.pop(f"nsuid_{nsuid}", None)
                            norm = _normalize_title_key(item_title)
                            if norm and f"title_{norm}" in posted_history:
                                posted_history.pop(f"title_{norm}", None)
                                fresh_history.pop(f"title_{norm}", None)
                        else:
                            # Critical: never drop tracking if Telegram still has the card.
                            # Dropping here caused silent orphans + daily reposts.
                            logger.error(
                                f"🛑 Keeping '{item_title}' (msg_id={msg_id}) in showcase after failed delete; "
                                f"slot will not be refilled until deletion succeeds."
                            )
                            print(
                                f"  ⚠️ [НЕ видалено] {item_title} (ID: {msg_id}) — залишаю в трекінгу, слот не звільняю"
                            )
                            surviving_items.append(item)

                # Persist purged surviving list immediately
                showcase_data[showcase_key] = list(surviving_items)
                save_active_showcase(showcase_data)
                save_posted_deals(fresh_history)

            # Step B: Calculate free slots
            available_slots = max(0, max_active_showcase - len(surviving_items))
            logger.info(f"Showcase {showcase_key}: {len(surviving_items)} active, {available_slots} slot(s) available (cap: {max_active_showcase}).")
            print(f"\n📊 [{showcase_key}] Оновлення вітрини: {len(surviving_items)} залишається, {available_slots} вільних слотів...")

            if available_slots <= 0:
                logger.info(f"Showcase {showcase_key} is full ({len(surviving_items)}/{max_active_showcase}). No new deals needed.")
                print(f"✅ Вітрину {showcase_key} заповнено: {len(surviving_items)}/{max_active_showcase} активних карток. Нові картки не публікуються.\n")
                continue

            # Step C: Fetch candidate deals
            logger.info(f"🔍 Fetching candidates to fill {available_slots} slot(s)...")
            raw_popular = await eshop_service.fetch_popular_discounted_games(
                min_discount_percent=criteria.min_discount_percent
            )
            raw_general = await eshop_service.fetch_discounted_games(
                rows=150, sort="popularity desc", min_discount_percent=criteria.min_discount_percent
            )
            raw_deals = raw_popular + raw_general

            # Step D: Filter out existing surviving deals, cooldown deals, and duplicates
            existing_titles = {_normalize_title_key(it.get("title", "")) for it in surviving_items}
            existing_fsids = {str(it.get("fs_id")) for it in surviving_items if it.get("fs_id")}
            existing_nsuids = {str(it.get("nsuid")) for it in surviving_items if it.get("nsuid")}

            deals_to_post: List[GameDeal] = []
            seen_batch_titles = set()
            seen_batch_ids = set()

            for d in raw_deals:
                d_norm = _normalize_title_key(d.title)
                d_fsid = str(d.fs_id) if d.fs_id else ""
                d_nsuid = str(d.nsuid) if d.nsuid else ""

                if not d_norm or d_norm in existing_titles or d_norm in seen_batch_titles:
                    continue
                if (d_fsid and d_fsid in existing_fsids) or (d_fsid and d_fsid in seen_batch_ids):
                    continue
                if (d_nsuid and d_nsuid in existing_nsuids) or (d_nsuid and d_nsuid in seen_batch_ids):
                    continue

                if _is_deal_already_posted(d, fresh_history, cooldown_seconds, now_ts):
                    continue

                seen_batch_titles.add(d_norm)
                if d_fsid:
                    seen_batch_ids.add(d_fsid)
                if d_nsuid:
                    seen_batch_ids.add(d_nsuid)

                deals_to_post.append(d)
                if len(deals_to_post) >= available_slots:
                    break

            logger.info(f"Selected {len(deals_to_post)} deal(s) to publish for {showcase_key}.")

            # Step E: Enrich and send ONLY the selected deals (never exceed hard cap)
            for deal in deals_to_post:
                if len(surviving_items) >= max_active_showcase:
                    logger.info(
                        f"Hard cap reached ({len(surviving_items)}/{max_active_showcase}); stopping further posts."
                    )
                    break

                enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                msg_text = format_eshop_deal_message(enriched, language=lang, currency_service=currency_service)
                badged_img = await download_and_badge_cover(enriched)
                photo_payload = badged_img.getvalue() if badged_img else (enriched.banner_url or enriched.image_url)

                sent_msg = None
                if photo_payload:
                    try:
                        sent_msg = await bot.send_photo(
                            chat_id=chat_id_int,
                            message_thread_id=topic_id_int,
                            photo=photo_payload,
                            caption=msg_text,
                            parse_mode="HTML",
                            allow_sending_without_reply=True,
                        )
                    except Exception as pe:
                        logger.debug(f"send_photo failed ({pe}), falling back to text message...")

                if not sent_msg:
                    try:
                        sent_msg = await bot.send_message(
                            chat_id=chat_id_int,
                            message_thread_id=topic_id_int,
                            text=msg_text,
                            parse_mode="HTML",
                            disable_web_page_preview=False,
                            allow_sending_without_reply=True,
                        )
                    except Exception as me:
                        logger.error(f"send_message failed for '{deal.title}': {me}")

                if sent_msg:
                    new_item = {
                        "fs_id": str(deal.fs_id) if deal.fs_id else None,
                        "nsuid": str(deal.nsuid) if deal.nsuid else None,
                        "title": deal.title,
                        "message_id": sent_msg.message_id,
                        "posted_at": now_ts,
                        "discount_percent": enriched.discount_percent,
                        "discount_price": enriched.discount_price,
                        "regular_price": enriched.regular_price,
                        "currency": enriched.currency,
                    }
                    surviving_items.append(new_item)
                    _record_deal_in_history(fresh_history, enriched, now_ts)
                    showcase_data[showcase_key] = surviving_items
                    save_active_showcase(showcase_data)
                    save_posted_deals(fresh_history)
                    total_posted_this_run += 1
                    print(f"  📤 [{len(surviving_items)}/{max_active_showcase}] Опубліковано: {deal.title} (ID: {sent_msg.message_id})")

                await asyncio.sleep(1)

            showcase_data[showcase_key] = surviving_items
            save_active_showcase(showcase_data)
            print(f"✅ Вітрину {showcase_key} оновлено: {len(surviving_items)}/{max_active_showcase} активних карток.\n")

        # 6. Save execution state (only keys touched this run — drop stale destinations)
        active_keys = set()
        for group in target_groups:
            cid = group.get("chat_id")
            if not cid:
                continue
            tid = group.get("topic_id")
            active_keys.add(f"{cid}_{tid}" if tid else str(cid))
        showcase_data = prune_showcase_to_keys(showcase_data, active_keys)
        save_active_showcase(showcase_data)
        save_posted_deals(fresh_history)
        save_last_run({
            "last_run_timestamp": now_ts,
            "last_run_iso": now_dt.isoformat(),
            "posted_count": total_posted_this_run,
        })
        sync_eshop_state_after_change(
            f"showcase cycle posted={total_posted_this_run} force={force} reset={reset}"
        )

        # 7. Check Wishlists and send direct alerts
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
                        if w_deal.discount_percent > 0 and (w_deal.regular_price is None or w_deal.regular_price > w_deal.discount_price):
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
                                        allow_sending_without_reply=True,
                                    )
                                else:
                                    await bot.send_message(
                                        chat_id=int(w_chat_id),
                                        message_thread_id=int(w_topic_id) if w_topic_id else None,
                                        text=alert_text,
                                        parse_mode="HTML",
                                        allow_sending_without_reply=True,
                                    )
                                wl_service.update_notification(wl_key, w_title, w_deal.discount_percent)
                                logger.info(f"Sent wishlist alert for '{w_deal.title}' to {w_chat_id}")
                                await asyncio.sleep(1)
                    except Exception as wl_item_err:
                        logger.debug(f"Error checking wishlist item '{w_title}': {wl_item_err}")
        except Exception as wl_err:
            logger.warning(f"Error processing wishlists in cron: {wl_err}")

        logger.info(f"Showcase cycle completed. Posted {total_posted_this_run} deal(s).")

    finally:
        await eshop_service.close()
        await rating_service.close()
        await region_price_service.close()
        await currency_service.close()
        try:
            await close_clients()
        except Exception:
            pass


async def remove_showcase_deals(remove_arg: str):
    """
    Safely remove active eShop showcase deal messages strictly from the designated eShop topic (561344).
    """
    setup_logging()
    clean_arg = remove_arg.strip().lower()
    logger.info(f"Starting removal of showcase deal messages strictly from target eShop topic: '{clean_arg}'...")

    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    # Determine the single designated target chat and topic for eShop deals
    if IS_TEST_MODE:
        target_chat = int(TEST_GROUPS[0]["chat_id"]) if TEST_GROUPS else -1001790782971
        target_topic = int(TEST_GROUPS[0]["topic_id"]) if TEST_GROUPS and TEST_GROUPS[0].get("topic_id") else 561344
    elif eshop_cfg.get("chat_id"):
        target_chat = int(eshop_cfg["chat_id"])
        target_topic = int(eshop_cfg.get("topic_id") or 561344)
    else:
        target_chat = -1001790782971
        target_topic = int(eshop_cfg.get("topic_id") or 561344)

    logger.info(f"Targeting eShop topic {target_topic} in chat {target_chat} for clean-up...")

    showcase_key = f"{target_chat}_{target_topic}" if target_topic else str(target_chat)
    showcase_data = load_active_showcase()
    items = showcase_data.get(showcase_key, [])

    remove_all = clean_arg == "all"
    is_title_search = not remove_all and not clean_arg.isdigit()

    if is_title_search:
        target_title_norm = clean_arg.lower()
        to_delete = [it for it in items if target_title_norm in it.get("title", "").lower()]
        surviving = [it for it in items if target_title_norm not in it.get("title", "").lower()]
        if not to_delete:
            logger.info(f"ℹ️ No tracked deals matching '{remove_arg}' found in showcase database.")
            print(f"ℹ️ No tracked deals matching '{remove_arg}' found in showcase database.")
            return
    elif remove_all:
        to_delete = items[:]
        surviving = []
    else:
        try:
            remove_count = max(1, int(clean_arg))
            to_delete = items[:remove_count]
            surviving = items[remove_count:]
        except ValueError:
            logger.error(f"Invalid remove argument: '{remove_arg}'. Please specify a number, game title, or 'all'.")
            return

    total_deleted = 0
    deleted_msg_ids = set()

    try:
        # Delete strictly tracked items recorded for this topic
        for it in to_delete:
            msg_id = it.get("message_id")
            title = it.get("title", "")
            if msg_id and int(msg_id) not in deleted_msg_ids:
                deleted = await safe_delete_showcase_message(
                    chat_id=target_chat,
                    topic_id=target_topic,
                    message_id=int(msg_id),
                    title=title,
                )
                if deleted:
                    total_deleted += 1
                    deleted_msg_ids.add(int(msg_id))
                await asyncio.sleep(0.08)

        # Update showcase state and release cooldown history for deleted games
        showcase_data[showcase_key] = surviving
        save_active_showcase(showcase_data)

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
        sync_eshop_state_after_change(f"remove arg={clean_arg} deleted={total_deleted}")

        if total_deleted > 0:
            logger.info(f"✅ Removal complete. Successfully deleted {total_deleted} tracked deal message(s) from topic {target_topic}.")
            print(f"✅ Successfully deleted {total_deleted} tracked deal message(s) from topic {target_topic}.")
        else:
            logger.info(f"ℹ️ Topic {target_topic} has 0 tracked deal messages in showcase database.")
            print(f"ℹ️ Topic {target_topic} has 0 tracked deal messages in showcase database.")
    finally:
        try:
            await close_clients()
        except Exception:
            pass


def parse_message_id_targets(arg_str: str) -> List[int]:
    """Parse comma-separated message IDs and ID ranges (e.g. '564561-564590,564947-564979')."""
    ids = []
    parts = [p.strip() for p in arg_str.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            sub = [s.strip() for s in part.split("-") if s.strip()]
            if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                start_id, end_id = int(sub[0]), int(sub[1])
                if start_id > end_id:
                    start_id, end_id = end_id, start_id
                if (end_id - start_id) > 500:
                    logger.warning(f"Range {start_id}-{end_id} exceeds safety cap of 500 IDs, truncating.")
                    end_id = start_id + 500
                ids.extend(range(start_id, end_id + 1))
        elif part.isdigit():
            ids.append(int(part))
    return sorted(list(set(ids)))


async def delete_orphan_showcase_messages(target_arg: str):
    """
    Safely delete orphan or untracked deal messages strictly from target topic (561344)
    using message IDs or ranges (e.g. '564561-564590,564947-564979').
    """
    setup_logging()
    msg_ids = parse_message_id_targets(target_arg)
    if not msg_ids:
        print(f"❌ No valid message IDs found in input: '{target_arg}'. Usage: --delete-messages 564561-564590,564947-564979")
        return

    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    target_chat = int(eshop_cfg.get("chat_id") or -1001790782971)
    target_topic = int(eshop_cfg.get("topic_id") or 561344)
    showcase_key = f"{target_chat}_{target_topic}" if target_topic else str(target_chat)

    logger.info(f"Targeting {len(msg_ids)} message IDs for safe deletion in chat {target_chat}, topic {target_topic}...")
    print(f"\n🗑 [Видалення повідомлень] Цільовий топік: {target_topic} (Чат: {target_chat})")
    print(f"Всього повідомлень для перевірки/видалення: {len(msg_ids)}\n" + "=" * 60)

    showcase_data = load_active_showcase()
    current_items = showcase_data.get(showcase_key, [])
    ids_to_del_set = set(msg_ids)

    # Filter out removed IDs from showcase data if present
    deleted_items = [it for it in current_items if int(it.get("message_id", 0)) in ids_to_del_set]
    surviving = [it for it in current_items if int(it.get("message_id", 0)) not in ids_to_del_set]

    total_deleted = 0
    try:
        for mid in msg_ids:
            deleted = await safe_delete_showcase_message(
                chat_id=target_chat,
                topic_id=target_topic,
                message_id=mid,
                title=f"Manual/Orphan ID {mid}",
            )
            if deleted:
                total_deleted += 1
                print(f"  🗑 [Видалено] Повідомлення ID: {mid}")
            await asyncio.sleep(0.08)

        if deleted_items or len(surviving) != len(current_items):
            showcase_data[showcase_key] = surviving
            save_active_showcase(showcase_data)
            print(f"💾 Оновлено базу активної вітрини: залишилось {len(surviving)} карток.")

            posted_history = load_posted_deals()
            for it in deleted_items:
                fs_id = it.get("fs_id")
                title = it.get("title")
                nsuid = it.get("nsuid")
                if fs_id and str(fs_id) in posted_history:
                    posted_history.pop(str(fs_id), None)
                if nsuid and f"nsuid_{nsuid}" in posted_history:
                    posted_history.pop(f"nsuid_{nsuid}", None)
                norm = _normalize_title_key(title)
                if norm and f"title_{norm}" in posted_history:
                    posted_history.pop(f"title_{norm}", None)
            save_posted_deals(posted_history)
            sync_eshop_state_after_change(f"delete-messages surviving={len(surviving)}")

        print(f"\n✅ Завершено. Оброблено {len(msg_ids)} повідомлень, видалено/підтверджено: {total_deleted}.\n" + "=" * 60)
    finally:
        try:
            await close_clients()
        except Exception:
            pass


def list_showcase_deals():
    """
    List all games currently tracked in active showcase database for topic 561344.
    """
    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    target_chat = int(eshop_cfg.get("chat_id") or -1001790782971)
    target_topic = int(eshop_cfg.get("topic_id") or 561344)
    showcase_key = f"{target_chat}_{target_topic}" if target_topic else str(target_chat)

    showcase_data = load_active_showcase()
    items = showcase_data.get(showcase_key, [])
    if not items:
        for k, v in showcase_data.items():
            if str(target_chat) in k and v:
                showcase_key = k
                items = v
                break

    print(f"\n📊 [Активна вітрина eShop] Топік: {target_topic} (Чат: {target_chat})")
    print(f"Всього ігор у базі вітрини: {len(items)}/30\n" + "=" * 60)
    if not items:
        print("ℹ️ База даних вітрини наразі порожня (0 ігор).")
        print("Щоб заповнити вітрину 30 актуальними хітами, виконайте: python send_eshop_deals.py --force")
        return

    for i, it in enumerate(items, 1):
        title = it.get("title", "Unknown")
        disc = it.get("discount_percent", 0)
        price = it.get("discount_price", 0)
        curr = it.get("currency", "EUR")
        msg_id = it.get("message_id")
        fs_id = it.get("fs_id")
        print(f"{i:2d}. {title} | -{disc:.0f}% ({price} {curr}) | msg_id: {msg_id} | fs_id: {fs_id}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nintendo eShop Deals broadcaster & Showcase Manager.")
    parser.add_argument("--force", "-f", action="store_true", help="Force deals broadcast regardless of interval.")
    parser.add_argument("--reset", action="store_true", help="Reset active showcase and history, broadcasting 30 fresh deals.")
    parser.add_argument("--refresh", action="store_true", help="Alias for --reset.")
    parser.add_argument("--list", "-l", action="store_true", help="List all currently tracked active deals in showcase database.")
    parser.add_argument(
        "--remove",
        "-r",
        type=str,
        default=None,
        help="Remove specified number of deals, game title, or 'all' from active showcase (e.g. --remove 20, --remove all).",
    )
    parser.add_argument(
        "--delete-messages",
        "--cleanup-orphans",
        type=str,
        default=None,
        help="Safely delete orphan/untracked deal messages in topic 561344 by ID or range (e.g. --delete-messages 564561-564590,564947-564979).",
    )

    args, unknown = parser.parse_known_args()

    if args.list or ("--list" in sys.argv) or any(a.lower() in ["list", "--list", "showcase", "--showcase"] for a in sys.argv[1:]):
        list_showcase_deals()
        sys.exit(0)

    # Detect delete-messages
    delete_target = getattr(args, "delete_messages", None) or getattr(args, "cleanup_orphans", None)
    if not delete_target:
        for idx, arg in enumerate(unknown):
            if arg.lower() in ["--delete-messages", "--cleanup-orphans", "delete-messages", "cleanup-orphans"] and idx + 1 < len(unknown):
                delete_target = unknown[idx + 1]
                break

    if delete_target:
        asyncio.run(delete_orphan_showcase_messages(delete_target))
        sys.exit(0)

    # Detect reset / refresh from flags or positional arguments
    reset_run = (
        args.reset
        or args.refresh
        or any(a.lower() in ["reset", "--reset", "refresh", "--refresh"] for a in sys.argv[1:])
    )

    remove_target = args.remove
    if not remove_target:
        for idx, arg in enumerate(unknown):
            if arg.lower() == "remove" and idx + 1 < len(unknown):
                remove_target = unknown[idx + 1]
                break

    if remove_target:
        asyncio.run(remove_showcase_deals(remove_target))
    else:
        force_run = (
            reset_run
            or args.force
            or ("--force" in sys.argv)
            or (os.environ.get("FORCE_ESHOP_DEALS", "").lower() == "true")
        )
        asyncio.run(send_eshop_deals(force=force_run, reset=reset_run))
