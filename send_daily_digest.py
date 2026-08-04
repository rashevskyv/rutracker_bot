"""
Send Daily Digest Script
Sends accumulated daily digest to configured channel
Should be run by cron/scheduler at 9:00 AM daily
"""
import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

from core.settings_loader import IS_TEST_MODE, TEST_GROUPS
from digest import runner
from digest.daily import digest_manager
from services.telegram_sender import send_message_to_admin
from services.manual_releases import process_manual_releases

logger = logging.getLogger(__name__)

LAST_RUN_FILE = os.path.join("data", "last_digest_run.json")


def _translate_for(group: dict) -> bool:
    return group.get('language', 'RU').upper() == 'UA'


async def send_digest():
    """Send daily digest to configured channel"""
    last_run_time = runner.get_last_run_time(LAST_RUN_FILE, timedelta(hours=24))
    if runner.in_cooldown(last_run_time, 'run_daily_digest', 'Daily digest'):
        return

    logger.info(f"Digest period: {last_run_time} to {datetime.now()}")

    # Process manual releases before sending digest
    manual_count = process_manual_releases(release_type='game')
    if manual_count > 0:
        logger.info(f"Added {manual_count} manual releases to digest")

    if IS_TEST_MODE:
        # TEST MODE: Send full digest to all test groups
        logger.info("TEST MODE: Sending full digest to test groups only")
        if not TEST_GROUPS:
            logger.error("TEST_GROUPS is not configured.")
            sys.exit(1)
        try:
            test_targets = [{'name': g.get('group_name', 'Unknown'), **g} for g in TEST_GROUPS]
            await runner.send_to_groups(digest_manager, test_targets, last_run_time,
                                        "test digest", translate=_translate_for)
        except Exception as e:
            logger.error(f"Failed to send test digest: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # PRODUCTION MODE: full digest to GROUPS + DIGEST_CHANNEL, short stats to test channel
    from core.settings_loader import bot
    config = await runner.load_settings_or_exit(__file__, "Daily digest")

    entries = digest_manager.get_entries_since(last_run_time)
    new_count = len(entries['new'])
    updated_count = len(entries['updated'])
    total_count = new_count + updated_count

    if total_count == 0:
        logger.info("No entries for digest period")
        await send_message_to_admin("ℹ️ Daily digest: No entries in the period")
        return

    target_groups = runner.collect_target_groups(config)
    if not target_groups:
        logger.error("No target groups configured")
        await send_message_to_admin("❌ No target groups configured for digest")
        sys.exit(1)

    logger.info(f"PRODUCTION MODE: Sending digest to {len(target_groups)} groups")

    try:
        sent_count = await runner.send_to_groups(digest_manager, target_groups, last_run_time,
                                                 "digest", translate=_translate_for)

        # Clear old entries AFTER all groups have been sent
        if sent_count > 0:
            runner.save_last_run_time(LAST_RUN_FILE)
            cleanup_time = datetime.now() - timedelta(days=7)
            digest_manager.clear_old_entries(cleanup_time)
            logger.info(f"Cleared digest entries older than {cleanup_time}")

        # Count pending manual releases
        pending_count = 0
        try:
            from services.manual_releases import load_manual_releases
            pending_count = sum(1 for e in load_manual_releases() if not e.get('processed', False))
        except Exception as e:
            logger.error(f"Error counting pending manual releases for stats: {e}")

        stats_chat_id, stats_topic_id = runner.stats_target()
        await bot.send_message(
            chat_id=stats_chat_id,
            message_thread_id=stats_topic_id,
            text=(
                f"📊 <b>Дайджест відправлено</b>\n\n"
                f"Нових ігор: {new_count}\n"
                f"Оновлень: {updated_count}\n"
                f"Ручних релізів: {manual_count} (в черзі: {pending_count})\n"
                f"Всього: {total_count}\n"
                f"Груп: {sent_count}/{len(target_groups)}"
            ),
            parse_mode='HTML'
        )
        logger.info("Stats sent to test channel")

    except Exception as e:
        logger.error(f"Failed to send daily digest: {e}")
        import traceback
        traceback.print_exc()
        try:
            await send_message_to_admin(f"❌ Failed to send daily digest: {e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(runner.run("Daily Digest Send", send_digest))
