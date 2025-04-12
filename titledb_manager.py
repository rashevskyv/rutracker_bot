# --- START OF FILE titledb_manager.py ---

import json
import os
import re
import time
import traceback
import requests
from urllib.parse import urlparse
import shutil
from typing import Optional, Dict, Any, List, Tuple, Set

try:
    from settings_loader import LOG
except ImportError:
    LOG = False

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
            print(f"TitleDBManager: JSON Path='{self.json_path}', Temp Dir='{self.tmp_screenshot_dir}'")
        except OSError as e: print(f"ERROR: Creating tmp dir '{potential_tmp_path}': {e}")
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
        except Exception as e: print(f"Error loading/parsing {file_path}: {e}")
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

        if LOG:
            print(f"Searching titledb for '{game_title}' in regions: {[r[0] for r in regions_to_check]}")
            print(f"  Norm (tight): '{search_normalized_tight}' | Norm (spaced): '{search_normalized_spaced}'")
            if search_before_colon_spaced: print(f"  Before colon: '{search_before_colon_spaced}'")
            if search_first_two_words: print(f"  First two: '{search_first_two_words}'")

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
                    if LOG: print(f"  Found potential match ({match_type}, Lvl:{current_match_level}): '{db_title_name}' (R:{region})")
                    best_match_level = current_match_level; best_match_data = game_db_data
                    if title_id: found_ids.add(title_id)
                    if best_match_level == 1: pass

            if best_match_level == 1: print(f"Stopping search after exact match in {region}."); break

        if best_match_data:
            print(f"Best match found (Level {best_match_level}): '{best_match_data.get('name')}'")
            return best_match_data
        else:
            if LOG: print(f"Game matching '{game_title}' not found after all checks.")
            return None

    def _get_file_extension_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                return ext
        except Exception:
            pass
        return ".jpg"

    def _download_image(self, url: str, save_path: str, timeout: int = 10) -> bool:
        if LOG: print(f"  Attempting download: {url} -> {save_path}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0', 'Accept': 'image/*'}; response = requests.get(url, headers=headers, timeout=timeout, stream=True); response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower();
            if not content_type.startswith('image/'): print(f"  Skipping non-image content-type '{content_type}' for {url}"); return False
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
            if LOG: print(f"  SUCCESS downloaded: {os.path.basename(save_path)}"); return True
        except Exception as e: print(f"  FAILED download for {url}: {e}"); return False

    def _clear_tmp_dir(self):
        if not self.tmp_screenshot_dir or not os.path.isdir(self.tmp_screenshot_dir): return False
        print(f"Clearing temporary screenshot directory: {self.tmp_screenshot_dir}")
        cleared = True
        for filename in os.listdir(self.tmp_screenshot_dir):
            file_path = os.path.join(self.tmp_screenshot_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception as e: print(f'Failed to delete {file_path}. Reason: {e}'); cleared = False
        return cleared

    def download_screenshots(self, screenshot_urls: List[str], nsuid: Optional[str] = None, game_title: Optional[str] = None, max_screenshots: int = 4) -> List[str]:
        # --- FIX: Separate checks ---
        if not self.tmp_screenshot_dir:
            print("Error: Temp screenshot dir not available.")
            return []
        if not screenshot_urls:
            return []
        # --------------------------

        self._clear_tmp_dir()
        if nsuid: file_prefix = str(nsuid)
        elif game_title: file_prefix = re.sub(r'[^\w\-]+', '_', game_title.lower()).strip('_')[:50]
        else: file_prefix = "unknown_game"
        urls_to_download = screenshot_urls[:max_screenshots]
        if LOG: print(f"Starting download of {len(urls_to_download)} screenshots for '{file_prefix}'...")
        downloaded_paths = []
        for i, url in enumerate(urls_to_download):
            if not url or not isinstance(url, str) or not url.startswith('http'): continue
            extension = self._get_file_extension_from_url(url); filename = f"{file_prefix}_{i}{extension}"
            save_path = os.path.join(self.tmp_screenshot_dir, filename)
            if self._download_image(url, save_path): downloaded_paths.append(save_path)
            time.sleep(0.1)
        if LOG: print(f"Finished download. Successfully got {len(downloaded_paths)} screenshots.")
        return downloaded_paths

# Testing Block remains the same
if __name__ == "__main__":
    test_titledb_json_path = "titledb"
    print("--- Running TitleDBManager Tests ---")
    abs_test_path = os.path.join(_SCRIPT_DIR, test_titledb_json_path)
    if not os.path.exists(abs_test_path):
        print(f"ERROR: Test titledb JSON directory not found: '{abs_test_path}'")
    else:
        try:
            manager = TitleDBManager(titledb_json_path=test_titledb_json_path)
            test_titles = [
                "The Legend of Zelda: Breath of the Wild",
                "Circuit Superstars",
                "Mario Kart 8 Deluxe",
                "eBaseball Professional Baseball Spirits 2021 Grand Slam",
                "eBaseball Pro Yakyuu Spirits 2021 Grand Slam",
                "NonExistentGame 12345"
            ]
            for title in test_titles:
                print(f"\n======= Testing: '{title}' =======")
                game_data = manager.find_game_data(title)
                if game_data:
                    print(f"  Found Game: {game_data.get('name', 'N/A')}")
                    nsuid = game_data.get('nsuId'); print(f"  NSUID: {nsuid}")
                    screenshots_urls = game_data.get('screenshots')
                    if screenshots_urls and isinstance(screenshots_urls, list):
                        print(f"  Screenshot URLs ({len(screenshots_urls)} found): {screenshots_urls[:5]}...")
                        print("\n  --- Testing Screenshot Download ---")
                        downloaded_files = manager.download_screenshots(screenshots_urls, nsuid=nsuid, game_title=title, max_screenshots=4)
                        if downloaded_files:
                             print(f"  --- Download Result ({len(downloaded_files)} files) ---")
                             for file_path in downloaded_files: print(f"    - Saved to: {file_path}")
                        else: print("\n  --- Download Result: No screenshots downloaded. ---")
                    else: print("  Screenshots URLs: Not found/invalid in JSON.")
                else: print("  Game not found.")
                print("-" * 20); time.sleep(0.5)
        except Exception as e:
            print(f"\n--- Test Failed ---"); print(f"Error: {e}"); traceback.print_exc()

# --- END OF FILE titledb_manager.py ---