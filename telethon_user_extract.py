"""
Extract digest data from Telegram using Telethon with user session
This will ask for phone number and verification code
Usage: python telethon_user_extract.py --chat-id -1001277664260 --topic-id 29459 --from-date 2026-04-25 --to-date 2026-04-30
"""
import asyncio
import argparse
import logging
from datetime import datetime
import re
import os

from telethon import TelegramClient
from telethon.tl.types import Message
from daily_digest import digest_manager
from tracker_parser import get_last_post_with_phrase

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> datetime:
    """Parse date string in format YYYY-MM-DD to datetime"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD") from e


def extract_game_info_from_message(message: Message) -> dict:
    """Extract game title, size, language, and URL from Telegram message"""

    if not message.text:
        return None

    text = message.text

    # Extract URL from entities
    url = None
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url:
                url = entity.url
                break

    # If no entity URL, search in text
    if not url:
        url_match = re.search(r'https://rutracker\.org/forum/viewtopic\.php\?t=\d+', text)
        if url_match:
            url = url_match.group(0)

    if not url or 'rutracker.org' not in url:
        return None  # Skip messages without RuTracker links

    # Extract title (first line)
    lines = text.split('\n')
    title_line = lines[0] if lines else ""

    # Check if it's an update
    is_updated = "[Обновлено]" in title_line or "Обновлено" in title_line

    # Clean title
    title = re.sub(r'\[Обновлено\]\s*', '', title_line, flags=re.IGNORECASE)
    title = re.sub(r'<[^>]+>', '', title)  # Remove HTML
    # Remove trailer link and everything after it
    title = re.sub(r'\s*\|.*$', '', title)

    # Extract format and language info before removing them for validation
    format_lang_match = re.search(r'\[(NSZ|NSP|XCI)\]', title, re.IGNORECASE)

    # Remove markdown formatting (**, __, etc.)
    title = re.sub(r'\*\*\*\*|\*\*|__', '', title)

    # Remove markdown link brackets if present (e.g., [Title](url) -> Title)
    title = re.sub(r'\[(.+?)\]\(https?://[^\)]+\)', r'\1', title)

    # Remove any remaining brackets at start/end (but keep [NSZ][ENG] in the middle)
    title = re.sub(r'^\s*\[(?![A-Z]{3}\])', '', title)
    title = title.strip()

    # Filter out non-game posts (must have had format markers)
    if not format_lang_match:
        return None

    if not title or len(title) < 10:
        return None

    # Extract size
    size = "N/A"
    size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|МБ|MB|ГБ))', text, re.IGNORECASE)
    if size_match:
        size = size_match.group(1)

    # Extract language
    language = "N/A"
    lang_patterns = [
        r'Язык(?:\s+интерфейса)?[:\s]+([^\n]+)',
        r'Language[:\s]+([^\n]+)',
        r'Мова[:\s]+([^\n]+)',
    ]
    for pattern in lang_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lang_text = match.group(1).strip()
            # Remove HTML tags and markdown
            lang_text = re.sub(r'<[^>]+>', '', lang_text)
            lang_text = re.sub(r'\*\*', '', lang_text)
            # Remove "интерфейса:" prefix if present
            lang_text = re.sub(r'^интерфейса:\s*', '', lang_text, flags=re.IGNORECASE)
            language = lang_text[:30]
            break

    # Extract update description from current message
    update_description = None
    if is_updated:
        # Look for **Обновлено:** with markdown formatting and optional link
        # Take everything after "Обновлено:" until the end of message
        update_match = re.search(r'\*\*Обновлено:\*\*\s*(?:\[Details\]\([^\)]+\)\s*)?(.+)', text, re.DOTALL | re.IGNORECASE)
        if update_match:
            update_text = update_match.group(1).strip()
            # Remove markdown formatting
            update_text = re.sub(r'\*\*', '', update_text)
            update_text = re.sub(r'\s+', ' ', update_text)
            update_description = update_text[:200]

    return {
        'title': title,
        'url': url,
        'size': size,
        'language': language,
        'is_updated': is_updated,
        'update_description': update_description
    }


async def extract_from_telegram(api_id: int, api_hash: str, chat_id: int, topic_id: int, from_date: datetime, to_date: datetime):
    """Extract digest data from Telegram using Telethon with user session"""

    logger.info(f"Connecting to Telegram as user...")
    logger.info(f"Chat: {chat_id}, Topic: {topic_id}")
    logger.info(f"Date range: {from_date} to {to_date}")

    # Create session file
    session_file = os.path.join(os.path.dirname(__file__), 'telethon_user_session')

    client = TelegramClient(session_file, api_id, api_hash)

    try:
        # Start with user session (will ask for phone and code)
        await client.start()
        logger.info("Connected to Telegram as user")

        # Get the channel entity first
        try:
            channel = await client.get_entity(chat_id)
            logger.info(f"Found channel: {channel.title if hasattr(channel, 'title') else chat_id}")
        except Exception as e:
            logger.error(f"Could not get channel entity: {e}")
            logger.info("Trying to get channel by username or link...")
            # If direct ID doesn't work, user needs to be in the channel
            return False

        # Get messages from the chat
        messages = []

        logger.info("Fetching messages...")

        # Iterate through messages (get all recent messages, filter by date)
        # If topic_id is specified, use it as reply_to parameter to get messages from that topic
        async for message in client.iter_messages(
            channel,
            limit=None,
            reply_to=topic_id if topic_id else None
        ):
            if not message.date:
                continue

            # Convert to naive datetime for comparison
            msg_date = message.date.replace(tzinfo=None)

            # Stop if we've gone past the from_date (messages are newest first)
            if msg_date < from_date:
                break

            # Skip if message is after to_date
            if msg_date >= to_date:
                continue

            messages.append(message)

        logger.info(f"Found {len(messages)} messages in date range")

        # Process messages (reverse to go chronologically)
        messages.reverse()
        processed_count = 0
        skipped_count = 0

        for i, message in enumerate(messages):
            try:
                game_info = extract_game_info_from_message(message)

                if not game_info:
                    skipped_count += 1
                    continue

                # If this is an updated game but no update_description in the main post,
                # check the next message for "Обновлено:" section
                if game_info['is_updated'] and not game_info['update_description']:
                    # First, try next message in topic
                    if i + 1 < len(messages):
                        next_message = messages[i + 1]
                        # In topic, messages go sequentially - no need to check ID
                        # Try to get text from message or caption
                        next_text = next_message.text or next_message.message or (next_message.caption if hasattr(next_message, 'caption') else None)

                        if next_text:
                            # Look for "Обновлено:" (with or without markdown)
                            # Take everything after "Обновлено:" until the end of message
                            update_match = re.search(r'\*?\*?Обновлено:\*?\*?\s*(?:\[Details\]\([^\)]+\)\s*)?(.+)', next_text, re.DOTALL | re.IGNORECASE)
                            if update_match:
                                update_text = update_match.group(1).strip()
                                # Remove markdown formatting
                                update_text = re.sub(r'\*\*', '', update_text)
                                update_text = re.sub(r'\s+', ' ', update_text)
                                game_info['update_description'] = update_text[:200]
                                logger.debug(f"Found update description in next message for: {game_info['title'][:50]}")

                    # If still no description, try RuTracker
                    if not game_info['update_description']:
                        logger.info(f"Searching RuTracker for update description: {game_info['title'][:50]}")
                        try:
                            rutracker_result = await get_last_post_with_phrase("Раздача обновлена", game_info['url'])
                            if rutracker_result:
                                # Extract text from HTML result (remove <b>Обновлено:</b> and <a> tags)
                                rutracker_text = re.sub(r'<b>Обновлено:</b>\s*', '', rutracker_result)
                                rutracker_text = re.sub(r'<a[^>]*>Details</a>', '', rutracker_text)
                                rutracker_text = re.sub(r'<[^>]+>', '', rutracker_text)
                                rutracker_text = rutracker_text.strip()
                                rutracker_text = re.sub(r'\s+', ' ', rutracker_text)
                                game_info['update_description'] = rutracker_text[:200]
                                logger.info(f"Found update description on RuTracker for: {game_info['title'][:50]}")
                        except Exception as rt_err:
                            logger.warning(f"RuTracker search failed for {game_info['title'][:50]}: {rt_err}")

                # Add to digest (even if no update_description for updated games)
                digest_manager.add_entry(
                    title=game_info['title'],
                    entry_url=game_info['url'],
                    size=game_info['size'],
                    language=game_info['language'],
                    is_updated=game_info['is_updated'],
                    update_description=game_info['update_description'],
                    timestamp=message.date.replace(tzinfo=None)
                )

                processed_count += 1
                logger.info(f"✓ Added: {game_info['title']}")

            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
                skipped_count += 1

        logger.info(f"Extraction complete: {processed_count} added, {skipped_count} skipped")
        return True

    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.disconnect()


async def main():
    parser = argparse.ArgumentParser(description='Extract digest data from Telegram using user session')
    parser.add_argument('--chat-id', required=True, type=int, help='Chat ID')
    parser.add_argument('--topic-id', type=int, help='Topic ID (optional)')
    parser.add_argument('--from-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', required=True, help='End date (YYYY-MM-DD)')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load API credentials
    from settings_loader import load_config
    import os

    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_settings_path = os.path.join(current_dir, 'test_settings.json')

    config = load_config(test_settings_path)
    if not config:
        logger.error("Could not load test_settings.json")
        return

    api_id = config.get('API_ID')
    api_hash = config.get('API_HASH')

    if not api_id or not api_hash:
        logger.error("API_ID and API_HASH not found in test_settings.json")
        return

    try:
        from_date = parse_date(args.from_date)
        to_date = parse_date(args.to_date)

        if from_date >= to_date:
            logger.error("from-date must be before to-date")
            return

        print("\n" + "="*60)
        print("TELETHON USER SESSION")
        print("You will be asked to enter your phone number and verification code")
        print("="*60 + "\n")

        success = await extract_from_telegram(
            api_id,
            api_hash,
            args.chat_id,
            args.topic_id,
            from_date,
            to_date
        )

        if success:
            logger.info("✓ Successfully extracted data from Telegram")
        else:
            logger.error("✗ Failed to extract data")

    except ValueError as e:
        logger.error(str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
