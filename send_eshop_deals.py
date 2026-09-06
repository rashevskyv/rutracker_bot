"""
Send Nintendo eShop Deals Script for RuTracker Bot.

Maintains an active Live Showcase of up to N deals (default 30):
- each tracked card is kept while its live Nintendo discount is still valid;
- expired/changed cards and cards displaced by more popular candidates are edited in-place (preserving message_id);
- sends a single update notification message with a collage and direct links when cards are rotated;
- previous update notification (< 48h) is safely deleted before posting a new one;
- showcase state is persisted atomically under PROJECT_ROOT/data after every change;
- after every showcase mutation, state is force-uploaded to Gist so digest sync cannot revive stale cards.
"""

import asyncio
import html
import io
import json
import logging
import math
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from PIL import Image
from telebot import types

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


def create_deals_collage(cover_bytes_list: List[bytes]) -> Optional[io.BytesIO]:
    """Create a near-square collage from every available updated game cover."""
    if not cover_bytes_list:
        return None
    try:
        valid_imgs = []
        for raw in cover_bytes_list:
            if not raw:
                continue
            try:
                im = Image.open(io.BytesIO(raw))
                valid_imgs.append(im)
            except Exception as ie:
                logger.debug(f"Could not open image for collage: {ie}")

        if not valid_imgs:
            return None

        n = len(valid_imgs)
        tile_w, tile_h = 480, 270
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        canvas = Image.new("RGB", (tile_w * cols, tile_h * rows), color=(20, 20, 20))
        for idx, img in enumerate(valid_imgs):
            r = idx // cols
            c = idx % cols
            resized = img.convert("RGB").resize((tile_w, tile_h), Image.Resampling.LANCZOS)
            canvas.paste(resized, (c * tile_w, r * tile_h))

        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning(f"Error creating deals collage: {e}")
        return None


