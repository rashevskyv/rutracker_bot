"""
Daily Digest Module for RuTracker Bot
Collects and formats daily summaries of new and updated torrents
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio

logger = logging.getLogger(__name__)

DIGEST_DATA_FILE = "daily_digest_data.json"


class DailyDigest:
    """Manages daily digest data collection and formatting"""

    def __init__(self, data_file: str = DIGEST_DATA_FILE):
        self.data_file = data_file
        self.current_directory = os.path.dirname(os.path.abspath(__file__))
        self.data_path = os.path.join(self.current_directory, data_file)

    def _load_data(self) -> Dict:
        """Load existing digest data from file"""
        if not os.path.exists(self.data_path):
            return {"entries": []}

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading digest data: {e}")
            return {"entries": []}

    def _save_data(self, data: Dict):
        """Save digest data to file"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving digest data: {e}")

    def add_entry(self, title: str, entry_url: str, size: str, language: str, is_updated: bool = False, update_description: Optional[str] = None, timestamp: Optional[datetime] = None):
        """
        Add a new entry to the daily digest

        Args:
            title: Game title (without HTML tags)
            entry_url: RuTracker link
            size: Torrent size (e.g., "2.13 ГБ")
            language: Language code (e.g., "ENG", "RUS")
            is_updated: True if this is an update, False if new
            update_description: Description of what was updated (for updated entries)
            timestamp: Entry timestamp (defaults to now if not provided)
        """
        data = self._load_data()

        entry = {
            "title": title,
            "url": entry_url,
            "size": size,
            "language": language,
            "is_updated": is_updated,
            "update_description": update_description,
            "timestamp": (timestamp or datetime.now()).isoformat()
        }

        data["entries"].append(entry)
        self._save_data(data)
        logger.info(f"Added {'updated' if is_updated else 'new'} entry to digest: {title}")

    def get_entries_since(self, since_time: datetime) -> Dict[str, List[Dict]]:
        """
        Get all entries since a specific time, grouped by type

        Returns:
            Dict with 'new' and 'updated' lists
        """
        data = self._load_data()

        new_entries = []
        updated_entries = []

        for entry in data["entries"]:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time >= since_time:
                    if entry["is_updated"]:
                        updated_entries.append(entry)
                    else:
                        new_entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        return {
            "new": new_entries,
            "updated": updated_entries
        }

    def clear_old_entries(self, before_time: datetime):
        """Remove entries older than specified time"""
        data = self._load_data()

        filtered_entries = []
        for entry in data["entries"]:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time >= before_time:
                    filtered_entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        data["entries"] = filtered_entries
        self._save_data(data)
        logger.info(f"Cleared old entries. Remaining: {len(filtered_entries)}")

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """
        Format digest message in the required format

        Returns:
            Formatted message string or None if no entries
        """
        import html

        entries = self.get_entries_since(since_time)

        new_entries = entries["new"]
        updated_entries = entries["updated"]

        if not new_entries and not updated_entries:
            logger.info("No entries for digest")
            return None

        message_parts = ["#rutracker_digest:"]

        # Format new entries
        if new_entries:
            message_parts.append("")  # Empty line before section
            message_parts.append("=== Добавлены ===")
            message_parts.append("")  # Empty line after section
            for entry in new_entries:
                title_escaped = html.escape(entry['title'])
                # Use invisible link format to avoid URL display
                line = f"• <a href=\"{entry['url']}\">{title_escaped}</a>&#8203; [{entry['size']}]"
                message_parts.append(line)

        # Format updated entries
        if updated_entries:
            message_parts.append("")  # Empty line before section
            message_parts.append("=== Обновлены ===")
            message_parts.append("")  # Empty line after section
            for entry in updated_entries:
                title_escaped = html.escape(entry['title'])
                # Use update_description if available, otherwise generic text
                update_text = entry.get('update_description', 'добавлен апдейт')
                line = f"• <a href=\"{entry['url']}\">{title_escaped}</a>&#8203; — {update_text}"
                message_parts.append(line)

        # Add link to digest channel at the end
        message_parts.append("")  # Empty line before link
        message_parts.append("📢 <a href=\"https://t.me/Nin3DSBrewNews\">Nin3DSBrewNews</a>")

        return "\n".join(message_parts)

    async def send_daily_digest(self, target_chat_id: int, target_topic_id: Optional[int] = None, since_time: Optional[datetime] = None, translate_to_ua: bool = False):
        """
        Send daily digest to specified Telegram channel

        Args:
            target_chat_id: Telegram chat ID
            target_topic_id: Optional topic ID for supergroups
            since_time: Optional start time for digest (defaults to last 24 hours)
            translate_to_ua: Whether to translate Russian text to Ukrainian
        """
        from settings_loader import bot
        from telegram_sender import send_message_to_admin

        # Calculate time range (last 24 hours from 9:00 to 9:00, or custom range)
        now = datetime.now()
        if since_time is None:
            since_time = now - timedelta(hours=24)

        logger.info(f"Generating daily digest for period: {since_time} to {now}")

        message = self.format_digest_message(since_time)

        if not message:
            logger.info("No entries for daily digest")
            await send_message_to_admin("Daily digest: No new entries in the specified period")
            return

        # Translate if needed
        if translate_to_ua:
            logger.info(f"Translating digest to Ukrainian for chat {target_chat_id}")
            try:
                from translation import translate_ru_to_ua
                message = await translate_ru_to_ua(message)
            except Exception as e:
                logger.error(f"Error translating digest: {e}. Sending in Russian.")

        # Clean up ###GAP### markers (convert to double newlines)
        import re
        message = re.sub(r'(?:\s*###GAP###\s*)+', '\n\n', message)
        message = re.sub(r'###\s*-\s*', '', message)  # Remove stray ### markers

        try:
            await bot.send_message(
                chat_id=target_chat_id,
                message_thread_id=target_topic_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info(f"Daily digest sent to {target_chat_id}")

            # Clear old entries (keep last 7 days for safety)
            # This prevents data loss during testing and allows re-sending digests if needed
            cleanup_time = now - timedelta(days=7)
            self.clear_old_entries(cleanup_time)

        except Exception as e:
            logger.error(f"Error sending daily digest: {e}")
            await send_message_to_admin(f"Error sending daily digest: {e}")


# Global instance
digest_manager = DailyDigest()
