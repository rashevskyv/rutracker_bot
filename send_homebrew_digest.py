"""
Send Homebrew Digest Script
Sends accumulated homebrew digest to configured channel
Should be run by cron/scheduler at 9:00 AM daily
"""
import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timedelta

from core.settings_loader import IS_TEST_MODE, TEST_GROUPS
from digest import runner
from digest.homebrew import homebrew_digest_manager
from services.telegram_sender import send_message_to_admin
from services.manual_releases import process_manual_releases

logger = logging.getLogger(__name__)

LAST_RUN_FILE = os.path.join("data", "last_homebrew_digest_run.json")
HB_STATS_FILE = os.path.join("data", "hb_collect_stats.json")
SWUK_STATS_FILE = os.path.join("data", "swuk_collect_stats.json")


def build_stats_text(manual_count: int = 0) -> str:
    """Build a per-source stats block from the last collector run files."""
    lines = ["\n\n📋 <b>Статистика збору:</b>"]

    # Count pending manual releases
    pending_count = 0
    try:
        from services.manual_releases import load_manual_releases
        pending_count = sum(1 for e in load_manual_releases() if not e.get('processed', False))
    except Exception as e:
        logger.error(f"Error counting pending manual releases for stats: {e}")

    # Manual releases
    emoji_manual = "📌" if (manual_count > 0 or pending_count > 0) else "➖"
    lines.append(f"{emoji_manual} Ручні релізи: додано {manual_count} (в черзі: {pending_count})")

    # Homebrew sources
    try:
        with open(HB_STATS_FILE, encoding='utf-8') as f:
            hb_stats = json.load(f)
        for source, s in hb_stats.items():
            if s.get('error'):
                error_desc = f" ({s.get('error_msg')})" if s.get('error_msg') else ""
                lines.append(f"⚠️ {source}: помилка збору{error_desc}")
            else:
                emoji = "✅" if s['found'] > 0 else "➖"
                lines.append(f"{emoji} {source}: перевірено {s['checked']}, знайдено {s['found']}")
    except FileNotFoundError:
        lines.append("➖ Homebrew: немає даних (колектор ще не запускався)")
    except Exception as e:
        lines.append(f"⚠️ Помилка читання homebrew stats: {e}")

    # SWUK source
    try:
        with open(SWUK_STATS_FILE, encoding='utf-8') as f:
            swuk = json.load(f)
        emoji = "✅" if swuk['found'] > 0 else "➖"
        lines.append(f"{emoji} SWUK (Switch UA): перевірено {swuk['checked']}, знайдено {swuk['found']}")
    except FileNotFoundError:
        lines.append("➖ SWUK: немає даних")
    except Exception as e:
        lines.append(f"⚠️ Помилка читання SWUK stats: {e}")

    return "\n".join(lines)


async def send_digest():
    """Send homebrew digest to configured channel"""
    last_run_time = runner.get_last_run_time(LAST_RUN_FILE, timedelta(days=7))
    if runner.in_cooldown(last_run_time, 'run_homebrew_digest', 'Homebrew digest'):
        return

    logger.info(f"Homebrew digest period: {last_run_time} to {datetime.now()}")

    # Process manual releases before sending digest
    manual_count = process_manual_releases(release_type='homebrew')
    if manual_count > 0:
        logger.info(f"Added {manual_count} manual releases to digest")

    from core.settings_loader import bot

    if IS_TEST_MODE:
        # TEST MODE: Send full digest to all test groups
        logger.info("TEST MODE: Sending homebrew digest to test groups only")
        if not TEST_GROUPS:
            logger.error("TEST_GROUPS is not configured.")
            sys.exit(1)
        try:
            for group in TEST_GROUPS:
                chat_id = int(group['chat_id'])
                topic_id = runner.parse_topic_id(group.get('topic_id'))
                translate_to_ua = group.get('language', 'RU').upper() == 'UA'

                logger.info(f"Sending test homebrew digest to {group.get('group_name', 'Unknown')} "
                            f"(chat_id: {chat_id}, topic_id: {topic_id}, translate: {translate_to_ua})")
                await homebrew_digest_manager.send_digest(
                    target_chat_id=chat_id,
                    target_topic_id=topic_id,
                    since_time=last_run_time,
                    translate_to_ua=translate_to_ua
                )

                # Send stats report to each test channel
                await bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    text=f"📊 <b>Тест-дайджест відправлено</b>{build_stats_text(manual_count)}",
                    parse_mode='HTML'
                )
            logger.info("Test homebrew digests sent successfully")
        except Exception as e:
            logger.error(f"Failed to send test homebrew digest: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # PRODUCTION MODE: full digest to GROUPS + DIGEST_CHANNEL, short stats to test channel
    config = await runner.load_settings_or_exit(__file__, "Homebrew digest")

    entries = homebrew_digest_manager.get_entries_since(last_run_time)
    total_count = len(entries)
    new_count = sum(1 for e in entries if e.get('is_new', False))
    update_count = total_count - new_count

    if total_count == 0:
        logger.info("No homebrew entries for digest period")
        await send_message_to_admin("ℹ️ Homebrew digest: No entries in the period")
        return

    target_groups = runner.collect_target_groups(config)
    if not target_groups:
        logger.error("No target groups configured")
        await send_message_to_admin("❌ No target groups configured for homebrew digest")
        sys.exit(1)

    logger.info(f"PRODUCTION MODE: Sending homebrew digest to {len(target_groups)} groups")

    try:
        # Homebrew descriptions are already in Ukrainian — no re-translation needed
        sent_count = await runner.send_to_groups(homebrew_digest_manager, target_groups, last_run_time,
                                                 "homebrew digest", translate=lambda g: False)

        # Clear old entries AFTER all groups have been sent
        if sent_count > 0:
            runner.save_last_run_time(LAST_RUN_FILE)
            # Mark included entries as no longer new
            homebrew_digest_manager.mark_as_sent(last_run_time)
            cleanup_time = datetime.now() - timedelta(days=7)
            homebrew_digest_manager.clear_old_entries(cleanup_time)
            logger.info(f"Cleared homebrew entries older than {cleanup_time}")

        stats_chat_id, stats_topic_id = runner.stats_target()
        await bot.send_message(
            chat_id=stats_chat_id,
            message_thread_id=stats_topic_id,
            text=(
                f"📊 <b>Homebrew дайджест відправлено</b>\n\n"
                f"Нових додатків: {new_count}\n"
                f"Оновлень: {update_count}\n"
                f"Ручних релізів: {manual_count}\n"
                f"Всього: {total_count}\n"
                f"Груп: {sent_count}/{len(target_groups)}"
                f"{build_stats_text(manual_count)}"
            ),
            parse_mode='HTML'
        )
        logger.info("Homebrew stats sent to test channel")

    except Exception as e:
        logger.error(f"Failed to send homebrew digest: {e}")
        import traceback
        traceback.print_exc()
        try:
            await send_message_to_admin(f"❌ Failed to send homebrew digest: {e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(runner.run("Homebrew Digest Send", send_digest))