def format_showcase_update_notification(
    active_cards: List[Dict[str, Any]],
    updated_message_ids: Optional[Set[int]] = None,
) -> str:
    """Format single notification message listing all active deals in the showcase."""
    updated_ids: Set[int] = set()
    if updated_message_ids:
        for mid in updated_message_ids:
            try:
                updated_ids.add(int(mid))
            except (ValueError, TypeError):
                pass

    lines = [
        "🔄 <b>Вітрина знижок оновлена!</b>",
        "🆕 — нова або замінена картка\n",
    ]
    for card in active_cards:
        escaped_title = html.escape(str(card.get("title") or "Unknown"))
        mid = card.get("message_id")
        try:
            mid_int = int(mid) if mid is not None else None
        except (ValueError, TypeError):
            mid_int = None

        is_updated = mid_int is not None and mid_int in updated_ids
        prefix = "🆕 " if is_updated else "• "
        link = f"https://t.me/kefir_ukr/561344/{mid}"

        disc = card.get("discount_percent")
        try:
            disc_val = float(disc) if disc is not None else 0.0
        except (ValueError, TypeError):
            disc_val = 0.0

        if disc_val > 0:
            lines.append(f"{prefix}<a href=\"{link}\">{escaped_title}</a> (-{disc_val:.0f}%)")
        else:
            lines.append(f"{prefix}<a href=\"{link}\">{escaped_title}</a>")

    return "\n".join(lines)


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
        last_notif_message_id = None
        last_notif_timestamp = None

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
            expired_targets: List[Dict[str, Any]] = []
            updated_cards: List[Dict[str, Any]] = []

            # Step A: Reset or check expired deals
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
                expired_targets = []
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
                            if getattr(game_check, "downloads_rank", None) is not None:
                                kept["downloads_rank"] = game_check.downloads_rank
                        surviving_items.append(kept)
                    else:
                        # Do NOT delete message; keep in surviving_items and mark as priority target for in-place edit
                        surviving_items.append(dict(item))
                        expired_targets.append(dict(item))
                        logger.info(f"⚠️ [EXPIRED DEAL] '{item_title}' (msg_id={msg_id}) discount ended/changed; queued for in-place edit.")
                        print(f"  ⚠️ [Неактуальна картка] {item_title} (ID: {msg_id}) — знижка завершилась або змінилась, позначено для заміни")

                # Persist surviving list immediately
                showcase_data[showcase_key] = list(surviving_items)
                save_active_showcase(showcase_data)
                save_posted_deals(fresh_history)

            # Step B: Calculate free slots
            available_slots = max(0, max_active_showcase - len(surviving_items))
            logger.info(f"Showcase {showcase_key}: {len(surviving_items)} active, {available_slots} slot(s) available (cap: {max_active_showcase}).")
            print(f"\n📊 [{showcase_key}] Оновлення вітрини: {len(surviving_items)} залишається, {available_slots} вільних слотів...")

            # Step C: Fetch candidate deals
            logger.info(f"🔍 Fetching candidates for {showcase_key}...")
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

            candidate_deals: List[GameDeal] = []
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

                candidate_deals.append(d)

            # Sort candidates by downloads_rank ascending (lower number = higher popularity).
            # Deals without rank are sorted to the end and cannot replace active cards.
            candidate_deals.sort(
                key=lambda d: (0, d.downloads_rank) if (d.downloads_rank is not None and not isinstance(d.downloads_rank, bool)) else (1, 0)
            )

            logger.info(f"Selected {len(candidate_deals)} candidate deal(s) for {showcase_key}.")

            # Step E: Fill free slots and rotate cards in-place
            expired_msg_ids = {it.get("message_id") for it in expired_targets}
            displaceable_items = [
                it for it in surviving_items
                if it.get("message_id") not in expired_msg_ids
                and it.get("downloads_rank") is not None
                and isinstance(it.get("downloads_rank"), (int, float))
                and not isinstance(it.get("downloads_rank"), bool)
            ]
            # Worst popularity first (highest downloads_rank number)
            displaceable_items.sort(key=lambda it: it["downloads_rank"], reverse=True)

            for deal in candidate_deals:
                target_item = None
                is_replacing_expired = False

                # Priority 1: Replace expired cards
                if expired_targets:
                    target_item = expired_targets[0]
                    is_replacing_expired = True
                # Priority 2: If showcase is at capacity, replace less popular active card
                elif len(surviving_items) >= max_active_showcase:
                    if deal.downloads_rank is None or isinstance(deal.downloads_rank, bool):
                        break
                    if not displaceable_items:
                        break
                    worst_item = displaceable_items[0]
                    target_rank = worst_item.get("downloads_rank")
                    if deal.downloads_rank >= target_rank:
                        break
                    target_item = worst_item
                    is_replacing_expired = False

                if target_item is not None:
                    target_msg_id = target_item.get("message_id")
                    target_title = target_item.get("title", "")
                    target_rank = target_item.get("downloads_rank")

                    if is_replacing_expired:
                        expired_targets.pop(0)
                    else:
                        displaceable_items.pop(0)

                    enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                    msg_text = format_eshop_deal_message(enriched, language=lang, currency_service=currency_service)
                    badged_img = await download_and_badge_cover(enriched)
                    cover_bytes = badged_img.getvalue() if badged_img else None
                    photo_payload = cover_bytes or (enriched.banner_url or enriched.image_url)

                    edit_success = False
                    edited_msg = None

                    if photo_payload and target_msg_id:
                        try:
                            media_obj = types.InputMediaPhoto(
                                media=photo_payload,
                                caption=msg_text,
                                parse_mode="HTML",
                            )
                            edited_msg = await bot.edit_message_media(
                                chat_id=chat_id_int,
                                message_id=int(target_msg_id),
                                media=media_obj,
                            )
                            if edited_msg:
                                edit_success = True
                        except Exception as pe:
                            logger.debug(f"edit_message_media failed for {target_msg_id} ({pe}), trying edit_message_caption...")

                    # A candidate may have no usable cover.  Keep an existing photo card and
                    # update its caption before falling back to an old text-only card.
                    if not edit_success and target_msg_id:
                        try:
                            edited_msg = await bot.edit_message_caption(
                                chat_id=chat_id_int,
                                message_id=int(target_msg_id),
                                caption=msg_text,
                                parse_mode="HTML",
                            )
                            if edited_msg:
                                edit_success = True
                        except Exception as ce:
                            logger.debug(f"edit_message_caption failed for {target_msg_id} ({ce}), trying edit_message_text...")

                    if not edit_success and target_msg_id:
                        try:
                            edited_msg = await bot.edit_message_text(
                                chat_id=chat_id_int,
                                message_id=int(target_msg_id),
                                text=msg_text,
                                parse_mode="HTML",
                                disable_web_page_preview=False,
                            )
                            if edited_msg:
                                edit_success = True
                        except Exception as me:
                            logger.error(f"edit_message_text failed for {target_msg_id} ('{deal.title}'): {me}")

                    if not edit_success:
                        logger.error(
                            f"🛑 [ROTATION BLOCKED] Could not edit message {target_msg_id} for '{target_title}'; "
                            f"keeping original in state, candidate '{deal.title}' will not be applied."
                        )
                        print(
                            f"  ⚠️ [НЕ змінено] {target_title} (ID: {target_msg_id}) — редагування не вдалося, заміну не застосовано"
                        )
                        continue

                    # Successful edit: release cooldown for displaced target in history
                    target_fsid = target_item.get("fs_id")
                    if target_fsid and str(target_fsid) in posted_history:
                        posted_history.pop(str(target_fsid), None)
                        fresh_history.pop(str(target_fsid), None)
                    target_nsuid = target_item.get("nsuid")
                    if target_nsuid and f"nsuid_{target_nsuid}" in posted_history:
                        posted_history.pop(f"nsuid_{target_nsuid}", None)
                        fresh_history.pop(f"nsuid_{target_nsuid}", None)
                    target_norm = _normalize_title_key(target_title)
                    if target_norm and f"title_{target_norm}" in posted_history:
                        posted_history.pop(f"title_{target_norm}", None)
                        fresh_history.pop(f"title_{target_norm}", None)

                    deal_rank = getattr(enriched, "downloads_rank", None)
                    if deal_rank is None or isinstance(deal_rank, bool):
                        deal_rank = getattr(deal, "downloads_rank", None)
                    if isinstance(deal_rank, bool):
                        deal_rank = None

                    new_item = {
                        "fs_id": str(deal.fs_id) if deal.fs_id else None,
                        "nsuid": str(deal.nsuid) if deal.nsuid else None,
                        "title": deal.title,
                        "message_id": int(target_msg_id),
                        "posted_at": now_ts,
                        "discount_percent": enriched.discount_percent,
                        "discount_price": enriched.discount_price,
                        "regular_price": enriched.regular_price,
                        "currency": enriched.currency,
                        "downloads_rank": deal_rank,
                    }

                    # Update surviving_items in place (keeping the same message_id!)
                    for idx_s, sit in enumerate(surviving_items):
                        if sit.get("message_id") == target_msg_id:
                            surviving_items[idx_s] = new_item
                            break

                    _record_deal_in_history(fresh_history, enriched, now_ts)
                    showcase_data[showcase_key] = list(surviving_items)
                    save_active_showcase(showcase_data)
                    save_posted_deals(fresh_history)
                    total_posted_this_run += 1

                    updated_cards.append({
                        "title": deal.title,
                        "message_id": int(target_msg_id),
                        "discount_percent": enriched.discount_percent,
                        "cover_bytes": cover_bytes,
                    })

                    if is_replacing_expired:
                        print(
                            f"  🔄 [Оновлено картку: завершена знижка] {target_title} (ID: {target_msg_id}) -> "
                            f"{deal.title} (ранг #{deal_rank})"
                        )
                    else:
                        print(
                            f"  🔄 [Оновлено картку: популярність] {target_title} (ID: {target_msg_id}, ранг #{target_rank}) -> "
                            f"{deal.title} (ранг #{deal_rank})"
                        )

                    await asyncio.sleep(1)

                else:
                    # Free slot in showcase (< max_active_showcase) and no expired targets
                    if len(surviving_items) >= max_active_showcase:
                        break

                    enriched = await filter_engine.enrich_deal(deal, fetch_regions=True)
                    msg_text = format_eshop_deal_message(enriched, language=lang, currency_service=currency_service)
                    badged_img = await download_and_badge_cover(enriched)
                    cover_bytes = badged_img.getvalue() if badged_img else None
                    photo_payload = cover_bytes or (enriched.banner_url or enriched.image_url)

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
                        deal_rank = getattr(enriched, "downloads_rank", None)
                        if deal_rank is None or isinstance(deal_rank, bool):
                            deal_rank = getattr(deal, "downloads_rank", None)
                        if isinstance(deal_rank, bool):
                            deal_rank = None

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
                            "downloads_rank": deal_rank,
                        }
                        surviving_items.append(new_item)
                        _record_deal_in_history(fresh_history, enriched, now_ts)
                        showcase_data[showcase_key] = list(surviving_items)
                        save_active_showcase(showcase_data)
                        save_posted_deals(fresh_history)
                        total_posted_this_run += 1
                        print(f"  📤 [{len(surviving_items)}/{max_active_showcase}] Опубліковано: {deal.title} (ID: {sent_msg.message_id})")

                    await asyncio.sleep(1)

            showcase_data[showcase_key] = list(surviving_items)
            save_active_showcase(showcase_data)
            print(f"✅ Вітрину {showcase_key} оновлено: {len(surviving_items)}/{max_active_showcase} активних карток.\n")

            # Notification for main showcase if any cards were updated
            is_main_showcase = (
                IS_TEST_MODE
                or (chat_id_int == AUTHORIZED_SHOWCASE_CHAT_ID and (topic_id_int is None or topic_id_int in [AUTHORIZED_SHOWCASE_TOPIC_ID, 0]))
            )
            if is_main_showcase and updated_cards:
                prev_notif_id = last_run_info.get("last_notification_message_id")
                prev_notif_ts = float(last_run_info.get("last_notification_timestamp") or 0.0)

                should_send_notif = True
                if prev_notif_id:
                    is_under_48h = (now_ts - prev_notif_ts) < (48 * 3600) if prev_notif_ts > 0 else True
                    if is_under_48h:
                        try:
                            logger.info(f"Deleting previous showcase notification message {prev_notif_id}...")
                            del_success = await safe_delete_showcase_message(
                                chat_id=chat_id_int,
                                topic_id=topic_id_int,
                                message_id=int(prev_notif_id),
                                title="Previous showcase update notification",
                            )
                            if not del_success:
                                logger.warning(
                                    f"Failed to delete previous notification {prev_notif_id}; "
                                    f"skipping sending new notification to prevent duplicates."
                                )
                                should_send_notif = False
                        except Exception as del_err:
                            logger.warning(f"Could not delete previous notification {prev_notif_id}: {del_err}")
                            should_send_notif = False
                    else:
                        logger.info(f"Previous notification {prev_notif_id} is older than 48h, skipping deletion.")

                if should_send_notif:
                    updated_mids = {
                        int(c["message_id"])
                        for c in updated_cards
                        if c.get("message_id") is not None
                    }
                    notif_text = format_showcase_update_notification(surviving_items, updated_mids)
                    cover_bytes_list = [c["cover_bytes"] for c in updated_cards if c.get("cover_bytes")]
                    collage_buf = create_deals_collage(cover_bytes_list) if cover_bytes_list else None

                    sent_notif = None
                    if collage_buf:
                        if len(notif_text) <= 1024:
                            try:
                                sent_notif = await bot.send_photo(
                                    chat_id=chat_id_int,
                                    message_thread_id=topic_id_int,
                                    photo=collage_buf.getvalue(),
                                    caption=notif_text,
                                    parse_mode="HTML",
                                    allow_sending_without_reply=True,
                                )
                            except Exception as pe:
                                logger.debug(f"send_photo for notification failed ({pe}), falling back to text...")
                        else:
                            logger.info(
                                f"Showcase notification ({len(notif_text)} chars) exceeds photo caption limit (1024); "
                                f"falling back to text message to preserve complete showcase card list."
                            )

                    if not sent_notif:
                        try:
                            sent_notif = await bot.send_message(
                                chat_id=chat_id_int,
                                message_thread_id=topic_id_int,
                                text=notif_text,
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                                allow_sending_without_reply=True,
                            )
                        except Exception as me:
                            logger.error(f"send_message for notification failed: {me}")

                    if sent_notif and getattr(sent_notif, "message_id", None):
                        last_notif_message_id = sent_notif.message_id
                        last_notif_timestamp = now_ts
                        logger.info(f"📢 Sent showcase update notification (ID: {last_notif_message_id}) for {len(updated_cards)} card(s).")
                else:
                    logger.info("Skipped sending new showcase update notification because previous notification could not be deleted.")

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
        last_run_payload = {
            "last_run_timestamp": now_ts,
            "last_run_iso": now_dt.isoformat(),
            "posted_count": total_posted_this_run,
        }
        if last_notif_message_id is not None:
            last_run_payload["last_notification_message_id"] = int(last_notif_message_id)
            last_run_payload["last_notification_timestamp"] = float(last_notif_timestamp)
        elif "last_notification_message_id" in last_run_info:
            last_run_payload["last_notification_message_id"] = last_run_info["last_notification_message_id"]
            last_run_payload["last_notification_timestamp"] = float(last_run_info.get("last_notification_timestamp") or 0.0)
        save_last_run(last_run_payload)
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
