"""
Send Swuk Digest Script
Sends accumulated Ukrainian Switch localizations digest to configured channel.
Should be run by cron/scheduler (e.g. daily at 09:00).
Uses the same GROUPS + DIGEST_CHANNEL targets as the homebrew digest.
"""
import asyncio
import logging
import sys
import json
import os
from datetime import datetime, timedelta

from core.settings_loader import setup_logging, close_clients, LOG, IS_TEST_MODE, TEST_GROUPS
from digest.swuk import swuk_digest_manager
from services.telegram_sender import send_message_to_admin

logger = logging.getLogger(__name__)

LAST_RUN_FILE = os.path.join("data", "last_swuk_digest_run.json")

# Fallback test channel for stats if TEST_GROUPS not set
DEFAULT_TEST_CHAT_ID = -1001960832921


def get_last_run_time() -> datetime:
    """Get the last swuk digest send time. Defaults to 7 days ago on first run."""
    if not os.path.exists(LAST_RUN_FILE):
        return datetime.now() - timedelta(days=7)
    try:
        with open(LAST_RUN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return datetime.fromisoformat(data['last_digest_time'])
    except Exception as e:
        logger.error(f"Error reading last run time: {e}")
        return datetime.now() - timedelta(days=7)


def save_last_run_time():
    """Save current time as last swuk digest send time."""
    current_time = datetime.now()
    try:
        with open(LAST_RUN_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_digest_time': current_time.isoformat()}, f, indent=2)
        logger.info(f"Saved swuk digest timestamp: {current_time}")
    except Exception as e:
        logger.error(f"Error saving swuk digest timestamp: {e}")


async def send_digest():
    """Send swuk digest to configured channels (same targets as homebrew digest)."""
    last_run_time = get_last_run_time()
    current_time = datetime.now()

    logger.info(f"Swuk digest period: {last_run_time} to {current_time}")

    entries = swuk_digest_manager.get_entries_since(last_run_time)
    total_count = len(entries)

    if total_count == 0:
        logger.info("No swuk entries for this period")
        await send_message_to_admin("ℹ️ Swuk digest: No new/updated localizations")
        return

    new_count = sum(1 for e in entries if e.get('is_new'))
    update_count = total_count - new_count

    # Determine stats chat details from TEST_GROUPS
    stats_chat_id = DEFAULT_TEST_CHAT_ID
    stats_topic_id = None
    if TEST_GROUPS:
        stats_chat_id = int(TEST_GROUPS[0]['chat_id'])
        stats_topic_id = int(TEST_GROUPS[0]['topic_id']) if TEST_GROUPS[0].get('topic_id') and str(TEST_GROUPS[0]['topic_id']).strip() else None

    if IS_TEST_MODE:
        logger.info("TEST MODE: Sending swuk digest to test groups only")
        if not TEST_GROUPS:
            logger.error("TEST_GROUPS is not configured.")
            sys.exit(1)
        try:
            for group in TEST_GROUPS:
                chat_id = int(group['chat_id'])
                topic_id = int(group['topic_id']) if group.get('topic_id') and str(group['topic_id']).strip() else None
                logger.info(f"Sending test swuk digest to {group.get('group_name', 'Unknown')} (chat: {chat_id}, topic: {topic_id})")
                await swuk_digest_manager.send_digest(
                    target_chat_id=chat_id,
                    target_topic_id=topic_id,
                    since_time=last_run_time,
                )
            logger.info("Test swuk digests sent successfully")
        except Exception as e:
            logger.error(f"Failed to send test swuk digest: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # PRODUCTION MODE: use same GROUPS + DIGEST_CHANNEL as homebrew digest
    from core.settings_loader import load_config, bot
    current_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(current_dir, 'config', 'settings.json')
    config = load_config(settings_path)

    if not config:
        logger.error("Could not load settings.json")
        await send_message_to_admin("❌ Swuk digest: Could not load settings.json")
        sys.exit(1)

    # Collect target groups (same logic as send_homebrew_digest.py)
    target_groups = []

    for group in config.get('GROUPS', []):
        target_groups.append({
            'name': group.get('group_name', 'Unknown'),
            'chat_id': group.get('chat_id'),
            'topic_id': group.get('topic_id'),
        })

    digest_config = config.get('DIGEST_CHANNEL')
    if digest_config and digest_config.get('enabled', False):
        target_groups.append({
            'name': digest_config.get('group_name', 'Digest Channel'),
            'chat_id': digest_config.get('chat_id'),
            'topic_id': digest_config.get('topic_id'),
        })

    if not target_groups:
        logger.error("No target groups configured")
        await send_message_to_admin("❌ Swuk digest: No target groups configured")
        sys.exit(1)

    logger.info(f"PRODUCTION MODE: Sending swuk digest to {len(target_groups)} groups")

    try:
        sent_count = 0
        for group in target_groups:
            try:
                chat_id = int(group['chat_id'])
                topic_id_raw = group.get('topic_id')
                topic_id = int(topic_id_raw) if topic_id_raw and str(topic_id_raw).strip() else None

                logger.info(f"Sending swuk digest to {group['name']} (chat: {chat_id}, topic: {topic_id})")
                await swuk_digest_manager.send_digest(
                    target_chat_id=chat_id,
                    target_topic_id=topic_id,
                    since_time=last_run_time,
                )
                sent_count += 1
                logger.info(f"Swuk digest sent to {group['name']}")
                await asyncio.sleep(1)

            except Exception as group_err:
                logger.error(f"Failed to send swuk digest to {group['name']}: {group_err}")

        if sent_count > 0:
            save_last_run_time()
            swuk_digest_manager.mark_as_sent(last_run_time)
            cleanup_time = datetime.now() - timedelta(days=7)
            swuk_digest_manager.clear_old_entries(cleanup_time)

        stats_message = (
            f"🇺🇦 <b>Swuk дайджест відправлено</b>\n\n"
            f"Нових локалізацій: {new_count}\n"
            f"Оновлень: {update_count}\n"
            f"Всього: {total_count}\n"
            f"Груп: {sent_count}/{len(target_groups)}"
        )
        await bot.send_message(
            chat_id=stats_chat_id,
            message_thread_id=stats_topic_id,
            text=stats_message,
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Failed to send swuk digest: {e}")
        import traceback
        traceback.print_exc()
        try:
            await send_message_to_admin(f"❌ Failed to send swuk digest: {e}")
        except Exception:
            pass
        sys.exit(1)


async def main():
    log_level = logging.DEBUG if LOG else logging.INFO
    setup_logging(log_level=log_level)

    logger.info("=" * 50)
    logger.info("Starting Swuk Digest Send")
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: {'TEST' if IS_TEST_MODE else 'PRODUCTION'}")
    logger.info("=" * 50)

    try:
        await send_digest()
    finally:
        await close_clients()


if __name__ == "__main__":
    asyncio.run(main())
