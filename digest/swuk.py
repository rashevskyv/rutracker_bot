"""
Swuk Digest Module
Collects and formats Ukrainian Switch localizations from swuk.com.ua
"""
import html
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

from digest.base import BaseDigest

logger = logging.getLogger(__name__)

SWUK_DIGEST_FILE = os.path.join("data", "swuk_digest_data.json")


class SwukDigest(BaseDigest):
    """Manages Ukrainian localizations digest from swuk.com.ua"""

    def __init__(self, data_file: str = SWUK_DIGEST_FILE):
        super().__init__(data_file, digest_name="swuk digest")

    def add_entry(self, game_name: str, release_url: str, description: str,
                  is_new: bool = True, timestamp: Optional[datetime] = None,
                  versions: Optional[List[str]] = None, modified_date: Optional[str] = None):
        """
        Add or update a localization entry.

        Args:
            game_name: Clean game title (without [НОВИНКА]/[ОНОВЛЕНО] prefix)
            release_url: URL of the swuk.com.ua game page (used as unique key)
            description: Game description (already Ukrainian, from RSS <description>)
            is_new: True for new localizations, False for updates
            timestamp: Discovery timestamp (defaults to now)
            versions: List of game versions supported (e.g., ["1.0.0", "1.3.1"])
            modified_date: Readable update date from guid modified timestamp (e.g. "03.05.2026")
        """
        data = self._load_data()

        entry = {
            "app_name": game_name,
            "release_url": release_url,
            "description": description,
            "is_new": is_new,
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "versions": versions or [],
            "modified_date": modified_date,
        }

        # Dedup by release_url
        replaced = False
        for i, existing in enumerate(data["entries"]):
            if existing.get("release_url") == release_url:
                # Preserve is_new if it was marked new before
                if existing.get("is_new"):
                    entry["is_new"] = True
                # If we don't have new versions/date but existing has them, keep them
                if not entry["versions"] and existing.get("versions"):
                    entry["versions"] = existing.get("versions")
                if not entry["modified_date"] and existing.get("modified_date"):
                    entry["modified_date"] = existing.get("modified_date")
                data["entries"][i] = entry
                replaced = True
                logger.info(f"Updated swuk digest entry: {game_name}")
                break

        if not replaced:
            data["entries"].append(entry)
            logger.info(f"Added swuk entry: {game_name} {'(NEW)' if is_new else '(UPDATE)'}")

        self._save_data(data)

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """Format localization digest message split into new / updated sections."""
        entries = self.get_entries_since(since_time)
        if not entries:
            return None

        # Deduplicate by URL (safety net)
        seen: set = set()
        unique: List[Dict] = []
        for e in entries:
            url = e.get("release_url", "")
            if url not in seen:
                seen.add(url)
                unique.append(e)
        entries = unique

        new_entries = sorted(
            [e for e in entries if e.get("is_new")],
            key=lambda x: x["app_name"].lower()
        )
        updated_entries = sorted(
            [e for e in entries if not e.get("is_new")],
            key=lambda x: x["app_name"].lower()
        )

        parts = ["#swuk", "🇺🇦 <b>Switch Українською</b>", ""]

        def _format_entry_line(e: Dict) -> str:
            name = html.escape(e["app_name"])
            desc = e.get("description", "")
            
            # Format versions nicely (e.g. "v1.0.0, v1.3.1")
            version_str = ""
            e_versions = e.get("versions", [])
            if e_versions:
                formatted_v = [f"v{v}" if not v.lower().startswith('v') else v for v in e_versions]
                version_str = f" ({', '.join(formatted_v)})"
            
            # Format update date (e.g. "[03.05.2026]")
            date_str = ""
            e_date = e.get("modified_date")
            if e_date:
                date_str = f" [{e_date}]"
                
            return f"• <a href=\"{e['release_url']}\">{name}</a>{version_str}{date_str} — {desc}"

        if new_entries:
            parts.append("⚠️ <b>Нові локалізації:</b>")
            for e in new_entries:
                parts.append(_format_entry_line(e))
            parts.append("")

        if updated_entries:
            parts.append("🔄 <b>Оновлені локалізації:</b>")
            for e in updated_entries:
                parts.append(_format_entry_line(e))
            parts.append("")

        parts.append("📢 <a href=\"https://swuk.com.ua\">swuk.com.ua</a>")

        return "\n".join(parts).rstrip()

    def mark_as_sent(self, since_time: datetime):
        """Mark entries included in this digest send as no longer new."""
        data = self._load_data()
        since_time = self._normalize_time(since_time)
        count = 0

        for entry in data["entries"]:
            try:
                entry_time = self._normalize_time(datetime.fromisoformat(entry["timestamp"]))
                if entry_time >= since_time and entry.get("is_new"):
                    entry["is_new"] = False
                    count += 1
            except Exception as e:
                logger.error(f"Error in mark_as_sent: {e}")

        if count > 0:
            self._save_data(data)
            logger.info(f"Marked {count} swuk entries as no longer new")


# Global instance
swuk_digest_manager = SwukDigest()
