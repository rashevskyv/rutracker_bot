"""
Homebrew Digest Module
Collects and formats daily summaries of homebrew application updates
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio

logger = logging.getLogger(__name__)

HOMEBREW_DIGEST_FILE = "homebrew_digest_data.json"


class HomebrewDigest:
    """Manages homebrew digest data collection and formatting"""

    def __init__(self, data_file: str = HOMEBREW_DIGEST_FILE):
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
            logger.error(f"Error loading homebrew digest data: {e}")
            return {"entries": []}

    def _save_data(self, data: Dict):
        """Save digest data to file"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving homebrew digest data: {e}")

    def add_entry(self, app_name: str, version: str, release_url: str, description: str,
                  platform: str = "3DS/DS(i)/Switch", timestamp: Optional[datetime] = None,
                  is_new: bool = False):
        """
        Add a new homebrew entry to the digest

        Args:
            app_name: Application name (e.g., "xdumptool", "OpenHome")
            version: Version string (e.g., "rewrite-prerelease", "v1.10.5")
            release_url: GitHub release URL
            description: Short description of the app
            platform: Platform category (e.g., "3DS/DS(i)/Switch", "Wii", "Windows/macOS/Linux")
            timestamp: Entry timestamp (defaults to now if not provided)
            is_new: Whether this is a new app (not just an update)
        """
        data = self._load_data()

        entry = {
            "app_name": app_name,
            "version": version,
            "release_url": release_url,
            "description": description,
            "platform": platform,
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "is_new": is_new
        }

        data["entries"].append(entry)
        self._save_data(data)
        logger.info(f"Added homebrew entry to digest: {app_name} {version}{'(NEW)' if is_new else ''}")

    def get_entries_since(self, since_time: datetime) -> List[Dict]:
        """
        Get all entries since a specific time

        Returns:
            List of entries
        """
        data = self._load_data()

        # Make since_time timezone-aware if it's naive
        if since_time.tzinfo is None:
            from datetime import timezone
            since_time = since_time.replace(tzinfo=timezone.utc)

        entries = []
        for entry in data["entries"]:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                # Make entry_time timezone-aware if it's naive
                if entry_time.tzinfo is None:
                    from datetime import timezone
                    entry_time = entry_time.replace(tzinfo=timezone.utc)

                if entry_time >= since_time:
                    entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        return entries

    def clear_old_entries(self, before_time: datetime):
        """Remove entries older than specified time"""
        data = self._load_data()

        # Make before_time timezone-aware if it's naive
        if before_time.tzinfo is None:
            from datetime import timezone
            before_time = before_time.replace(tzinfo=timezone.utc)

        filtered_entries = []
        for entry in data["entries"]:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                # Make entry_time timezone-aware if it's naive
                if entry_time.tzinfo is None:
                    from datetime import timezone
                    entry_time = entry_time.replace(tzinfo=timezone.utc)

                if entry_time >= before_time:
                    filtered_entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        data["entries"] = filtered_entries
        self._save_data(data)
        logger.info(f"Cleared old homebrew entries. Remaining: {len(filtered_entries)}")

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """
        Format homebrew digest message

        Returns:
            Formatted message string or None if no entries
        """
        import html

        entries = self.get_entries_since(since_time)

        if not entries:
            logger.info("No homebrew entries for digest")
            return None

        # Group entries by platform
        platforms = {}
        for entry in entries:
            platform = entry.get('platform', '3DS/DS(i)/Switch')
            if platform not in platforms:
                platforms[platform] = []
            platforms[platform].append(entry)

        message_parts = ["#homebrew_digest:"]
        message_parts.append("")  # Empty line

        # Format entries grouped by platform
        for platform, platform_entries in platforms.items():
            message_parts.append(f"=== {platform} ===")
            for entry in platform_entries:
                app_name = html.escape(entry['app_name'])
                version = html.escape(entry['version'])
                description = entry['description']  # Already contains Telegram HTML, don't escape
                is_new = entry.get('is_new', False)

                # Parse date from timestamp
                try:
                    entry_date = datetime.fromisoformat(entry['timestamp'])
                    date_str = entry_date.strftime('%d.%m.%Y')
                except:
                    date_str = "дата невідома"

                # Format: • <a href="url">AppName version</a> від date — description
                # Add ⚠️ emoji for new apps
                marker = "⚠️ " if is_new else "• "
                line = f"{marker}<a href=\"{entry['release_url']}\">{app_name} {version}</a> від {date_str} — {description}"
                message_parts.append(line)

            message_parts.append("")  # Empty line after each platform section

        # Add link to digest channel at the end
        message_parts.append("📢 <a href=\"https://t.me/Nin3DSBrewNews\">Nin3DSBrewNews</a>")

        return "\n".join(message_parts).rstrip()

    async def send_homebrew_digest(self, target_chat_id: int, target_topic_id: Optional[int] = None,
                                   since_time: Optional[datetime] = None, translate_to_ua: bool = False):
        """
        Send homebrew digest to specified Telegram channel

        Args:
            target_chat_id: Telegram chat ID
            target_topic_id: Optional topic ID for supergroups
            since_time: Optional start time for digest (defaults to last 24 hours)
            translate_to_ua: Whether to translate Russian text to Ukrainian
        """
        from settings_loader import bot
        from telegram_sender import send_message_to_admin

        # Calculate time range
        now = datetime.now()
        if since_time is None:
            since_time = now - timedelta(hours=24)

        logger.info(f"Generating homebrew digest for period: {since_time} to {now}")

        message = self.format_digest_message(since_time)

        if not message:
            logger.info("No entries for homebrew digest")
            await send_message_to_admin("Homebrew digest: No new entries in the specified period")
            return

        # Translate if needed
        if translate_to_ua:
            logger.info(f"Translating homebrew digest to Ukrainian for chat {target_chat_id}")
            try:
                from translation import translate_ru_to_ua
                message = await translate_ru_to_ua(message)
            except Exception as e:
                logger.error(f"Error translating homebrew digest: {e}. Sending in Russian.")

        try:
            await bot.send_message(
                chat_id=target_chat_id,
                message_thread_id=target_topic_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info(f"Homebrew digest sent to {target_chat_id}")

            # Clear old entries (keep last 7 days)
            cleanup_time = now - timedelta(days=7)
            self.clear_old_entries(cleanup_time)
            logger.info(f"Cleared entries older than {cleanup_time}")

        except Exception as e:
            logger.error(f"Error sending homebrew digest: {e}")
            await send_message_to_admin(f"Error sending homebrew digest: {e}")


# Global instance
homebrew_digest_manager = HomebrewDigest()
