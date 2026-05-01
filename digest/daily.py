"""
Daily Digest Module for RuTracker Bot
Collects and formats daily summaries of new and updated torrents
"""
import html
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

from digest.base import BaseDigest

logger = logging.getLogger(__name__)

DIGEST_DATA_FILE = os.path.join("data", "daily_digest_data.json")


class DailyDigest(BaseDigest):
    """Manages daily rutracker digest data collection and formatting"""

    def __init__(self, data_file: str = DIGEST_DATA_FILE):
        super().__init__(data_file, digest_name="daily digest")

    def add_entry(self, title: str, entry_url: str, size: str, language: str,
                  is_updated: bool = False, update_description: Optional[str] = None,
                  timestamp: Optional[datetime] = None):
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
        Get all entries since a specific time, grouped by type (new/updated).

        Returns:
            Dict with 'new' and 'updated' lists
        """
        all_entries = super().get_entries_since(since_time)

        new_entries = []
        updated_entries = []

        for entry in all_entries:
            if entry.get("is_updated"):
                updated_entries.append(entry)
            else:
                new_entries.append(entry)

        return {
            "new": new_entries,
            "updated": updated_entries
        }

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """
        Format digest message in the required format

        Returns:
            Formatted message string or None if no entries
        """
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


# Global instance
digest_manager = DailyDigest()
