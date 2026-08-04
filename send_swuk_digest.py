"""
Send Swuk Digest Script
Sends accumulated Ukrainian Switch localizations digest to configured channel.
Should be run by cron/scheduler (e.g. daily at 09:00).
Uses the same GROUPS + DIGEST_CHANNEL targets as the homebrew digest.
"""
import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

from core.settings_loader import IS_TEST_MODE, TEST_GROUPS
from digest import runner
from digest.swuk import swuk_digest_manager
from services.telegram_sender import send_message_to_admin

logger = logging.getLogger(__name__)

LAST_RUN_FILE = os.path.join("data", "last_swuk_digest_run.json")


async def send_digest():
    """Send swuk digest to configured channels (same targets as homebrew digest)."""
    last_run_time = runner.get_last_run_time(LAST_RUN_FILE, timedelta(days=7))
    if runner.in_cooldown(last_run_time, 'run_swuk_digest', 'Swuk digest'):
        return

    logger.info(f"Swuk digest period: {last_run_time} to {datetime.now()}")

    entries = swuk_digest_manager.get_entries_since(last_run_time)
    total_count = len(entries)

    if total_count == 0:
        logger.info("No swuk entries for this period")
        await send_message_to_admin("ℹ️ Swuk digest: No new/updated localizations")
        return

    new_count = sum(1 for e in entries if e.get('is_new'))
    update_count = total_count - new_count

    if IS_TEST_MODE:
        logger.info("TEST MODE: Sending swuk digest to test groups only")
        if not TEST_GROUPS:
            logger.error("TEST_GROUPS is not configured.")
            sys.exit(1)
        try:
            test_targets = [{'name': g.get('group_name', 'Unknown'), **g} for g in TEST_GROUPS]
            await runner.send_to_groups(swuk_digest_manager, test_targets, last_run_time, "test swuk digest")
        except Exception as e:
            logger.error(f"Failed to send test swuk digest: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # PRODUCTION MODE: use same GROUPS + DIGEST_CHANNEL as homebrew digest
    from core.settings_loader import bot
    config = await runner.load_settings_or_exit(__file__, "Swuk digest")
    target_groups = runner.collect_target_groups(config)

    if not target_groups:
        logger.error("No target groups configured")
        await send_message_to_admin("❌ Swuk digest: No target groups configured")
        sys.exit(1)

    logger.info(f"PRODUCTION MODE: Sending swuk digest to {len(target_groups)} groups")

    try:
        sent_count = await runner.send_to_groups(swuk_digest_manager, target_groups, last_run_time, "swuk digest")

        if sent_count > 0:
            runner.save_last_run_time(LAST_RUN_FILE)
            swuk_digest_manager.mark_as_sent(last_run_time)
            swuk_digest_manager.clear_old_entries(datetime.now() - timedelta(days=7))

        stats_chat_id, stats_topic_id = runner.stats_target()
        await bot.send_message(
            chat_id=stats_chat_id,
            message_thread_id=stats_topic_id,
            text=(
                f"🇺🇦 <b>Swuk дайджест відправлено</b>\n\n"
                f"Нових локалізацій: {new_count}\n"
                f"Оновлень: {update_count}\n"
                f"Всього: {total_count}\n"
                f"Груп: {sent_count}/{len(target_groups)}"
            ),
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


if __name__ == "__main__":
    asyncio.run(runner.run("Swuk Digest Send", send_digest))
