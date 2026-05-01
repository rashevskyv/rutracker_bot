"""
Homebrew Digest Module
Collects and formats daily summaries of homebrew application updates
"""
import html
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

from digest.base import BaseDigest

logger = logging.getLogger(__name__)

HOMEBREW_DIGEST_FILE = os.path.join("data", "homebrew_digest_data.json")


class HomebrewDigest(BaseDigest):
    """Manages homebrew digest data collection and formatting"""

    def __init__(self, data_file: str = HOMEBREW_DIGEST_FILE):
        super().__init__(data_file, digest_name="homebrew digest")

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

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """
        Format homebrew digest message grouped by platform.

        Returns:
            Formatted message string or None if no entries
        """
        entries = self.get_entries_since(since_time)

        if not entries:
            logger.info("No homebrew entries for digest")
            return None

        # Group entries by platform
        platforms: Dict[str, List[Dict]] = {}
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
                except Exception:
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


# Global instance
homebrew_digest_manager = HomebrewDigest()
