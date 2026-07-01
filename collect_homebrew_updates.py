"""
Homebrew Updates Collector
Checks GitHub/GitLab for homebrew app updates and adds them to digest.
Also fetches 3DS/DS apps from Universal-DB API as the primary source.
"""
import asyncio
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
import aiohttp
from digest.homebrew import homebrew_digest_manager
from services.translation import translate_ru_to_ua

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level constants (avoid Python 3.14 scoping issues with os inside functions)
DEFAULT_LIST_PATH = os.path.join('data', 'list_hb.json')
DEFAULT_STATE_PATH = os.path.join('data', 'hb_state.json')
HOMEBREW_LAST_RUN_PATH = os.path.join('data', 'last_homebrew_digest_run.json')

# Universal-DB API (3DS/DS)
UDB_API_URL = 'https://udb-api.lightsage.dev/all'
UDB_STATE_PATH = os.path.join('data', 'udb_state.json')
UDB_CATEGORIES = {'3DS', 'DS(i)', '3DS/DS(i)', '3DS/DS(i)/Switch'}

# ForTheUsers repos (Switch + WiiU)
SWITCH_REPO_URL = 'https://switch.cdn.fortheusers.org/repo.json'
WIIU_REPO_URL = 'https://wiiu.cdn.fortheusers.org/repo.json'
FORTHEUSERS_STATE_PATH = os.path.join('data', 'fortheusers_state.json')
SWITCH_FTU_CATEGORIES = {'Switch', 'WiiU/Switch', '3DS/DS(i)/Switch'}
WIIU_FTU_CATEGORIES = {'WiiU', 'WiiU/Switch'}

# Shared descriptions cache (translated, never re-translated)
DESCRIPTIONS_CACHE_PATH = os.path.join('data', 'hb_descriptions.json')

GPT_MODEL = 'gpt-5.4-nano'

# VitaDB (PS Vita)
VITADB_STATE_PATH = os.path.join('data', 'vitadb_state.json')
VITADB_ENDPOINTS = [
    ('https://rinnegatamante.eu/vitadb/list_hbs_json.php',     'vita-hb',     'PSVita'),
    ('https://rinnegatamante.eu/vitadb/list_plugins_json.php', 'vita-plugin', 'PSVita Plugin'),
    ('https://rinnegatamante.eu/vitadb/list_tools_json.php',   'vita-tool',   'PSVita PC Tool'),
]
# Vita entries in list_hb.json (if any) use this category
VITA_CATEGORIES = {'Vita', 'PSVita'}

# Collector run stats (saved after each run for the digest sender)
HB_STATS_PATH = os.path.join('data', 'hb_collect_stats.json')

# Chrome-like headers to bypass Cloudflare protection on a remote server/hosting
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}


