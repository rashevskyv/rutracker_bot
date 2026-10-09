"""
Base Digest Module
Shared functionality for all digest types (daily rutracker, homebrew, etc.)
"""
import json
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from utils.atomic_io import atomic_open

logger = logging.getLogger(__name__)


class BaseDigest:
    """Base class for digest data collection, storage, and sending."""

    def __init__(self, data_file: str, digest_name: str = "digest"):
        self.data_file = data_file
        self.digest_name = digest_name
        # Data files live in the project root, not in the digest/ subdirectory
        self.current_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(self.current_directory, data_file)

    def _load_data(self) -> Dict:
        """Load existing digest data from file"""
        if not os.path.exists(self.data_path):
            return {"entries": []}

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {self.digest_name} data: {e}")
            return {"entries": []}

    def _save_data(self, data: Dict):
        """Save digest data to file"""
        try:
            with atomic_open(self.data_path) as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving {self.digest_name} data: {e}")

    @staticmethod
    def _normalize_time(dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (default to UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def get_entries_since(self, since_time: datetime) -> List[Dict]:
        """Get all entries since a specific time."""
        data = self._load_data()
        since_time = self._normalize_time(since_time)

        entries = []
        for entry in data["entries"]:
            try:
                entry_time = self._normalize_time(datetime.fromisoformat(entry["timestamp"]))
                if entry_time >= since_time:
                    entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        return entries

    def clear_old_entries(self, before_time: datetime):
        """Remove entries older than specified time"""
        data = self._load_data()
        before_time = self._normalize_time(before_time)

        filtered_entries = []
        for entry in data["entries"]:
            try:
                entry_time = self._normalize_time(datetime.fromisoformat(entry["timestamp"]))
                if entry_time >= before_time:
                    filtered_entries.append(entry)
            except Exception as e:
                logger.error(f"Error parsing entry timestamp: {e}")

        data["entries"] = filtered_entries
        self._save_data(data)
        logger.info(f"Cleared old {self.digest_name} entries. Remaining: {len(filtered_entries)}")

    def format_digest_message(self, since_time: datetime) -> Optional[str]:
        """Format digest message. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement format_digest_message()")

    def _split_digest_message(self, message: str, max_length: int = 4096) -> list:
        """
        Split a long digest into Telegram-sized parts.
        1. Whole sections (=== ... ===) are packed into parts; a section that does not fit
           into the current part starts a new one.
        2. A section longer than max_length is split at entry boundaries (• / ⚠️ / #)
           into roughly equal chunks; every continuation chunk repeats the section header.
        Text before the first section header stays with the first section.
        """
        is_entry = lambda line: line.strip().startswith(('•', '⚠️', '#'))

        # Cut lines into sections at === headers
        sections = [{'title': '', 'lines': []}]
        for line in message.split('\n'):
            if line.strip().startswith('==='):
                sections.append({'title': line.strip(), 'lines': [line]})
            else:
                sections[-1]['lines'].append(line)
        if len(sections) > 1:
            preamble = sections.pop(0)['lines']
            sections[0]['lines'] = preamble + sections[0]['lines']
            sections[0]['prefix_len'] = len(preamble)

        parts = []
        current = ''
        for sec in sections:
            lines = sec['lines']
            # Head = preamble + title + non-entry lines before the first entry
            i = sec.get('prefix_len', 0) + (1 if sec['title'] else 0)
            while i < len(lines) and not is_entry(lines[i]):
                i += 1
            head, entries = lines[:i], []
            for line in lines[i:]:
                if is_entry(line) or not entries:
                    entries.append(line)
                else:
                    entries[-1] += '\n' + line

            body = '\n'.join(head + entries).strip()
            if not body:
                continue
            if len(body) > max_length:
                chunks = self._split_section_evenly(head, sec['title'], entries, max_length)
                if current:
                    parts.append(current)
                parts.extend(chunks[:-1])
                current = chunks[-1]  # the tail may share a part with the next section
            elif current and len(current) + 2 + len(body) > max_length:
                parts.append(current)
                current = body
            else:
                current = f"{current}\n\n{body}" if current else body

        if current:
            parts.append(current)
        return parts

    @staticmethod
    def _split_section_evenly(head: list, title: str, entries: list, max_length: int) -> list:
        """Split one oversized section into the fewest roughly equal chunks that fit max_length."""
        total = sum(len(e) + 1 for e in entries)
        n = max(2, -(-total // max_length))
        while True:
            groups = [[]]
            acc = 0
            for e in entries:
                # Start the next chunk once this entry's midpoint crosses the next 1/n boundary
                if groups[-1] and acc + len(e) / 2 > len(groups) * total / n:
                    groups.append([])
                groups[-1].append(e)
                acc += len(e) + 1
            chunks = ['\n'.join((head if k == 0 else [title]) + g).strip() for k, g in enumerate(groups)]
            # A single entry longer than max_length cannot be fixed here; stop at one entry per chunk
            if all(len(c) <= max_length for c in chunks) or n >= len(entries):
                return chunks
            n += 1

    async def send_digest(self, target_chat_id: int, target_topic_id: Optional[int] = None,
                          since_time: Optional[datetime] = None, translate_to_ua: bool = False):
        """
        Send digest to specified Telegram channel.

        Args:
            target_chat_id: Telegram chat ID
            target_topic_id: Optional topic ID for supergroups
            since_time: Optional start time for digest (defaults to last 24 hours)
            translate_to_ua: Whether to translate Russian text to Ukrainian
        """
        from core.settings_loader import bot
        from services.telegram_sender import send_message_to_admin

        now = datetime.now()
        if since_time is None:
            since_time = now - timedelta(hours=24)

        logger.info(f"Generating {self.digest_name} for period: {since_time} to {now}")

        message = self.format_digest_message(since_time)

        if not message:
            logger.info(f"No entries for {self.digest_name}")
            await send_message_to_admin(f"{self.digest_name.capitalize()}: No new entries in the specified period")
            return

        # Translate if needed
        if translate_to_ua:
            logger.info(f"Translating {self.digest_name} to Ukrainian for chat {target_chat_id}")
            try:
                from services.translation import translate_ru_to_ua
                message = await translate_ru_to_ua(message)
            except Exception as e:
                logger.error(f"Error translating {self.digest_name}: {e}. Sending in Russian.")

        # Clean up ###GAP### markers (convert to double newlines)
        message = re.sub(r'(?:\s*###GAP###\s*)+', '\n\n', message)
        message = re.sub(r'###\s*-?\s*', '', message)  # Remove stray ### markers

        # Clean HTML before sending to Telegram
        from utils.telegram_utils import fix_html_for_telegram
        message = fix_html_for_telegram(message)

        try:
            # Telegram max message length is 4096 chars
            if len(message) <= 4096:
                await bot.send_message(
                    chat_id=target_chat_id,
                    message_thread_id=target_topic_id,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                # Split long digests at entry boundaries (• markers)
                # Each entry = line starting with • plus any continuation lines
                parts = self._split_digest_message(message, 4096)
                logger.info(f"{self.digest_name}: message too long ({len(message)} chars), splitting into {len(parts)} parts")
                for i, part in enumerate(parts):
                    clean_part = fix_html_for_telegram(part)
                    await bot.send_message(
                        chat_id=target_chat_id,
                        message_thread_id=target_topic_id,
                        text=clean_part,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
            logger.info(f"{self.digest_name.capitalize()} sent to {target_chat_id}")

        except Exception as e:
            logger.error(f"Error sending {self.digest_name}: {e}")
            await send_message_to_admin(f"Error sending {self.digest_name}: {e}")
            raise  # Re-raise so the caller knows this group failed

# --- END OF FILE base_digest.py ---
