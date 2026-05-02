"""
Manual Releases Processor
Reads manual_releases.json and adds entries to the appropriate digests.
Entries are processed once and then removed from the file.
"""
import json
import os
import logging
from datetime import datetime
from typing import List, Dict

from digest.daily import digest_manager
from digest.homebrew import homebrew_digest_manager

logger = logging.getLogger(__name__)

MANUAL_RELEASES_FILE = os.path.join("data", "manual_releases.json")


def load_manual_releases() -> List[Dict]:
    """Load manual releases from JSON file"""
    if not os.path.exists(MANUAL_RELEASES_FILE):
        return []

    try:
        with open(MANUAL_RELEASES_FILE, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            logger.warning("manual_releases.json is not a list, skipping")
            return []
        return entries
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in manual_releases.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading manual_releases.json: {e}")
        return []


def clear_manual_releases():
    """Clear the manual releases file after processing"""
    try:
        with open(MANUAL_RELEASES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        logger.info("Cleared manual_releases.json")
    except Exception as e:
        logger.error(f"Error clearing manual_releases.json: {e}")


def process_manual_releases() -> int:
    """
    Process all manual releases and add them to appropriate digests.

    Returns:
        Number of entries processed successfully
    """
    entries = load_manual_releases()
    if not entries:
        return 0

    processed = 0

    for entry in entries:
        entry_type = entry.get('type', '').lower()
        added_date = entry.get('added_date')

        # Parse timestamp
        timestamp = None
        if added_date:
            try:
                timestamp = datetime.fromisoformat(added_date)
            except ValueError:
                logger.warning(f"Invalid date format: {added_date}, using current time")

        try:
            if entry_type == 'game':
                digest_manager.add_entry(
                    title=entry.get('title', 'Unknown'),
                    entry_url=entry.get('url', ''),
                    size=entry.get('size', 'N/A'),
                    language=entry.get('language', 'N/A'),
                    is_updated=entry.get('is_updated', False),
                    update_description=entry.get('description'),
                    genres=entry.get('genres', []),
                    trailer_url=entry.get('trailer_url'),
                    timestamp=timestamp
                )
                logger.info(f"Manual release added to daily digest: {entry.get('title')}")
                processed += 1

            elif entry_type == 'homebrew':
                homebrew_digest_manager.add_entry(
                    app_name=entry.get('app_name', 'Unknown'),
                    version=entry.get('version', ''),
                    release_url=entry.get('release_url', ''),
                    description=entry.get('description', ''),
                    platform=entry.get('platform', 'Switch'),
                    is_new=entry.get('is_new', False),
                    timestamp=timestamp
                )
                logger.info(f"Manual release added to homebrew digest: {entry.get('app_name')}")
                processed += 1

            else:
                logger.warning(f"Unknown manual release type: '{entry_type}', skipping entry")

        except Exception as e:
            logger.error(f"Error processing manual release: {e}")

    if processed > 0:
        clear_manual_releases()
        logger.info(f"Processed {processed} manual releases")

    return processed
