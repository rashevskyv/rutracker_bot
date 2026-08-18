"""Shared plumbing for the send_*_digest.py scripts.

Only the parts that were byte-identical across all three live here: last-run
timestamps, the 20h cooldown, target-group collection and the send loop.
Stats text, translation policy and manual-release handling stay in each script
because they genuinely differ.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from core.settings_loader import setup_logging, close_clients, LOG, IS_TEST_MODE, TEST_GROUPS

logger = logging.getLogger(__name__)

COOLDOWN = timedelta(hours=20)

# Fallback test channel for stats if TEST_GROUPS is not set
DEFAULT_TEST_CHAT_ID = -1001960832921


def get_last_run_time(path: str, default_age: timedelta) -> datetime:
    """Last send time from `path`, or now - default_age when missing/unreadable."""
    fallback = datetime.now() - default_age
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return datetime.fromisoformat(json.load(f)['last_digest_time'])
    except Exception as e:
        logger.error(f"Error reading last run time from {path}: {e}")
        return fallback


def save_last_run_time(path: str):
    """Stamp `path` with the current time."""
    current_time = datetime.now()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'last_digest_time': current_time.isoformat()}, f, indent=2)
        logger.info(f"Saved digest send timestamp: {current_time}")
    except Exception as e:
        logger.error(f"Error saving digest send timestamp: {e}")


def in_cooldown(last_run_time: datetime, force_task: str, label: str) -> bool:
    """True when this digest ran under COOLDOWN ago and nothing overrides it.

    Guards against GitHub Actions cron drift firing the job twice in a day.
    """
    if IS_TEST_MODE or os.environ.get('FORCE_TASK') == force_task:
        return False
    if datetime.now() - last_run_time < COOLDOWN:
        logger.info(f"{label} was already sent recently (last run: {last_run_time}). Skipping.")
        return True
    return False


def parse_topic_id(raw) -> Optional[int]:
    """Telegram topic ids arrive as str/int/None/empty — normalize to int or None."""
    return int(raw) if raw and str(raw).strip() else None


def collect_target_groups(config: Dict) -> List[Dict]:
    """GROUPS plus DIGEST_CHANNEL (when enabled), flattened to one list."""
    target_groups = [
        {
            'name': g.get('group_name', 'Unknown'),
            'chat_id': g.get('chat_id'),
            'topic_id': g.get('topic_id'),
            'language': g.get('language', 'RU'),
        }
        for g in config.get('GROUPS', [])
    ]

    digest_config = config.get('DIGEST_CHANNEL')
    if digest_config and digest_config.get('enabled', False):
        target_groups.append({
            'name': digest_config.get('group_name', 'Digest Channel'),
            'chat_id': digest_config.get('chat_id'),
            'topic_id': digest_config.get('topic_id'),
            'language': digest_config.get('language', 'RU'),
        })

    # Include granular user subscriptions for daily digests
    try:
        from services.subscription_service import SubscriptionService
        sub_service = SubscriptionService()
        existing_ids = {str(g.get("chat_id")) for g in target_groups if g.get("chat_id")}
        for sub in sub_service.get_subscribers_for("digests"):
            if str(sub.get("chat_id")) not in existing_ids:
                target_groups.append({
                    "name": sub.get("title", f"User_{sub['chat_id']}"),
                    "chat_id": sub.get("chat_id"),
                    "topic_id": sub.get("topic_id"),
                    "language": sub.get("language", "UA"),
                })
    except Exception as sub_err:
        logger.debug(f"Could not load digest subscribers: {sub_err}")

    return target_groups


def stats_target() -> tuple:
    """(chat_id, topic_id) of the channel that receives the run summary."""
    if TEST_GROUPS:
        return int(TEST_GROUPS[0]['chat_id']), parse_topic_id(TEST_GROUPS[0].get('topic_id'))
    return DEFAULT_TEST_CHAT_ID, None


async def send_to_groups(manager, groups: List[Dict], since_time: datetime,
                         label: str, translate: Optional[Callable[[Dict], bool]] = None) -> int:
    """Send the digest to every group, one second apart. Returns how many succeeded.

    A failing group is logged and skipped — one bad chat_id must not block the rest.
    `translate` decides per group; None means the manager takes no translate flag.
    """
    sent_count = 0
    for group in groups:
        try:
            chat_id = int(group['chat_id'])
            topic_id = parse_topic_id(group.get('topic_id'))

            extra = {}
            if translate is not None:
                extra['translate_to_ua'] = translate(group)

            logger.info(f"Sending {label} to {group['name']} (chat_id: {chat_id}, topic_id: {topic_id}, {extra})")
            await manager.send_digest(
                target_chat_id=chat_id,
                target_topic_id=topic_id,
                since_time=since_time,
                **extra,
            )
            sent_count += 1
            logger.info(f"{label} sent to {group['name']}")
            await asyncio.sleep(1)

        except Exception as group_err:
            logger.error(f"Failed to send {label} to {group['name']}: {group_err}")

    logger.info(f"{label} sent to {sent_count}/{len(groups)} groups")
    return sent_count


async def load_settings_or_exit(script_file: str, label: str) -> Dict:
    """config/settings.json, or exit(1) after telling the admins."""
    from core.settings_loader import load_config
    from services.telegram_sender import send_message_to_admin

    settings_path = os.path.join(os.path.dirname(os.path.abspath(script_file)), 'config', 'settings.json')
    config = load_config(settings_path)
    if not config:
        logger.error("Could not load settings.json")
        await send_message_to_admin(f"❌ {label}: Could not load settings.json")
        sys.exit(1)
    return config


async def run(title: str, send_digest: Callable):
    """Standard entry point: set up logging, run send_digest(), always close clients."""
    setup_logging(log_level=logging.DEBUG if LOG else logging.INFO)

    logger.info("=" * 50)
    logger.info(f"Starting {title}")
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: {'TEST' if IS_TEST_MODE else 'PRODUCTION'}")
    logger.info("=" * 50)

    try:
        await send_digest()
    finally:
        await close_clients()
