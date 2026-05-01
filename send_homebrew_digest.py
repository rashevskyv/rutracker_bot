"""
Send Homebrew Digest Script
Sends accumulated homebrew digest to configured channel
Should be run by cron/scheduler at 9:00 AM daily
"""
import asyncio
import logging
import sys
import json
import os
from datetime import datetime, timedelta

from core.settings_loader import setup_logging, close_clients, LOG, IS_TEST_MODE
from digest.homebrew import homebrew_digest_manager
from services.telegram_sender import send_message_to_admin

logger = logging.getLogger(__name__)

LAST_RUN_FILE = "last_homebrew_digest_run.json"


def get_last_run_time() -> datetime:
    """Get the last digest run time from file (set by collect_homebrew_updates.py)"""
    if not os.path.exists(LAST_RUN_FILE):
        # Default to 7 days ago if file doesn't exist (first run)
        return datetime.now() - timedelta(days=7)

    try:
        with open(LAST_RUN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return datetime.fromisoformat(data['last_digest_time'])
    except Exception as e:
        logger.error(f"Error reading last run time: {e}")
        return datetime.now() - timedelta(days=7)


async def send_digest():
    """Send homebrew digest to configured channel"""

    # Get last run time
    last_run_time = get_last_run_time()
    current_time = datetime.now()

    logger.info(f"Homebrew digest period: {last_run_time} to {current_time}")

    # Load settings to get DIGEST_CHANNEL configuration
    from core.settings_loader import load_config, bot
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Test channel for stats
    TEST_CHAT_ID = -1001960832921
    TEST_TOPIC_ID = None

    if IS_TEST_MODE:
        # TEST MODE: Send full digest only to test group
        logger.info("TEST MODE: Sending homebrew digest to test group only")
        try:
            await homebrew_digest_manager.send_digest(
                target_chat_id=TEST_CHAT_ID,
                target_topic_id=TEST_TOPIC_ID,
                since_time=last_run_time
            )
            logger.info("Test homebrew digest sent successfully")
        except Exception as e:
            logger.error(f"Failed to send test homebrew digest: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # PRODUCTION MODE: Send full digest to ALL groups (GROUPS + DIGEST_CHANNEL) + short stats to test channel
        settings_path = os.path.join(current_dir, 'settings.json')
        config = load_config(settings_path)

        if not config:
            logger.error("Could not load settings.json")
            await send_message_to_admin("❌ Could not load settings.json")
            sys.exit(1)

        # Get entries for stats
        entries = homebrew_digest_manager.get_entries_since(last_run_time)
        total_count = len(entries)

        # Count new apps vs updates
        new_count = sum(1 for e in entries if e.get('is_new', False))
        update_count = total_count - new_count

        if total_count == 0:
            logger.info("No homebrew entries for digest period")
            await send_message_to_admin("ℹ️ Homebrew digest: No entries in the period")
            return

        # Collect all target groups (with language info)
        target_groups = []

        # Add GROUPS
        groups = config.get('GROUPS', [])
        for group in groups:
            target_groups.append({
                'name': group.get('group_name', 'Unknown'),
                'chat_id': group.get('chat_id'),
                'topic_id': group.get('topic_id'),
                'language': group.get('language', 'RU')
            })

        # Add DIGEST_CHANNEL if enabled
        digest_config = config.get('DIGEST_CHANNEL')
        if digest_config and digest_config.get('enabled', False):
            target_groups.append({
                'name': digest_config.get('group_name', 'Digest Channel'),
                'chat_id': digest_config.get('chat_id'),
                'topic_id': digest_config.get('topic_id'),
                'language': digest_config.get('language', 'RU')
            })

        if not target_groups:
            logger.error("No target groups configured")
            await send_message_to_admin("❌ No target groups configured for homebrew digest")
            sys.exit(1)

        logger.info(f"PRODUCTION MODE: Sending homebrew digest to {len(target_groups)} groups")

        try:
            sent_count = 0
            for group in target_groups:
                try:
                    chat_id = int(group['chat_id'])
                    topic_id = int(group['topic_id']) if group['topic_id'] and str(group['topic_id']).strip() else None

                    # Use language from config
                    group_lang = group.get('language', 'RU').upper()
                    translate_to_ua = group_lang == 'UA'

                    logger.info(f"Sending homebrew digest to {group['name']} (chat_id: {chat_id}, topic_id: {topic_id}, translate: {translate_to_ua})")

                    await homebrew_digest_manager.send_digest(
                        target_chat_id=chat_id,
                        target_topic_id=topic_id,
                        since_time=last_run_time,
                        translate_to_ua=translate_to_ua
                    )
                    sent_count += 1
                    logger.info(f"Homebrew digest sent to {group['name']}")

                    # Small delay between groups
                    await asyncio.sleep(1)

                except Exception as group_err:
                    logger.error(f"Failed to send homebrew digest to {group['name']}: {group_err}")
                    # Continue with other groups

            logger.info(f"Production homebrew digest sent to {sent_count}/{len(target_groups)} groups")

            # Clear old entries AFTER all groups have been sent
            if sent_count > 0:
                cleanup_time = datetime.now() - timedelta(days=7)
                homebrew_digest_manager.clear_old_entries(cleanup_time)
                logger.info(f"Cleared homebrew entries older than {cleanup_time}")

            # Send short stats to test channel
            stats_message = (
                f"📊 <b>Homebrew дайджест відправлено</b>\n\n"
                f"Нових додатків: {new_count}\n"
                f"Оновлень: {update_count}\n"
                f"Всього: {total_count}\n"
                f"Груп: {sent_count}/{len(target_groups)}"
            )
            await bot.send_message(
                chat_id=TEST_CHAT_ID,
                message_thread_id=TEST_TOPIC_ID,
                text=stats_message,
                parse_mode='HTML'
            )
            logger.info("Homebrew stats sent to test channel")

        except Exception as e:
            logger.error(f"Failed to send homebrew digest: {e}")
            import traceback
            traceback.print_exc()

            try:
                await send_message_to_admin(f"❌ Failed to send homebrew digest: {e}")
            except:
                pass

            sys.exit(1)


async def main():
    log_level = logging.DEBUG if LOG else logging.INFO
    setup_logging(log_level=log_level)

    logger.info("=" * 50)
    logger.info("Starting Homebrew Digest Send")
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: {'TEST' if IS_TEST_MODE else 'PRODUCTION'}")
    logger.info("=" * 50)

    try:
        await send_digest()
    finally:
        await close_clients()


if __name__ == "__main__":
    asyncio.run(main())
