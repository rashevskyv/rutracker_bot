"""
Homebrew Updates Collector
Checks GitHub/GitLab for homebrew app updates and adds them to digest
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import aiohttp
from homebrew_digest import homebrew_digest_manager
from translation import translate_ru_to_ua

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HomebrewUpdatesCollector:
    """Collects homebrew updates from GitHub/GitLab"""

    def __init__(self, list_path: str, github_token: Optional[str] = None, gitlab_token: Optional[str] = None):
        self.list_path = Path(list_path)
        self.github_token = github_token
        self.gitlab_token = gitlab_token
        self.session: Optional[aiohttp.ClientSession] = None

        # Rate limit tracking
        self.github_requests = 0
        self.gitlab_requests = 0
        self.updates_found = 0
        self.errors = []

    async def __aenter__(self):
        """Initialize aiohttp session"""
        headers = {'User-Agent': 'HomebrewBot/1.0'}
        self.session = aiohttp.ClientSession(headers=headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

    def load_homebrew_list(self) -> List[Dict]:
        """Load homebrew list from JSON file"""
        logger.info(f"Loading homebrew list from {self.list_path}")

        if not self.list_path.exists():
            logger.error(f"File not found: {self.list_path}")
            return []

        try:
            with open(self.list_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            logger.info(f"Loaded {len(entries)} homebrew entries")
            return entries
        except Exception as e:
            logger.error(f"Error loading homebrew list: {e}")
            return []

    async def github_request(self, url: str) -> Optional[Dict]:
        """Make GitHub API request with rate limit handling"""
        if not self.session:
            logger.error("Session not initialized")
            return None

        headers = {}
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'

        try:
            async with self.session.get(url, headers=headers, timeout=30) as resp:
                # Check rate limits
                remaining = resp.headers.get('X-RateLimit-Remaining')
                if remaining:
                    logger.debug(f"GitHub rate limit remaining: {remaining}")

                if resp.status == 403:
                    reset_time = resp.headers.get('X-RateLimit-Reset')
                    if reset_time:
                        reset_dt = datetime.fromtimestamp(int(reset_time))
                        logger.warning(f"GitHub rate limit hit. Resets at {reset_dt}")
                    return None

                if resp.status != 200:
                    logger.warning(f"GitHub API returned status {resp.status} for {url}")
                    return None

                self.github_requests += 1
                return await resp.json()

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting {url}")
            return None
        except Exception as e:
            logger.error(f"Error requesting {url}: {e}")
            return None

    async def gitlab_request(self, url: str) -> Optional[Dict]:
        """Make GitLab API request with rate limit handling"""
        if not self.session:
            logger.error("Session not initialized")
            return None

        headers = {}
        if self.gitlab_token:
            headers['Private-Token'] = self.gitlab_token

        try:
            async with self.session.get(url, headers=headers, timeout=30) as resp:
                # Check rate limits
                remaining = resp.headers.get('RateLimit-Remaining')
                if remaining:
                    logger.debug(f"GitLab rate limit remaining: {remaining}")

                if resp.status != 200:
                    logger.warning(f"GitLab API returned status {resp.status} for {url}")
                    return None

                self.gitlab_requests += 1
                return await resp.json()

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting {url}")
            return None
        except Exception as e:
            logger.error(f"Error requesting {url}: {e}")
            return None

    async def check_github_updates(self, entry: Dict) -> Optional[Dict]:
        """Check for GitHub updates"""
        api_url = entry['api_url']
        releases_url = f"{api_url}/releases"

        releases = await self.github_request(releases_url)
        if not releases or not isinstance(releases, list) or len(releases) == 0:
            return None

        # Get latest release
        latest = releases[0]

        # Check if it has a message (error)
        if 'message' in latest:
            logger.warning(f"{entry['app_name']}: GitHub returned message: {latest['message']}")
            return None

        # Parse dates
        try:
            entry_date = datetime.fromisoformat(entry['comm_date'].replace('Z', '+00:00'))
            release_date = datetime.fromisoformat(latest['published_at'].replace('Z', '+00:00'))

            # Check assets for newer date
            asset_date = release_date
            if 'assets' in latest and latest['assets']:
                for asset in latest['assets']:
                    asset_updated = datetime.fromisoformat(asset['updated_at'].replace('Z', '+00:00'))
                    if asset_updated > asset_date:
                        asset_date = asset_updated

            # Check if there's an update
            if release_date > entry_date or asset_date > entry_date:
                return {
                    'tag_name': latest['tag_name'],
                    'html_url': latest['html_url'],
                    'date': max(release_date, asset_date).isoformat()
                }
        except Exception as e:
            logger.error(f"Error parsing dates for {entry['app_name']}: {e}")

        return None

    async def check_gitlab_updates(self, entry: Dict) -> Optional[Dict]:
        """Check for GitLab updates"""
        api_url = entry['api_url']

        releases = await self.gitlab_request(api_url)
        if not releases or not isinstance(releases, list) or len(releases) == 0:
            return None

        # Sort by date (descending)
        releases.sort(key=lambda x: x.get('released_at', ''), reverse=True)
        latest = releases[0]

        # Parse dates
        try:
            entry_date = datetime.fromisoformat(entry['comm_date'].replace('Z', '+00:00'))
            release_date = datetime.fromisoformat(latest['released_at'].replace('Z', '+00:00'))

            # Check if there's an update
            if release_date > entry_date:
                return {
                    'tag_name': latest['tag_name'],
                    'html_url': latest['_links']['self'],
                    'date': release_date.isoformat()
                }
        except Exception as e:
            logger.error(f"Error parsing dates for {entry['app_name']}: {e}")

        return None

    async def process_entry(self, entry: Dict, translate: bool = True) -> bool:
        """Process single homebrew entry"""
        app_name = entry['app_name']
        api_url = entry['api_url']

        logger.info(f"Checking {app_name}...")

        # Check if entry is marked as new
        is_new = entry.get('new', False)

        # Determine source (GitHub or GitLab)
        update_info = None
        if is_new:
            # For new entries, use current release info without checking for updates
            logger.info(f"✓ New app: {app_name} {entry['tag_name']}")
            update_info = {
                'tag_name': entry['tag_name'],
                'html_url': entry['html_url'],
                'date': entry['comm_date']
            }
        elif 'github' in api_url:
            update_info = await self.check_github_updates(entry)
        elif 'gitlab' in api_url:
            update_info = await self.check_gitlab_updates(entry)
        else:
            logger.warning(f"{app_name}: Unknown API source: {api_url}")
            return False

        if not update_info:
            return False

        # Found an update or new app!
        if not is_new:
            logger.info(f"✓ Update found: {app_name} {update_info['tag_name']}")
        self.updates_found += 1

        # Translate description if needed
        description = entry['description']
        if translate:
            try:
                logger.info(f"Translating description for {app_name}...")
                description = await translate_ru_to_ua(description)
            except Exception as e:
                logger.error(f"Translation failed for {app_name}: {e}")
                # Keep original Russian description

        # Parse date for display
        try:
            update_date = datetime.fromisoformat(update_info['date'].replace('Z', '+00:00'))
        except:
            update_date = datetime.now()

        # Add to digest
        homebrew_digest_manager.add_entry(
            app_name=app_name,
            version=update_info['tag_name'],
            release_url=update_info['html_url'],
            description=description,
            platform=entry['category'],
            timestamp=update_date,
            is_new=entry.get('new', False)
        )

        return True

    async def collect_updates(self, translate: bool = True, max_entries: Optional[int] = None):
        """Collect all homebrew updates"""
        entries = self.load_homebrew_list()

        if not entries:
            logger.error("No entries to process")
            return

        if max_entries:
            entries = entries[:max_entries]
            logger.info(f"Processing first {max_entries} entries (test mode)")

        total = len(entries)
        logger.info(f"Processing {total} homebrew entries...")

        # Track entries that had 'new' flag and were processed
        new_entries_processed = []

        # Process entries with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def process_with_semaphore(entry: Dict, index: int):
            async with semaphore:
                try:
                    was_new = entry.get('new', False)
                    processed = await self.process_entry(entry, translate=translate)

                    # Track new entries that were successfully processed
                    if was_new and processed:
                        new_entries_processed.append(index)

                except Exception as e:
                    logger.error(f"Error processing {entry['app_name']}: {e}")
                    self.errors.append(f"{entry['app_name']}: {e}")

                # Progress indicator
                if (index + 1) % 10 == 0:
                    logger.info(f"Progress: {index + 1}/{total} | Updates: {self.updates_found} | Errors: {len(self.errors)}")

        # Process all entries
        tasks = [process_with_semaphore(entry, i) for i, entry in enumerate(entries)]
        await asyncio.gather(*tasks)

        # Remove 'new' flag from processed entries (only in production mode)
        from settings_loader import IS_TEST_MODE
        if new_entries_processed and not IS_TEST_MODE:
            logger.info(f"Removing 'new' flag from {len(new_entries_processed)} processed entries...")

            # Reload full list (not just the slice)
            full_entries = self.load_homebrew_list()

            for index in new_entries_processed:
                if index < len(full_entries) and full_entries[index].get('new'):
                    del full_entries[index]['new']
                    logger.info(f"Removed 'new' flag from {full_entries[index]['app_name']}")

            # Save updated list
            try:
                import json
                with open(self.list_path, 'w', encoding='utf-8') as f:
                    json.dump(full_entries, f, ensure_ascii=False, indent=2)
                logger.info(f"Updated {self.list_path} - removed 'new' flags")
            except Exception as e:
                logger.error(f"Error saving updated list: {e}")
        elif new_entries_processed and IS_TEST_MODE:
            logger.info(f"TEST MODE: Would remove 'new' flag from {len(new_entries_processed)} entries in production")

        # Summary
        logger.info("=" * 60)
        logger.info(f"Collection complete!")
        logger.info(f"Total entries processed: {total}")
        logger.info(f"Updates found: {self.updates_found}")
        logger.info(f"GitHub requests: {self.github_requests}")
        logger.info(f"GitLab requests: {self.gitlab_requests}")
        logger.info(f"Errors: {len(self.errors)}")

        if self.errors:
            logger.warning("Errors encountered:")
            for error in self.errors[:10]:  # Show first 10 errors
                logger.warning(f"  - {error}")

        # Save collection timestamp (for digest to use)
        from settings_loader import IS_TEST_MODE
        if not IS_TEST_MODE:
            self._save_collection_timestamp()

    def _save_collection_timestamp(self):
        """Save the current collection time as last digest run time"""
        import json
        from datetime import datetime

        LAST_RUN_FILE = "last_homebrew_digest_run.json"
        current_time = datetime.now()

        try:
            with open(LAST_RUN_FILE, 'w', encoding='utf-8') as f:
                json.dump({'last_digest_time': current_time.isoformat()}, f, indent=2)
            logger.info(f"Saved collection timestamp for digest: {current_time}")
        except Exception as e:
            logger.error(f"Error saving collection timestamp: {e}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Collect homebrew updates')
    parser.add_argument('--list', default='list_hb.json',
                        help='Path to list_hb.json')
    parser.add_argument('--translate', action='store_true',
                        help='Translate descriptions to Ukrainian (default: no translation)')
    parser.add_argument('--test', type=int, metavar='N',
                        help='Test mode: process only first N entries')
    parser.add_argument('--github-token', help='GitHub API token')
    parser.add_argument('--gitlab-token', help='GitLab API token')

    args = parser.parse_args()

    # Load tokens from environment, command line, or settings (in that order)
    import os

    github_token = args.github_token or os.environ.get('GITHUB_TOKEN')
    gitlab_token = args.gitlab_token or os.environ.get('GITLAB_TOKEN')

    if not github_token or not gitlab_token:
        try:
            from settings_loader import settings
            if not github_token:
                github_token = settings.get('GITHUB_TOKEN')
            if not gitlab_token:
                gitlab_token = settings.get('GITLAB_TOKEN')
        except Exception as e:
            logger.warning(f"Could not load tokens from settings: {e}")

    # Debug: log token status (without revealing the token)
    logger.info(f"GitHub token: {'present' if github_token else 'missing'}")
    logger.info(f"GitLab token: {'present' if gitlab_token else 'missing'}")

    async with HomebrewUpdatesCollector(
        list_path=args.list,
        github_token=github_token,
        gitlab_token=gitlab_token
    ) as collector:
        await collector.collect_updates(
            translate=args.translate,
            max_entries=args.test
        )


if __name__ == "__main__":
    asyncio.run(main())
