"""
Telethon User Authorization Script
Run this once to authorize and save session
Usage: python telethon_auth.py
"""
import asyncio
import logging
import os

from telethon import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def authorize():
    """Authorize Telethon user session"""

    # Load API credentials
    from settings_loader import load_config

    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_settings_path = os.path.join(current_dir, 'test_settings.json')

    config = load_config(test_settings_path)
    if not config:
        logger.error("Could not load test_settings.json")
        return False

    api_id = config.get('API_ID')
    api_hash = config.get('API_HASH')

    if not api_id or not api_hash:
        logger.error("API_ID and API_HASH not found in test_settings.json")
        return False

    # Create session file
    session_file = os.path.join(current_dir, 'telethon_user_session')

    print("\n" + "="*60)
    print("TELETHON USER AUTHORIZATION")
    print("="*60)
    print("\nThis will create a session file for future use.")
    print("You will need to enter:")
    print("  1. Your phone number (with country code, e.g., +380...)")
    print("  2. Verification code from Telegram")
    print("  3. 2FA password (if enabled)")
    print("\n" + "="*60 + "\n")

    client = TelegramClient(session_file, api_id, api_hash)

    try:
        # Start client (will ask for phone and code)
        await client.start()

        # Get current user info
        me = await client.get_me()
        logger.info(f"✓ Successfully authorized as: {me.first_name} (@{me.username})")
        logger.info(f"✓ Session saved to: {session_file}.session")

        print("\n" + "="*60)
        print("✓ AUTHORIZATION SUCCESSFUL")
        print(f"User: {me.first_name} (@{me.username})")
        print(f"Session file: {session_file}.session")
        print("\nYou can now use telethon_user_extract.py without re-entering credentials")
        print("="*60 + "\n")

        return True

    except Exception as e:
        logger.error(f"Authorization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.disconnect()


async def main():
    success = await authorize()
    if not success:
        print("\n✗ Authorization failed. Please try again.")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
