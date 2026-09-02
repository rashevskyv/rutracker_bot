"""
Homebrew Digest Module
Collects and formats daily summaries of homebrew application updates
"""
import html
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional

from digest.base import BaseDigest

logger = logging.getLogger(__name__)

HOMEBREW_DIGEST_FILE = os.path.join("data", "homebrew_digest_data.json")


def clean_markdown_and_whitespace(text: str) -> str:
    """Strip raw markdown syntax, unwanted HTML tags, and normalize whitespace."""
    if not text:
        return ""
    # Strip HTML tags like <p>, <div>, <b>, <a> except Telegram <i> handled separately
    text = re.sub(r'</?(?!i\b|/i\b)[a-zA-Z][^>]*>', ' ', text)
    # Remove markdown images ![caption](url) BEFORE links
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bold / italics (**text**, *text*, __text__, _text_)
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
    text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
    # Remove headers (#, ##, ###, etc.)
    text = re.sub(r'(?m)^#{1,6}\s*', '', text)
    # Remove bullet markers (*, -, +, •)
    text = re.sub(r'(?m)^\s*[\*\-\+•]\s*', '', text)
    # Remove backticks `code`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Clean up lingering markdown artifacts
    text = text.replace('**', '').replace('###', '')
    # Normalize multiple whitespaces and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def limit_to_sentences(text: str, max_sentences: int = 2, max_chars: int = 220) -> str:
    """Limit text to at most max_sentences and max_chars without cutting mid-word when possible."""
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) > max_sentences:
        text = " ".join(sentences[:max_sentences])
    if len(text) > max_chars:
        truncated = text[:max_chars]
        last_punct = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
        if last_punct > 50:
            text = truncated[:last_punct + 1]
        else:
            last_space = truncated.rfind(' ')
            if last_space > 50:
                text = truncated[:last_space] + "..."
            else:
                text = truncated + "..."
    return text.strip()


def sanitize_digest_description(description: str) -> str:
    """
    Sanitize homebrew description for digest:
    - Strips raw markdown (**, ###, bullets, [links](url))
    - Collapses multiple newlines
    - Limits main description to 1-2 sentences (max ~220 chars)
    - Limits optional changelog (<i>...</i>) to 1-2 sentences (max ~180 chars)
    - Ensures clean Telegram HTML formatting without walls of text
    """
    if not description or not description.strip():
        return ""

    raw = description.strip()

    # Check if there is an italic changelog block (<i>...</i>)
    if '<i>' in raw:
        parts = raw.split('<i>', 1)
        base_desc = parts[0].strip()
        cl_part = parts[1]
        if '</i>' in cl_part:
            cl_text = cl_part.split('</i>')[0].strip()
        else:
            cl_text = cl_part.strip()
    else:
        base_desc = raw
        cl_text = ""

    clean_base = clean_markdown_and_whitespace(base_desc)
    clean_base = limit_to_sentences(clean_base, max_sentences=2, max_chars=220)

    clean_cl = clean_markdown_and_whitespace(cl_text)
    clean_cl = limit_to_sentences(clean_cl, max_sentences=2, max_chars=180)

    if clean_base and clean_cl:
        return f"{clean_base}\n<i>{clean_cl}</i>"
    elif clean_cl:
        return f"<i>{clean_cl}</i>"
    else:
        return clean_base



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
                description = sanitize_digest_description(entry.get('description', ''))
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
                if description:
                    line = f"{marker}<a href=\"{entry['release_url']}\">{app_name} {version}</a> від {date_str} — {description}"
                else:
                    line = f"{marker}<a href=\"{entry['release_url']}\">{app_name} {version}</a> від {date_str}"
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
