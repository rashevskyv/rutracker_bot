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
                  platform: str = "Switch", timestamp: Optional[datetime] = None,
                  release_date: Optional[datetime] = None, is_new: bool = False):
        """
        Add a new homebrew entry to the digest

        Args:
            app_name: Application name (e.g., "xdumptool", "OpenHome")
            version: Version string (e.g., "rewrite-prerelease", "v1.10.5")
            release_url: GitHub release URL
            description: Short description of the app
            platform: Platform category (e.g., "3DS/DS(i)/Switch", "Wii", "Windows/macOS/Linux")
            timestamp: Entry discovery timestamp (defaults to now if not provided)
            release_date: Original GitHub release date for display
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
            "release_date": (release_date or datetime.now()).isoformat(),
            "is_new": is_new
        }

        # Dedup: replace existing entry with same release URL
        replaced = False
        for i, existing in enumerate(data["entries"]):
            if existing.get("release_url") == release_url:
                # Preserve the is_new flag if the existing entry was new
                if existing.get("is_new"):
                    entry["is_new"] = True
                
                # If version and app_name are the same, preserve original discovery timestamp
                # This prevents entry from reappearing in digests if re-added with same info
                if existing.get("version") == version and existing.get("app_name") == app_name:
                    entry["timestamp"] = existing.get("timestamp", entry["timestamp"])
                    logger.debug(f"Preserving timestamp for unchanged entry: {app_name} {version}")

                data["entries"][i] = entry
                replaced = True
                logger.info(f"Updated existing homebrew digest entry: {app_name} {version}")
                break

        if not replaced:
            data["entries"].append(entry)
            logger.info(f"Added homebrew entry to digest: {app_name} {version}{' (NEW)' if is_new else ''}")

        self._save_data(data)

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

        # Deduplicate by release_url (safety net against data file duplicates)
        seen_urls = set()
        unique_entries = []
        for entry in entries:
            url = entry.get('release_url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_entries.append(entry)
        if len(unique_entries) < len(entries):
            logger.warning(f"Removed {len(entries) - len(unique_entries)} duplicate entries from digest output")
        entries = unique_entries

        # Group entries by platform
        platforms: Dict[str, List[Dict]] = {}
        for entry in entries:
            platform_str = entry.get('platform', 'Switch')
            sub_platforms = [p.strip() for p in platform_str.split('/') if p.strip()]
            for p in sub_platforms:
                if p == 'DS':
                    p = 'DS(i)'
                if p not in platforms:
                    platforms[p] = []
                if entry not in platforms[p]:
                    platforms[p].append(entry)

        message_parts = ["#homebrew_digest:"]
        message_parts.append("")  # Empty line

        # Format entries grouped by platform
        for platform, platform_entries in platforms.items():
            message_parts.append(f"=== {platform} ===")
            for entry in sorted(platform_entries, key=lambda e: e['app_name'].lower()):
                app_name = html.escape(entry['app_name'])
                version = html.escape(entry['version'])
                description = entry['description']  # Already contains Telegram HTML, don't escape
                is_new = entry.get('is_new', False)

                # Parse date from timestamp
                try:
                    entry_date = datetime.fromisoformat(entry.get('release_date', entry['timestamp']))
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

    def mark_as_sent(self, since_time: datetime):
        """
        Mark all entries included in the digest (timestamp >= since_time) as no longer new.
        """
        data = self._load_data()
        since_time = self._normalize_time(since_time)
        updated_count = 0

        for entry in data["entries"]:
            try:
                entry_time = self._normalize_time(datetime.fromisoformat(entry["timestamp"]))
                if entry_time >= since_time and entry.get("is_new"):
                    entry["is_new"] = False
                    updated_count += 1
            except Exception as e:
                logger.error(f"Error parsing entry timestamp during mark_as_sent: {e}")

        if updated_count > 0:
            self._save_data(data)
            logger.info(f"Marked {updated_count} homebrew entries as no longer new")


# Global instance
homebrew_digest_manager = HomebrewDigest()