class HomebrewUpdatesCollector:
    """Collects homebrew updates from GitHub/GitLab"""

    def __init__(self, list_path: str, state_path: str = None, github_token: Optional[str] = None, gitlab_token: Optional[str] = None):
        self.list_path = Path(list_path)
        self.state_path = Path(state_path or DEFAULT_STATE_PATH)
        self.github_token = github_token
        self.gitlab_token = gitlab_token

        # Rate limit tracking
        self.github_requests = 0
        self.gitlab_requests = 0
        self.udb_requests = 0
        self.updates_found = 0
        self.updated_apps = []
        self.errors = []

        # Per-source stats: {source_name: {'checked': int, 'found': int}}
        self.source_stats: Dict[str, Dict[str, int]] = {}

        # State dicts
        self._state: Dict[str, Dict] = {}              # hb_state.json (GitHub/GitLab)
        self._udb_state: Dict[str, Dict] = {}          # udb_state.json (Universal-DB)
        self._fortheusers_state: Dict[str, Dict] = {}  # fortheusers_state.json
        self._vitadb_state: Dict[str, Dict] = {}       # vitadb_state.json
        self._descriptions: Dict[str, str] = {}        # hb_descriptions.json (shared cache)

        # Load unprocessed manual releases to skip update tracking for them
        self.unprocessed_manual_names = set()
        try:
            from services.manual_releases import load_manual_releases
            self.unprocessed_manual_names = {
                e.get('app_name', '').lower() for e in load_manual_releases()
                if not e.get('processed')
            }
        except Exception as e:
            logger.error(f"Error pre-loading unprocessed manual releases: {e}")

    def is_unprocessed_manual(self, name: str) -> bool:
        """Check if name is in unprocessed manual releases (flexible matching)"""
        if not name:
            return False
        n_clean = name.lower().replace('-', ' ').replace('_', ' ').strip()
        for m_name in self.unprocessed_manual_names:
            m_clean = m_name.lower().replace('-', ' ').replace('_', ' ').strip()
            if n_clean == m_clean or n_clean.startswith(m_clean) or m_clean.startswith(n_clean):
                return True
        return False

    @property
    def session(self) -> aiohttp.ClientSession:
        """Use the shared aiohttp session from settings_loader."""
        from core.settings_loader import get_session
        return get_session()

    def load_state(self) -> Dict[str, Dict]:
        """Load dynamic state (comm_date, tag_name, html_url) from hb_state.json"""
        if not self.state_path.exists():
            logger.warning(f"State file not found: {self.state_path} — using empty state")
            return {}
        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"Loaded state for {len(state)} entries from {self.state_path}")
            return state
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            return {}

    def save_state(self):
        """Save dynamic state to hb_state.json"""
        try:
            os.makedirs(self.state_path.parent, exist_ok=True)
            with open(self.state_path, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved state for {len(self._state)} entries to {self.state_path}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_udb_state(self) -> Dict[str, Dict]:
        """Load Universal-DB state (version, updated, description cache) from udb_state.json"""
        udb_state_path = Path(UDB_STATE_PATH)
        if not udb_state_path.exists():
            logger.info("UDB state file not found — starting fresh")
            return {}
        try:
            with open(udb_state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"Loaded UDB state for {len(state)} entries")
            return state
        except Exception as e:
            logger.error(f"Error loading UDB state: {e}")
            return {}

    def save_udb_state(self):
        """Save Universal-DB state to udb_state.json"""
        udb_state_path = Path(UDB_STATE_PATH)
        try:
            os.makedirs(udb_state_path.parent, exist_ok=True)
            with open(udb_state_path, 'w', encoding='utf-8') as f:
                json.dump(self._udb_state, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved UDB state for {len(self._udb_state)} entries")
        except Exception as e:
            logger.error(f"Error saving UDB state: {e}")

    def load_fortheusers_state(self) -> Dict[str, Dict]:
        """Load ForTheUsers state from fortheusers_state.json"""
        path = Path(FORTHEUSERS_STATE_PATH)
        if not path.exists():
            logger.info("ForTheUsers state file not found — starting fresh")
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"Loaded ForTheUsers state for {len(state)} entries")
            return state
        except Exception as e:
            logger.error(f"Error loading ForTheUsers state: {e}")
            return {}

    def save_fortheusers_state(self):
        """Save ForTheUsers state to fortheusers_state.json"""
        path = Path(FORTHEUSERS_STATE_PATH)
        try:
            os.makedirs(path.parent, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._fortheusers_state, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved ForTheUsers state for {len(self._fortheusers_state)} entries")
        except Exception as e:
            logger.error(f"Error saving ForTheUsers state: {e}")

    def load_descriptions_cache(self) -> Dict[str, str]:
        """Load shared descriptions cache from hb_descriptions.json"""
        path = Path(DESCRIPTIONS_CACHE_PATH)
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logger.info(f"Loaded descriptions cache: {len(cache)} entries")
            return cache
        except Exception as e:
            logger.error(f"Error loading descriptions cache: {e}")
            return {}

    def save_descriptions_cache(self):
        """Save shared descriptions cache to hb_descriptions.json"""
        path = Path(DESCRIPTIONS_CACHE_PATH)
        try:
            os.makedirs(path.parent, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._descriptions, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved descriptions cache: {len(self._descriptions)} entries")
        except Exception as e:
            logger.error(f"Error saving descriptions cache: {e}")

    def load_vitadb_state(self) -> Dict[str, Dict]:
        """Load VitaDB state from vitadb_state.json"""
        path = Path(VITADB_STATE_PATH)
        if not path.exists():
            logger.info("VitaDB state file not found — starting fresh")
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"Loaded VitaDB state for {len(state)} entries")
            return state
        except Exception as e:
            logger.error(f"Error loading VitaDB state: {e}")
            return {}

    def save_vitadb_state(self):
        """Save VitaDB state to vitadb_state.json"""
        path = Path(VITADB_STATE_PATH)
        try:
            os.makedirs(path.parent, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._vitadb_state, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved VitaDB state for {len(self._vitadb_state)} entries")
        except Exception as e:
            logger.error(f"Error saving VitaDB state: {e}")

    def load_homebrew_list(self) -> List[Dict]:
        """Load static registry and merge with dynamic state"""
        logger.info(f"Loading homebrew registry from {self.list_path}")

        if not self.list_path.exists():
            logger.error(f"Registry file not found: {self.list_path}")
            return []

        try:
            with open(self.list_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception as e:
            logger.error(f"Error loading homebrew registry: {e}")
            return []

        # Load and merge dynamic state
        self._state = self.load_state()

        for entry in entries:
            api_url = entry.get('api_url', '')
            if api_url in self._state:
                state_data = self._state[api_url]
                entry['comm_date'] = state_data.get('comm_date', '2024-01-01T00:00:00Z')
                entry['tag_name'] = state_data.get('tag_name', '')
                entry['html_url'] = state_data.get('html_url', '')
            else:
                # New entry without state — use defaults
                entry.setdefault('comm_date', '2024-01-01T00:00:00Z')
                entry.setdefault('tag_name', '')
                entry.setdefault('html_url', '')

        logger.info(f"Loaded {len(entries)} homebrew entries (merged with state)")
        return entries

    @staticmethod
    def _extract_github_slug(url: str) -> Optional[str]:
        """Extract 'owner/repo' from a GitHub URL (api or web) or slug."""
        if not url:
            return None
        url = url.rstrip('/')
        if url.startswith(('http://', 'https://')):
            for prefix in ('https://api.github.com/repos/', 'https://github.com/'):
                if url.startswith(prefix):
                    slug = url[len(prefix):]
                    # Remove any trailing path segments (e.g. /releases)
                    return '/'.join(slug.split('/')[:2])
            return None
        # If it doesn't look like a URL but contains exactly one slash, it might be a slug
        if '/' in url and url.count('/') == 1:
            return url
        return None

    async def summarize_and_translate_notes(self, notes: str) -> Optional[str]:
        """Summarize update notes to exactly 1 Ukrainian sentence using GPT."""
        from core.settings_loader import openai_client
        if not openai_client or not notes or not notes.strip():
            return None
        try:
            prompt = (
                f"Summarize the following software update notes into exactly ONE concise sentence in Ukrainian.\n\n"
                f"Rules:\n"
                f"1. ONE sentence only — no more.\n"
                f"2. Describe only WHAT was changed, fixed, or added in this update.\n"
                f"3. Do NOT include thanks, credits, author names, or release ceremony text.\n"
                f"4. Keep English brand names and technical terms untranslated.\n"
                f"5. Output plain text only (no HTML, no markdown). End with a period.\n\n"
                f"Update notes:\n{notes.strip()}\n\n"
                f"One-sentence Ukrainian summary:"
            )
            use_new_param = GPT_MODEL.startswith(('gpt-5', 'o1', 'o3', 'o4'))
            extra = {'max_completion_tokens': 100} if use_new_param else {'max_tokens': 100}
            response = await openai_client.chat.completions.create(
                model=GPT_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.3,
                **extra,
            )
            result = response.choices[0].message.content.strip()
            logger.info(f"Summarized update notes: {result[:80]}")
            return result
        except Exception as e:
            logger.error(f"Error summarizing update notes: {e}")
            return None

    async def _get_description_cached(
        self, cache_key: str, local_entry: Optional[Dict],
        raw_text: str, fallback_name: str
    ) -> str:
        """
        Resolve description using priority chain (shared for all repo sources):
        1. Our list_hb.json entry description
        2. hb_descriptions.json cache
        3. raw_text → GPT summarize+translate → save to cache
        """
        # 1. Our list
        if local_entry and local_entry.get('description'):
            return local_entry['description']

        # 2. Shared descriptions cache
        if cache_key in self._descriptions:
            return self._descriptions[cache_key]

        # 3. Translate and cache
        if not raw_text.strip():
            return fallback_name

        logger.info(f"[{cache_key}]: translating and caching description...")
        try:
            from services.translation import translate_short_description
            translated = await translate_short_description(raw_text)
            # Only cache if translation succeeded (i.e. result differs from raw input or is clearly Ukrainian)
            self._descriptions[cache_key] = translated
            return translated
        except Exception as e:
            logger.error(f"[{cache_key}]: description translation failed: {e}")
            # Do NOT cache — return fallback without saving raw English text
            return fallback_name

    async def _get_description_for_udb_app(
        self, slug: str, udb_app: Dict, local_entry: Optional[Dict]
    ) -> str:
        """Resolve description for a UDB app."""
        raw_desc = udb_app.get('long_description') or udb_app.get('description') or ''
        return await self._get_description_cached(
            cache_key=f'udb:{slug}',
            local_entry=local_entry,
            raw_text=raw_desc,
            fallback_name=udb_app.get('title', slug),
        )

    @staticmethod
    def _extract_latest_changelog(changelog: str) -> Optional[str]:
        """Extract the most recent changelog block (before first double newline after header)."""
        if not changelog or changelog.strip().lower() in ('n/a', 'na', ''):
            return None
        # Split on double newline — first block is the most recent entry
        blocks = changelog.split('\n\n')
        if not blocks:
            return None
        latest = blocks[0].strip()
        # If the latest block is just a version number with no detail, include next block too
        if latest and len(latest.splitlines()) == 1 and len(blocks) > 1:
            latest = f"{latest}\n{blocks[1].strip()}"
        return latest if latest else None

    async def github_request(self, url: str) -> Optional[Dict]:
        """Make GitHub API request with rate limit handling"""
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
        if is_new and api_url in self._state:
            is_new = False

        # Determine source (GitHub or GitLab)
        update_info = None
        if is_new:
            # For new entries, fetch current release info from API
            # (entry fields tag_name/html_url may be empty for freshly added apps)
            if 'github' in api_url:
                releases_url = f"{api_url}/releases"
                releases = await self.github_request(releases_url)
                if releases and isinstance(releases, list) and len(releases) > 0:
                    latest = releases[0]
                    if 'message' not in latest:
                        try:
                            release_date = datetime.fromisoformat(latest['published_at'].replace('Z', '+00:00'))
                            update_info = {
                                'tag_name': latest['tag_name'],
                                'html_url': latest['html_url'],
                                'date': release_date.isoformat()
                            }
                        except Exception as e:
                            logger.error(f"Error parsing new app release for {app_name}: {e}")
            elif 'gitlab' in api_url:
                releases = await self.gitlab_request(api_url)
                if releases and isinstance(releases, list) and len(releases) > 0:
                    releases.sort(key=lambda x: x.get('released_at', ''), reverse=True)
                    latest = releases[0]
                    try:
                        release_date = datetime.fromisoformat(latest['released_at'].replace('Z', '+00:00'))
                        update_info = {
                            'tag_name': latest['tag_name'],
                            'html_url': latest['_links']['self'],
                            'date': release_date.isoformat()
                        }
                    except Exception as e:
                        logger.error(f"Error parsing new app release for {app_name}: {e}")

            # Fallback: use entry fields if API failed
            if not update_info:
                update_info = {
                    'tag_name': entry.get('tag_name') or 'unknown',
                    'html_url': entry.get('html_url') or '',
                    'date': entry.get('comm_date', datetime.now().isoformat())
                }

            logger.info(f"✓ New app: {app_name} {update_info['tag_name']}")
        elif 'github' in api_url:
            update_info = await self.check_github_updates(entry)
        elif 'gitlab' in api_url:
            update_info = await self.check_gitlab_updates(entry)
        else:
            logger.warning(f"{app_name}: Unknown API source: {api_url}")
            return False

        if not update_info:
            return False

        if self.is_unprocessed_manual(app_name):
            logger.info(f"Skipping updates post for {app_name} — pending manual release. Updating state only.")
            self._state[api_url] = {
                'comm_date': update_info['date'],
                'tag_name': update_info['tag_name'],
                'html_url': update_info['html_url']
            }
            return False

        # Found an update or new app!
        if not is_new:
            logger.info(f"✓ Update found: {app_name} {update_info['tag_name']}")
        self.updates_found += 1
        self.updated_apps.append(f"{app_name} {update_info['tag_name']}{' (NEW)' if is_new else ''}")

        # Resolve description via shared cache:
        # 1. list_hb.json description (already Ukrainian) → used directly, no GPT
        # 2. hb_descriptions.json cache hit → used directly
        # 3. GitHub release body → GPT translate → save to cache
        slug = self._extract_github_slug(entry['api_url']) or entry['api_url']
        description = await self._get_description_cached(
            cache_key=f'github:{slug}',
            local_entry=entry,
            raw_text='',  # GitHub Phase 2 has no raw API description
            fallback_name=app_name,
        )

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
            platform=entry['platform'],
            timestamp=datetime.now(),
            release_date=update_date,
            is_new=is_new
        )

        # Update dynamic state
        self._state[api_url] = {
            'comm_date': update_info['date'],
            'tag_name': update_info['tag_name'],
            'html_url': update_info['html_url']
        }

        return True

    async def collect_udb_updates(self, local_entries: List[Dict]) -> Set[str]:
        """
        Phase 1: Fetch all 3DS/DS apps from Universal-DB API.
        Returns a set of GitHub slugs ('owner/repo') that were covered by UDB,
        so the main GitHub/GitLab phase can skip them.
        """
        logger.info("=== Phase 1: Universal-DB (3DS/DS) ===")

        # Initialize default stats in case of failure or empty response
        self.source_stats['UDB (3DS/DS)'] = {'checked': 0, 'found': 0}

        # Build a lookup: github_slug -> local list_hb entry (for description priority)
        local_by_slug: Dict[str, Dict] = {}
        for entry in local_entries:
            if entry.get('platform', '') in UDB_CATEGORIES:
                slug = self._extract_github_slug(entry.get('api_url', ''))
                if slug:
                    local_by_slug[slug] = entry

        # Fetch all UDB apps
        try:
            async with self.session.get(UDB_API_URL, headers=BROWSER_HEADERS, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"UDB API returned {resp.status} — skipping UDB phase")
                    self.source_stats['UDB (3DS/DS)']['error'] = True
                    self.source_stats['UDB (3DS/DS)']['error_msg'] = f"HTTP {resp.status}"
                    return set()
                udb_data = await resp.json()
                self.udb_requests += 1
        except Exception as e:
            logger.error(f"UDB API request failed: {e} — skipping UDB phase")
            self.source_stats['UDB (3DS/DS)']['error'] = True
            self.source_stats['UDB (3DS/DS)']['error_msg'] = str(e)
            return set()

        # Convert list to dict for compatibility if needed
        if isinstance(udb_data, list):
            udb_data = {app.get('slug'): app for app in udb_data if app.get('slug')}

        # udb_data is a dict: {slug: app_object}
        if not isinstance(udb_data, dict):
            logger.error(f"Unexpected UDB response format: {type(udb_data)}")
            self.source_stats['UDB (3DS/DS)']['error'] = True
            self.source_stats['UDB (3DS/DS)']['error_msg'] = "Unexpected response format"
            return set()

        logger.info(f"Fetched {len(udb_data)} apps from Universal-DB")

        covered_github_slugs: Set[str] = set()
        first_run_initialized = 0
        updates_from_udb = 0
        udb_checked = 0

        for udb_slug, udb_app in udb_data.items():
            systems = [s.upper() for s in udb_app.get('systems', [])]
            if not any(s in ('3DS', 'DS') for s in systems):
                continue
            udb_checked += 1

            # Mark GitHub slug as covered
            github_url = udb_app.get('github', '')
            gh_slug = self._extract_github_slug(github_url)
            if gh_slug:
                covered_github_slugs.add(gh_slug.lower())

            current_version = udb_app.get('version') or ''
            current_updated = udb_app.get('updated') or ''

            saved = self._udb_state.get(udb_slug, {})
            saved_version = saved.get('version', '')
            saved_updated = saved.get('updated', '')

            # First run for this slug: just save state, don't post
            if not saved_version and not saved_updated:
                self._udb_state.setdefault(udb_slug, {})
                self._udb_state[udb_slug]['version'] = current_version
                self._udb_state[udb_slug]['updated'] = current_updated
                self._udb_state[udb_slug]['release_url'] = (
                    udb_app.get('download_page') or github_url or ''
                )
                first_run_initialized += 1
                continue

            # Check if version or updated timestamp changed
            version_changed = current_version and current_version != saved_version
            updated_changed = current_updated and current_updated != saved_updated
            if not version_changed and not updated_changed:
                continue

            # Found an update!
            app_title = udb_app.get('title', udb_slug)
            if self.is_unprocessed_manual(app_title):
                logger.info(f"Skipping UDB update for {app_title} — pending manual release. Updating state only.")
                self._udb_state[udb_slug] = {
                    'version': current_version,
                    'updated': current_updated,
                    'release_url': udb_app.get('download_page') or github_url or ''
                }
                continue
            logger.info(f"UDB update: {app_title} {current_version} (was {saved_version})")

            # Resolve local entry for this UDB app
            local_entry = local_by_slug.get((gh_slug or '').lower()) if gh_slug else None

            # Get description (priority chain)
            description = await self._get_description_for_udb_app(
                udb_slug, udb_app, local_entry
            )

            # Summarize update notes if available
            update_notes_text = udb_app.get('update_notes') or udb_app.get('update_notes_md') or ''
            summarized_notes = None
            if update_notes_text.strip():
                summarized_notes = await self.summarize_and_translate_notes(update_notes_text)

            # Determine release URL
            release_url = udb_app.get('download_page') or github_url or ''

            # Determine release date
            try:
                release_date = datetime.fromisoformat(
                    current_updated.replace('Z', '+00:00')
                ) if current_updated else datetime.now()
            except Exception:
                release_date = datetime.now()

            # Determine category for digest
            # Use local entry category if available, otherwise derive from UDB systems
            if local_entry:
                platform = local_entry.get('platform', '3DS')
            else:
                platform = '/'.join(systems).replace('DS', 'DS(i)')

            # Build final description (append summarized notes if available)
            final_description = description
            if summarized_notes:
                final_description = f"{description}\n<i>{summarized_notes}</i>"

            # Add to digest
            homebrew_digest_manager.add_entry(
                app_name=app_title,
                version=current_version,
                release_url=release_url,
                description=final_description,
                platform=platform,
                timestamp=datetime.now(),
                release_date=release_date,
                is_new=False,
            )

            # Update UDB state
            self._udb_state[udb_slug]['version'] = current_version
            self._udb_state[udb_slug]['updated'] = current_updated
            self._udb_state[udb_slug]['release_url'] = release_url

            updates_from_udb += 1
            self.updates_found += 1
            self.updated_apps.append(f"{app_title} {current_version} [UDB]")

        logger.info(
            f"UDB phase complete: {updates_from_udb} updates, "
            f"{first_run_initialized} new entries initialized, "
            f"{len(covered_github_slugs)} GitHub repos covered"
        )
        self.source_stats['UDB (3DS/DS)'] = {'checked': udb_checked, 'found': updates_from_udb}
        return covered_github_slugs

    async def collect_fortheusers_updates(
        self,
        platform: str,
        repo_url: str,
        key_prefix: str,
        list_categories: Set[str],
        local_entries: List[Dict],
    ) -> Set[str]:
        """
        Fetch all apps from a fortheusers repo.json and detect updates.
        Returns set of GitHub slugs ('owner/repo') covered by this repo.
        platform: 'Switch' or 'WiiU'
        key_prefix: 'switch-hb' or 'wiiu-hb'
        """
        logger.info(f"=== Phase 1 [{platform}]: {repo_url} ===")

        # Initialize default stats
        self.source_stats[f'{platform} (FTU)'] = {'checked': 0, 'found': 0}

        # Build lookup: github_slug -> local list_hb entry (for description/platform)
        local_by_gh_slug: Dict[str, Dict] = {}
        for entry in local_entries:
            if entry.get('platform', '') in list_categories:
                gh_slug = self._extract_github_slug(entry.get('api_url', ''))
                if gh_slug:
                    local_by_gh_slug[gh_slug.lower()] = entry

        # Also match via the web GitHub URL in fortheusers 'url' field
        local_by_gh_slug_web: Dict[str, Dict] = {}
        for entry in local_entries:
            if entry.get('platform', '') in list_categories:
                gh_slug = self._extract_github_slug(entry.get('api_url', ''))
                if gh_slug:
                    local_by_gh_slug_web[gh_slug.lower()] = entry

        try:
            async with self.session.get(repo_url, headers=BROWSER_HEADERS, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"ForTheUsers [{platform}] API returned {resp.status} — skipping")
                    self.source_stats[f'{platform} (FTU)']['error'] = True
                    self.source_stats[f'{platform} (FTU)']['error_msg'] = f"HTTP {resp.status}"
                    return set()
                repo_data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"ForTheUsers [{platform}] request failed: {e} — skipping")
            self.source_stats[f'{platform} (FTU)']['error'] = True
            self.source_stats[f'{platform} (FTU)']['error_msg'] = str(e)
            return set()

        packages = repo_data.get('packages', [])
        if not isinstance(packages, list):
            logger.error(f"ForTheUsers [{platform}] unexpected format")
            return set()

        logger.info(f"Fetched {len(packages)} packages from ForTheUsers [{platform}]")

        covered_github_slugs: Set[str] = set()
        first_run_initialized = 0
        updates_found = 0
        ftu_checked = 0

        for pkg in packages:
            name = pkg.get('name', '')
            if not name:
                continue
            ftu_checked += 1

            state_key = f"{key_prefix}:{name}"

            # Extract GitHub slug from 'url' field for matching and coverage tracking
            pkg_url = pkg.get('url', '')
            gh_slug = self._extract_github_slug(pkg_url)
            if gh_slug:
                covered_github_slugs.add(gh_slug.lower())

            current_version = pkg.get('version', '')
            current_updated = pkg.get('updated', '')  # format: DD/MM/YYYY

            saved = self._fortheusers_state.get(state_key, {})
            saved_version = saved.get('version', '')
            saved_updated = saved.get('updated', '')

            # First run: save state, don't post
            if not saved_version and not saved_updated:
                self._fortheusers_state[state_key] = {
                    'version': current_version,
                    'updated': current_updated,
                }
                first_run_initialized += 1
                continue

            # Check for changes
            if current_version == saved_version and current_updated == saved_updated:
                continue

            # Found update!
            app_title = pkg.get('title', name)
            if self.is_unprocessed_manual(app_title):
                logger.info(f"Skipping FTU update for {app_title} — pending manual release. Updating state only.")
                self._fortheusers_state[state_key] = {
                    'version': current_version,
                    'updated': current_updated,
                }
                continue
            logger.info(f"ForTheUsers [{platform}] update: {app_title} {current_version} (was {saved_version})")

            # Resolve local entry
            local_entry = local_by_gh_slug.get((gh_slug or '').lower()) if gh_slug else None

            # Get description (priority chain via shared cache)
            raw_desc = pkg.get('details') or pkg.get('description') or ''
            description = await self._get_description_cached(
                cache_key=state_key,
                local_entry=local_entry,
                raw_text=raw_desc,
                fallback_name=app_title,
            )

            # Summarize latest changelog block
            changelog_raw = pkg.get('changelog', '')
            latest_cl = self._extract_latest_changelog(changelog_raw)
            summarized_notes = None
            if latest_cl:
                summarized_notes = await self.summarize_and_translate_notes(latest_cl)

            # Release date from DD/MM/YYYY
            release_date = datetime.now()
            if current_updated:
                try:
                    release_date = datetime.strptime(current_updated, '%d/%m/%Y')
                except ValueError:
                    pass

            # Release URL
            release_url = pkg_url or ''

            # Platform from local entry if available
            display_platform = local_entry.get('platform', platform) if local_entry else platform

            # Final description with notes
            final_description = description
            if summarized_notes:
                final_description = f"{description}\n<i>{summarized_notes}</i>"

            homebrew_digest_manager.add_entry(
                app_name=app_title,
                version=current_version,
                release_url=release_url,
                description=final_description,
                platform=display_platform,
                timestamp=datetime.now(),
                release_date=release_date,
                is_new=False,
            )

            # Update state
            self._fortheusers_state[state_key] = {
                'version': current_version,
                'updated': current_updated,
            }

            updates_found += 1
            self.updates_found += 1
            self.updated_apps.append(f"{app_title} {current_version} [{platform}/FTU]")

        logger.info(
            f"ForTheUsers [{platform}] complete: {updates_found} updates, "
            f"{first_run_initialized} initialized, {len(covered_github_slugs)} GitHub repos covered"
        )
        self.source_stats[f'{platform} (FTU)'] = {'checked': ftu_checked, 'found': updates_found}
        return covered_github_slugs

    async def collect_vitadb_updates(
        self,
        endpoint_url: str,
        key_prefix: str,
        platform_name: str,
        local_entries: List[Dict],
    ) -> Set[str]:
        """
        Fetch apps from a VitaDB endpoint and detect updates.
        Returns set of GitHub slugs ('owner/repo') covered by this source.

        endpoint_url: one of the 3 vitadb POST endpoints
        key_prefix: 'vita-hb', 'vita-plugin', or 'vita-tool'
        platform_name: 'PSVita', 'PSVita Plugin', or 'PSVita PC Tool'
        """
        logger.info(f"=== Phase 1d [{platform_name}]: {endpoint_url} ===")

        # Initialize default stats
        self.source_stats[platform_name] = {'checked': 0, 'found': 0}

        # Build local lookup: github_slug -> list_hb entry (Vita platform)
        local_by_gh_slug: Dict[str, Dict] = {}
        for entry in local_entries:
            if entry.get('platform', '') in VITA_CATEGORIES:
                gh_slug = self._extract_github_slug(entry.get('api_url', ''))
                if gh_slug:
                    local_by_gh_slug[gh_slug.lower()] = entry

        try:
            # VitaDB requires POST request with no body
            async with self.session.post(endpoint_url, headers=BROWSER_HEADERS, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"VitaDB [{platform_name}] returned {resp.status} — skipping")
                    self.source_stats[platform_name]['error'] = True
                    self.source_stats[platform_name]['error_msg'] = f"HTTP {resp.status}"
                    return set()
                packages = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"VitaDB [{platform_name}] request failed: {e} — skipping")
            self.source_stats[platform_name]['error'] = True
            self.source_stats[platform_name]['error_msg'] = str(e)
            return set()

        if not isinstance(packages, list):
            logger.error(f"VitaDB [{platform_name}] unexpected response format")
            return set()

        logger.info(f"Fetched {len(packages)} entries from VitaDB [{platform_name}]")

        covered_github_slugs: Set[str] = set()
        first_run_initialized = 0
        updates_found = 0
        vita_checked = 0

        for pkg in packages:
            pkg_id = str(pkg.get('id', ''))
            if not pkg_id:
                continue

            # Skip inactive entries
            if str(pkg.get('status', '0')) != '0':
                continue
            vita_checked += 1

            state_key = f"{key_prefix}:{pkg_id}"

            # Track GitHub coverage for Phase 2 skip logic
            source_url = pkg.get('source', '')
            gh_slug = self._extract_github_slug(source_url)
            if gh_slug:
                covered_github_slugs.add(gh_slug.lower())

            current_version = pkg.get('version', '')
            current_date = pkg.get('date', '')  # format: YYYY-MM-DD

            saved = self._vitadb_state.get(state_key, {})
            saved_version = saved.get('version', '')
            saved_date = saved.get('date', '')

            # First run: save state, don't post
            if not saved_version and not saved_date:
                self._vitadb_state[state_key] = {
                    'version': current_version,
                    'date': current_date,
                }
                first_run_initialized += 1
                continue

            # Check for changes
            if current_version == saved_version and current_date == saved_date:
                continue

            # Found an update!
            app_name = pkg.get('name', f"App {pkg_id}")
            if self.is_unprocessed_manual(app_name):
                logger.info(f"Skipping VitaDB update for {app_name} — pending manual release. Updating state only.")
                self._vitadb_state[state_key] = {
                    'version': current_version,
                    'date': current_date,
                }
                continue
            logger.info(
                f"VitaDB [{platform_name}] update: {app_name} {current_version} (was {saved_version})"
            )

            # Resolve local entry for description priority
            local_entry = local_by_gh_slug.get((gh_slug or '').lower()) if gh_slug else None

            # Get description via shared cache
            raw_desc = pkg.get('long_description') or pkg.get('description') or ''
            description = await self._get_description_cached(
                cache_key=state_key,
                local_entry=local_entry,
                raw_text=raw_desc,
                fallback_name=app_name,
            )

            # Summarize changelog
            changelog_raw = pkg.get('changelog', '')
            latest_cl = self._extract_latest_changelog(changelog_raw)
            summarized_notes = None
            if latest_cl:
                summarized_notes = await self.summarize_and_translate_notes(latest_cl)

            # Release date from YYYY-MM-DD
            release_date = datetime.now()
            if current_date:
                try:
                    release_date = datetime.strptime(current_date, '%Y-%m-%d')
                except ValueError:
                    pass

            # Release URL: prefer release_page, fallback to source
            release_url = pkg.get('release_page') or source_url or ''

            # Final description with notes
            final_description = description
            if summarized_notes:
                final_description = f"{description}\n<i>{summarized_notes}</i>"

            homebrew_digest_manager.add_entry(
                app_name=app_name,
                version=current_version,
                release_url=release_url,
                description=final_description,
                platform=platform_name,
                timestamp=datetime.now(),
                release_date=release_date,
                is_new=False,
            )

            # Update state
            self._vitadb_state[state_key] = {
                'version': current_version,
                'date': current_date,
            }

            updates_found += 1
            self.updates_found += 1
            self.updated_apps.append(f"{app_name} {current_version} [{platform_name}/VitaDB]")

        logger.info(
            f"VitaDB [{platform_name}] complete: {updates_found} updates, "
            f"{first_run_initialized} initialized, {len(covered_github_slugs)} GitHub repos covered"
        )
        self.source_stats[platform_name] = {'checked': vita_checked, 'found': updates_found}
        return covered_github_slugs

    async def collect_updates(self, translate: bool = True, max_entries: Optional[int] = None):
        """Collect all homebrew updates"""
        entries = self.load_homebrew_list()

        if not entries:
            logger.error("No entries to process")
            return

        # Load states
        self._udb_state = self.load_udb_state()
        self._fortheusers_state = self.load_fortheusers_state()
        self._vitadb_state = self.load_vitadb_state()
        self._descriptions = self.load_descriptions_cache()

        # Phase 1a: Universal-DB (3DS/DS) — primary source
        covered = await self.collect_udb_updates(entries)

        # Phase 1b: Switch fortheusers repo
        covered |= await self.collect_fortheusers_updates(
            platform='Switch',
            repo_url=SWITCH_REPO_URL,
            key_prefix='switch-hb',
            list_categories=SWITCH_FTU_CATEGORIES,
            local_entries=entries,
        )

        # Phase 1c: WiiU fortheusers repo
        covered |= await self.collect_fortheusers_updates(
            platform='WiiU',
            repo_url=WIIU_REPO_URL,
            key_prefix='wiiu-hb',
            list_categories=WIIU_FTU_CATEGORIES,
            local_entries=entries,
        )

        # Phase 1d: VitaDB (PS Vita) — homebrews, plugins, tools
        for endpoint_url, key_prefix, platform_name in VITADB_ENDPOINTS:
            vita_covered = await self.collect_vitadb_updates(
                endpoint_url=endpoint_url,
                key_prefix=key_prefix,
                platform_name=platform_name,
                local_entries=entries,
            )
            covered |= vita_covered

        covered_github_slugs = {s.lower() for s in covered}

        # Save all states and descriptions cache
        self.save_udb_state()
        self.save_fortheusers_state()
        self.save_vitadb_state()
        self.save_descriptions_cache()

        # Phase 2: GitHub/GitLab — skip entries already covered by repo sources
        all_covered_categories = UDB_CATEGORIES | SWITCH_FTU_CATEGORIES | WIIU_FTU_CATEGORIES | VITA_CATEGORIES
        udb_skipped = 0
        filtered_entries = []
        for entry in entries:
            if entry.get('platform', '') in all_covered_categories:
                gh_slug = self._extract_github_slug(entry.get('api_url', ''))
                if gh_slug and gh_slug.lower() in covered_github_slugs:
                    udb_skipped += 1
                    continue
            filtered_entries.append(entry)

        logger.info(
            f"=== Phase 2: GitHub/GitLab ({len(filtered_entries)} entries, "
            f"{udb_skipped} skipped — covered by repo sources) ==="
        )

        entries = filtered_entries
        github_total = len(entries)

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

        # Save dynamic state (always, regardless of mode)
        self.save_state()

        # Remove 'new' flag from processed entries in the static registry
        from core.settings_loader import IS_TEST_MODE
        if new_entries_processed and not IS_TEST_MODE:
            logger.info(f"Removing 'new' flag from {len(new_entries_processed)} processed entries...")

            # Reload static registry (without merging state)
            try:
                with open(self.list_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
            except Exception as e:
                logger.error(f"Error reloading registry: {e}")
                registry = None

            if registry:
                for index in new_entries_processed:
                    if index < len(registry) and registry[index].get('new'):
                        del registry[index]['new']
                        logger.info(f"Removed 'new' flag from {registry[index]['app_name']}")

                try:
                    with open(self.list_path, 'w', encoding='utf-8') as f:
                        json.dump(registry, f, ensure_ascii=False, indent=2)
                    logger.info(f"Updated {self.list_path} - removed 'new' flags")
                except Exception as e:
                    logger.error(f"Error saving registry: {e}")
        elif new_entries_processed and IS_TEST_MODE:
            logger.info(f"TEST MODE: Would remove 'new' flag from {len(new_entries_processed)} entries in production")

        # Track GitHub/GitLab stats
        self.source_stats['GitHub/GitLab'] = {'checked': github_total, 'found': self.updates_found - sum(s['found'] for s in self.source_stats.values())}

        # Save stats for digest sender
        try:
            os.makedirs('data', exist_ok=True)
            with open(HB_STATS_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.source_stats, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved collector stats to {HB_STATS_PATH}")
        except Exception as e:
            logger.error(f"Error saving collector stats: {e}")

        # Summary
        logger.info("=" * 60)
        logger.info(f"Collection complete!")
        logger.info(f"Total entries processed: {total}")
        logger.info(f"Updates found: {self.updates_found}")

        if self.updated_apps:
            logger.info("Updated Apps List:")
            for app in self.updated_apps:
                logger.info(f"  - {app}")

        logger.info(f"UDB requests: {self.udb_requests}")
        logger.info(f"GitHub requests: {self.github_requests}")
        logger.info(f"GitLab requests: {self.gitlab_requests}")
        logger.info(f"Errors: {len(self.errors)}")

        if self.errors:
            logger.warning("Errors encountered:")
            for error in self.errors[:10]:  # Show first 10 errors
                logger.warning(f"  - {error}")





async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Collect homebrew updates')
    parser.add_argument('--list', default=DEFAULT_LIST_PATH,
                        help='Path to list_hb.json (static registry)')
    parser.add_argument('--state', default=DEFAULT_STATE_PATH,
                        help='Path to hb_state.json (dynamic state)')
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
            from core.settings_loader import settings
            if not github_token:
                github_token = settings.get('GITHUB_TOKEN')
            if not gitlab_token:
                gitlab_token = settings.get('GITLAB_TOKEN')
        except Exception as e:
            logger.warning(f"Could not load tokens from settings: {e}")

    # Debug: log token status (without revealing the token)
    logger.info(f"GitHub token: {'present' if github_token else 'missing'}")
    logger.info(f"GitLab token: {'present' if gitlab_token else 'missing'}")

    collector = HomebrewUpdatesCollector(
        list_path=args.list,
        state_path=args.state,
        github_token=github_token,
        gitlab_token=gitlab_token
    )
    await collector.collect_updates(
        translate=args.translate,
        max_entries=args.test
    )

    # Clean up shared session
    from core.settings_loader import close_clients
    await close_clients()


if __name__ == "__main__":
    asyncio.run(main())
