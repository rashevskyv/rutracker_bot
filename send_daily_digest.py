"""
Send Daily Digest Script
Sends accumulated daily digest to configured channel
Should be run by cron/scheduler at 9:00 AM daily
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta

from settings_loader import setup_logging, close_clients, LOG, IS_TEST_MODE
from daily_digest import digest_manager
from telegram_sender import send_message_to_admin

logger = logging.getLogger(__name__)


async def send_digest():
    """Send daily digest to configured channel"""

    # Determine target channel based on mode
    if IS_TEST_MODE:
        # Send to test group
        target_chat_id = -1001960832921
        target_topic_id = None
        logger.info("TEST MODE: Sending digest to test group")
    else:
        # Send to production channel
        target_chat_id = -1001188608656  # Nin3DSBrewNews
        target_topic_id = None
        logger.info("PRODUCTION MODE: Sending digest to Nin3DSBrewNews")

    try:
        await digest_manager.send_daily_digest(
            target_chat_id=target_chat_id,
            target_topic_id=target_topic_id
        )
        logger.info("Daily digest sent successfully")

    except Exception as e:
        logger.error(f"Failed to send daily digest: {e}")
        import traceback
        traceback.print_exc()

        # Notify admin about failure
        try:
            await send_message_to_admin(f"❌ Failed to send daily digest: {e}")
        except:
            pass

        sys.exit(1)


async def main():
    # Setup logging
    log_level = logging.DEBUG if LOG else logging.INFO
    setup_logging(log_level=log_level)

    logger.info("=" * 50)
    logger.info("Starting Daily Digest Send")
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: {'TEST' if IS_TEST_MODE else 'PRODUCTION'}")
    logger.info("=" * 50)

    try:
        await send_digest()
    finally:
        await close_clients()


if __name__ == "__main__":
    asyncio.run(main())
