"""
Swuk Updates Collector
Fetches Ukrainian Switch localizations from swuk.com.ua RSS feed
and adds them to the swuk digest.
"""
import asyncio
import json
import os
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from digest.swuk import swuk_digest_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SWUK_FEED_URL = 'https://swuk.com.ua/feed/tg-updates/'
SWUK_STATE_PATH = os.path.join('data', 'swuk_state.json')


def load_swuk_state() -> Dict:
    """Load swuk tracking state from file."""
    path = Path(SWUK_STATE_PATH)
    if not path.exists():
        logger.info("Swuk state file not found — starting fresh")
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading swuk state: {e}")
        return {}


def save_swuk_state(state: Dict):
    """Save swuk tracking state to file."""
    path = Path(SWUK_STATE_PATH)
    try:
        os.makedirs(path.parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved swuk state: {len(state)} entries")
    except Exception as e:
        logger.error(f"Error saving swuk state: {e}")


def parse_modified_from_guid(guid: str) -> Optional[str]:
    """Extract ?modified=TIMESTAMP from guid string."""
    match = re.search(r'\?modified=(\d+)', guid)
    return match.group(1) if match else None


def clean_title(title: str) -> str:
    """Remove [НОВИНКА] / [ОНОВЛЕНО] prefix."""
    return re.sub(r'^\[(НОВИНКА|ОНОВЛЕНО)\]\s*', '', title).strip()


def strip_html_tags(text: str) -> str:
    """Strip HTML tags and unescape entities from description."""
    import html as html_lib
    text = re.sub(r'<[^>]+>', '', text)
    text = html_lib.unescape(text)
    return text.strip()


async def collect_swuk_updates():
    """Main collection logic: fetch RSS, compare with state, add to digest."""
    state = load_swuk_state()
    updates_found = 0

    from core.settings_loader import get_session
    session = get_session()

    logger.info(f"Fetching swuk RSS: {SWUK_FEED_URL}")
    try:
        async with session.get(SWUK_FEED_URL, timeout=30) as resp:
            if resp.status != 200:
                logger.error(f"Swuk feed returned status {resp.status}")
                return
            xml_content = await resp.text()
    except Exception as e:
        logger.error(f"Failed to fetch swuk feed: {e}")
        return

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.error(f"Failed to parse swuk RSS: {e}")
        return

    items = root.findall('.//item')
    logger.info(f"Found {len(items)} items in swuk RSS")

    for item in items:
        title_raw = item.findtext('title', '').strip()
        link = item.findtext('link', '').strip()
        guid = item.findtext('guid', '').strip()
        description_raw = item.findtext('description', '').strip()

        if not link or not title_raw:
            continue

        is_new = '[НОВИНКА]' in title_raw
        game_name = clean_title(title_raw)
        modified = parse_modified_from_guid(guid)
        description = strip_html_tags(description_raw)

        saved = state.get(link, {})
        saved_modified = saved.get('modified', '')

        # Nothing changed — skip
        if saved_modified and saved_modified == modified:
            continue

        action = 'new' if not saved_modified else 'updated'
        # If we've seen this URL before, it's an update regardless of title prefix
        if saved_modified:
            is_new = False

        logger.info(f"Swuk [{action}]: {game_name} (modified: {modified})")

        swuk_digest_manager.add_entry(
            game_name=game_name,
            release_url=link,
            description=description,
            is_new=is_new,
            timestamp=datetime.now(),
        )

        state[link] = {
            'modified': modified or '',
            'title': game_name,
        }
        updates_found += 1

    save_swuk_state(state)
    logger.info(f"Swuk collection complete: {updates_found} new/updated entries")


async def main():
    """Entry point."""
    from core.settings_loader import close_clients
    try:
        await collect_swuk_updates()
    finally:
        await close_clients()


if __name__ == '__main__':
    asyncio.run(main())
