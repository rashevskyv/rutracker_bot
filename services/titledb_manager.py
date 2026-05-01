# --- START OF FILE titledb_manager.py ---

import json
import os
import re
import time
import traceback

from urllib.parse import urlparse
import shutil
import aiohttp
import asyncio
import logging
from io import BytesIO 
from typing import Optional, Dict, Any, List, Tuple, Set

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_REGIONS_TO_CHECK: List[Tuple[str, str]] = [
    ("GB", "en"), ("US", "en"), ("JP", "ja"),
]
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TMP_SCREENSHOT_DIR = os.path.join(_SCRIPT_DIR, "tmp_screenshots")

class TitleDBManager:
    def __init__(self, titledb_json_path: str, tmp_screenshot_dir: str = DEFAULT_TMP_SCREENSHOT_DIR):
        self.tmp_screenshot_dir = None; self.json_path = None
        potential_json_path = os.path.join(_SCRIPT_DIR, titledb_json_path) if not os.path.isabs(titledb_json_path) else titledb_json_path
        if os.path.isdir(potential_json_path): self.json_path = potential_json_path
        else: raise FileNotFoundError(f"TitleDB JSON directory not found at '{titledb_json_path}' (resolved: '{potential_json_path}')")
        potential_tmp_path = os.path.join(_SCRIPT_DIR, tmp_screenshot_dir) if not os.path.isabs(tmp_screenshot_dir) else tmp_screenshot_dir
        try:
            os.makedirs(potential_tmp_path, exist_ok=True); self.tmp_screenshot_dir = potential_tmp_path
            logger.info(f"TitleDBManager initialized: JSON Path='{self.json_path}', Temp Dir='{self.tmp_screenshot_dir}'")
        except OSError as e:
            logger.error(f"Error creating tmp dir '{potential_tmp_path}': {e}")
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}; self._last_load_time: Dict[Tuple[str, str], float] = {}
        self._cache_ttl_seconds = 3600

    def _normalize_title_for_comparison(self, text: str, remove_spaces=True) -> str:
        if not text: return ""
        cleaned = text.lower(); cleaned = cleaned.replace('™', '').replace('®', '').replace('©', '')
        cleaned = re.sub(r'[^\w\s\-]+', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(); cleaned = re.sub(r'\-+', '-', cleaned).strip('-')
        if remove_spaces: cleaned = cleaned.replace(' ', '').replace('-', '')
        return cleaned

    def _load_region_data(self, region: str, language: str) -> Optional[Dict[str, Any]]:
        region_key = (region.upper(), language.lower()); file_name = f"{region_key[0]}.{region_key[1]}.json"
        file_path = os.path.join(self.json_path, file_name); current_time = time.time()
        if region_key in self._cache and (current_time - self._last_load_time.get(region_key, 0)) < self._cache_ttl_seconds: return self._cache[region_key]
        if not os.path.isfile(file_path): return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
            self._cache[region_key] = data; self._last_load_time[region_key] = current_time; return data
        except Exception as e:
            logger.error(f"Error loading/parsing {file_path}: {e}")
        return None

    def find_game_data(self, game_title: str, regions_to_check: Optional[List[Tuple[str, str]]] = None) -> Optional[Dict[str, Any]]:
        if not game_title: return None
        if regions_to_check is None: regions_to_check = DEFAULT_REGIONS_TO_CHECK
        search_normalized_tight = self._normalize_title_for_comparison(game_title, remove_spaces=True)
        search_normalized_spaced = self._normalize_title_for_comparison(game_title, remove_spaces=False)
        title_before_colon = game_title.split(':', 1)[0].strip()
        search_before_colon_spaced = self._normalize_title_for_comparison(title_before_colon, remove_spaces=False) if title_before_colon != game_title else None
        words = search_normalized_spaced.split(); search_first_two_words = " ".join(words[:2]) if len(words) >= 2 else None
        if not search_normalized_tight: return None

        logger.debug(f"Searching titledb for '{game_title}' in regions: {[r[0] for r in regions_to_check]}")
        logger.debug(f"  Norm (tight): '{search_normalized_tight}' | Norm (spaced): '{search_normalized_spaced}'")
        if search_before_colon_spaced: logger.debug(f"  Before colon: '{search_before_colon_spaced}'")
        if search_first_two_words: logger.debug(f"  First two: '{search_first_two_words}'")

        found_ids: Set[str] = set(); best_match_level = 99; best_match_data = None

        for region, language in regions_to_check:
            region_data = self._load_region_data(region, language);
            if not region_data: continue
            for nsuid_str, game_db_data in region_data.items():
                if not isinstance(game_db_data, dict) or 'name' not in game_db_data: continue
                db_title_name = game_db_data['name']
                db_title_normalized_tight = self._normalize_title_for_comparison(db_title_name, remove_spaces=True)
                db_title_normalized_spaced = self._normalize_title_for_comparison(db_title_name, remove_spaces=False)
                title_id = game_db_data.get('id'); current_match_level = 99; match_type = ""

                if search_normalized_tight == db_title_normalized_tight: current_match_level = 1; match_type = "Exact tight"
                elif len(search_normalized_tight) >= 5 and search_normalized_tight in db_title_normalized_tight: current_match_level = 2; match_type = "Partial tight (search in DB)"
                elif search_before_colon_spaced and search_before_colon_spaced == db_title_normalized_spaced: current_match_level = 3; match_type = "Before colon spaced"
                elif search_first_two_words and db_title_normalized_spaced.startswith(search_first_two_words): current_match_level = 4; match_type = "First two words spaced"

                if current_match_level < best_match_level:
                    if title_id and title_id in found_ids and current_match_level >= best_match_level: continue
                    logger.debug(f"  Potential match ({match_type}, Lvl:{current_match_level}): '{db_title_name}' (R:{region})")
                    best_match_level = current_match_level; best_match_data = game_db_data
                    if title_id: found_ids.add(title_id)
                    if best_match_level == 1:
                        logger.info(f"Exact match found for '{game_title}' in {region}: '{db_title_name}'")

            if best_match_level == 1:
                 break

        if best_match_data:
            logger.info(f"Best match found (Level {best_match_level}): '{best_match_data.get('name')}'")
            return best_match_data
        else:
            logger.info(f"Game matching '{game_title}' not found after all checks.")
            return None

    def _get_file_extension_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                return ext
        except Exception: pass
        return ".jpg"

    async def _try_download_image(self, image_url: str, timeout: int = 15) -> Optional[BytesIO]:
        if not image_url or not image_url.startswith(('http://', 'https://')): return None
        try:
            from core.settings_loader import get_session
            session = get_session()
            async with session.get(image_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.read()
                if not content:
                    logger.warning(f"Download resulted in empty file: {image_url}")
                    return None
                return BytesIO(content)
        except Exception as e:
            logger.error(f"Download failed (Error: {e}): {image_url}")
            return None

    def _clear_tmp_dir(self):
        if not self.tmp_screenshot_dir or not os.path.isdir(self.tmp_screenshot_dir): return False
        logger.debug(f"Clearing temporary screenshot directory: {self.tmp_screenshot_dir}")
        cleared = True
        for filename in os.listdir(self.tmp_screenshot_dir):
            file_path = os.path.join(self.tmp_screenshot_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception as e:
                logger.error(f'Failed to delete {file_path}. Reason: {e}')
                cleared = False
        return cleared

    async def download_cover_image(self, image_url: str, timeout: int = 15) -> Optional[BytesIO]:
        fallback_url = 'https://via.placeholder.com/300x200.png?text=No+Image+Found'
        image = await self._try_download_image(image_url, timeout)
        if image: return image
        logger.warning(f"Cover download failed for {image_url}. Trying fallback...")
        if image_url != fallback_url:
            image = await self._try_download_image(fallback_url, timeout)
            if image:
                logger.info("Fallback image downloaded.")
                return image
            else:
                logger.warning("Fallback image download failed.")
        return None

    async def download_trailer_thumbnail(self, video_id: str, timeout: int = 15) -> Optional[BytesIO]:
        if not video_id: return None
        thumbnail_urls_to_try = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg", f"https://img.youtube.com/vi/{video_id}/sddefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg", f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/default.jpg",
        ]
        for url in thumbnail_urls_to_try:
            image = await self._try_download_image(url, timeout)
            if image:
                logger.debug(f"Successfully downloaded thumbnail: {url}")
                return image
        return None

    async def download_screenshots(self, screenshot_urls: List[str], nsuid: Optional[str] = None, game_title: Optional[str] = None, max_screenshots: int = 4) -> List[str]:
        if not self.tmp_screenshot_dir:
            logger.error("Temp screenshot dir not available.")
            return []
        if not screenshot_urls: return []
        self._clear_tmp_dir()
        if nsuid: file_prefix = str(nsuid)
        elif game_title: file_prefix = re.sub(r'[^\w\-]+', '_', game_title.lower()).strip('_')[:50]
        else: file_prefix = "unknown_game"
        urls_to_download = screenshot_urls[:max_screenshots]
        logger.info(f"Starting download of {len(urls_to_download)} screenshots for '{file_prefix}'...")
        downloaded_paths = []
        for i, url in enumerate(urls_to_download):
            if not url or not isinstance(url, str) or not url.startswith('http'): continue
            extension = self._get_file_extension_from_url(url); filename = f"{file_prefix}_{i}{extension}"
            save_path = os.path.join(self.tmp_screenshot_dir, filename)
            image_data: Optional[BytesIO] = await self._try_download_image(url) # Download first
            if image_data:
                try: # Save the downloaded data
                    with open(save_path, 'wb') as f_out: f_out.write(image_data.getbuffer())
                    downloaded_paths.append(save_path)
                except Exception as write_err:
                    logger.error(f"FAILED to save downloaded image to {save_path}: {write_err}")
            await asyncio.sleep(0.1)
        logger.info(f"Finished download. Successfully got {len(downloaded_paths)} screenshots.")
        return downloaded_paths

if __name__ == "__main__":
    # Minimal logging for direct tests
    logging.basicConfig(level=logging.INFO)
    test_titledb_json_path = "titledb"
    logger.info("--- Running TitleDBManager Tests ---")
    abs_test_path = os.path.join(_SCRIPT_DIR, test_titledb_json_path)
    if not os.path.exists(abs_test_path):
        logger.error(f"Test titledb JSON directory not found: '{abs_test_path}'")
    else:
        try:
            manager = TitleDBManager(titledb_json_path=test_titledb_json_path)
            # ... (test titles logic)
        except Exception as e:
            logger.error(f"Test Failed: {e}")
            traceback.print_exc()

# --- END OF FILE titledb_manager.py ---