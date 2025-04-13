# --- START OF FILE youtube_search.py ---
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
try: from settings_loader import LOG
except ImportError: LOG = True
from typing import Optional, Tuple
import os, time, shutil, traceback, json
try:
    import yt_dlp; YTDLP_AVAILABLE = True
except ImportError: print("WARNING: yt-dlp missing. pip install yt-dlp"); YTDLP_AVAILABLE = False

_SCRIPT_DIR_YT = os.path.dirname(os.path.abspath(__file__))
VIDEO_DOWNLOAD_DIR = os.path.join(_SCRIPT_DIR_YT, "tmp_videos")

def search_trailer_on_youtube(game_title: str, api_key: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not api_key: return None, None
    cleaned_game_title = re.sub(r'\[.*?\]', '', game_title).strip(); cleaned_game_title = re.sub(r'\b(Deluxe|Ultimate|Gold|Standard|Complete|GOTY|Edition)\b', '', cleaned_game_title, flags=re.IGNORECASE).strip(); cleaned_game_title = re.sub(r'[^\w\s\-\:]+$', '', cleaned_game_title).strip()
    if not cleaned_game_title: return None, None
    search_queries = [f'"{cleaned_game_title}" Nintendo Switch Official Trailer', f"{cleaned_game_title} Nintendo Switch Trailer", f"{cleaned_game_title} Switch Gameplay Trailer", f"{cleaned_game_title} Nintendo Switch Gameplay", f"{cleaned_game_title} Official Trailer", f"{cleaned_game_title} Gameplay"]
    # --- FIX: Moved check inside ---
    if '/' in cleaned_game_title:
        base_title = cleaned_game_title.split('/', 1)[0].strip()
        # Only add base_title queries if it's actually different and not empty
        if base_title and base_title != cleaned_game_title:
            search_queries.insert(1, f'"{base_title}" Nintendo Switch Gameplay')
            search_queries.insert(2, f'"{base_title}" Nintendo Switch Trailer')
    # --- End FIX ---
    # if LOG: print(f"Cleaned game title for YouTube search: '{cleaned_game_title}'")
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        for query in search_queries:
            try:
                search_response = youtube.search().list(q=query, part="id,snippet", type="video", order="relevance", maxResults=1, relevanceLanguage="en", videoDefinition="high").execute()
                items = search_response.get("items", [])
                if items: video = items[0]; video_id = video["id"]["videoId"]; video_title = video["snippet"]["title"]; trailer_url = f"https://www.youtube.com/watch?v={video_id}"; print(f"Found video: '{video_title}' - URL: {trailer_url} (Query: '{query}')"); return trailer_url, video_title
            except HttpError as e:
                 print(f"YT HTTP error (Query: '{query}'): {e}")
                 if hasattr(e, 'resp') and e.resp.status == 403: print("Quota likely exceeded.")
            except Exception as e:
                 print(f"YT unexpected error (Query: '{query}'): {e}")
        return None, None
    except Exception as e: print(f"Failed to build YouTube API service: {e}"); return None, None

# --- download_youtube_video using yt-dlp ---
# (download_youtube_video remains unchanged)
def download_youtube_video(video_url: str, video_id: str, max_filesize_mb: int = 48) -> Optional[str]:
    if not YTDLP_AVAILABLE: print("yt-dlp not available."); return None
    if not video_url or not video_id: return None
    max_bytes = max_filesize_mb * 1024 * 1024; os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)
    output_template = os.path.join(VIDEO_DOWNLOAD_DIR, f'{video_id}.%(ext)s'); downloaded_file_path = None; best_format_id = None; final_filename = None # Initialize final_filename
    # Step 1: Get available formats
    ydl_opts_info = {'quiet': True, 'no_warnings': True, 'listformats': False, 'skip_download': True, 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl: info_dict = ydl.extract_info(video_url, download=False); formats = info_dict.get('formats', [])
        eligible_formats = []
        if formats:
            for f in formats:
                filesize = f.get('filesize') or f.get('filesize_approx')
                if filesize is None or filesize > max_bytes: continue
                ext = f.get('ext'); vcodec = f.get('vcodec'); acodec = f.get('acodec')
                if ext == 'mp4' and vcodec != 'none' and acodec != 'none': eligible_formats.append(f)
                elif vcodec != 'none' and acodec != 'none': eligible_formats.append(f)
                elif ext == 'mp4' and vcodec != 'none' and f.get('format_note') != 'storyboard': eligible_formats.append(f)
        if not eligible_formats: print("No suitable formats found under the size limit."); return None
        eligible_formats.sort(key=lambda f: (f.get('height', 0), f.get('tbr', 0) or f.get('vbr', 0) or f.get('abr', 0)), reverse=True)
        best_format = eligible_formats[0]; best_format_id = best_format.get('format_id')
        filesize_mb = (best_format.get('filesize') or best_format.get('filesize_approx', 0)) / (1024*1024)
        print(f"Selected best format: ID={best_format_id}, Res={best_format.get('resolution', 'N/A')}, Ext={best_format.get('ext')}, Size={filesize_mb:.2f}MB")
    except yt_dlp.utils.DownloadError as e: print(f"yt-dlp Error getting video info: {e}"); return None
    except Exception as e: print(f"Unexpected error getting video info: {e}"); traceback.print_exc(); return None

    # Step 2: Download the selected format
    if best_format_id:
        potential_extensions = ['mp4', 'mkv', 'webm', 'part']
        for ext in potential_extensions:
             fpath = os.path.join(VIDEO_DOWNLOAD_DIR, f"{video_id}.{ext}")
             if os.path.exists(fpath):
                 try: os.remove(fpath); print(f"Removed existing file: {fpath}")
                 except OSError as e: print(f"Could not remove existing file {fpath}: {e}")
        ydl_opts_download = {'format': best_format_id, 'outtmpl': output_template, 'noplaylist': True, 'quiet': False, 'no_warnings': True, 'noprogress': False, 'retries': 3, 'socket_timeout': 30, 'merge_output_format': 'mp4'}
        download_success = False # Flag to track success
        try:
            print(f"Attempting download of format {best_format_id}..."); start_time = time.time()
            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl: ydl.download([video_url])
            # Find downloaded file again AFTER download completes
            for fname in os.listdir(VIDEO_DOWNLOAD_DIR):
                if fname.startswith(video_id) and not fname.endswith(".part"): final_filename = fname; break
            if final_filename:
                 downloaded_file_path = os.path.join(VIDEO_DOWNLOAD_DIR, final_filename); end_time = time.time()
                 filesize_mb = os.path.getsize(downloaded_file_path) / (1024*1024)
                 print(f"Download complete: {final_filename} ({filesize_mb:.2f} MB) in {end_time - start_time:.2f}s")
                 if os.path.getsize(downloaded_file_path) > max_bytes:
                      print(f"Downloaded video size exceeds limit. Deleting."); os.remove(downloaded_file_path)
                      downloaded_file_path = None # Set path to None if deleted
                 else:
                      download_success = True # Mark as success only if size is okay
            else: print("yt-dlp finished, but downloaded file not found.")
        except yt_dlp.utils.DownloadError as e: print(f"yt-dlp Download Error during final download: {e}")
        except Exception as e: print(f"Unexpected error during final yt-dlp download: {e}"); traceback.print_exc();
        finally: # Cleanup ONLY if download FAILED
             if not download_success and downloaded_file_path and os.path.exists(downloaded_file_path):
                 print(f"Cleaning up failed/oversized download: {downloaded_file_path}")
                 try: os.remove(downloaded_file_path)
                 except OSError: pass
                 downloaded_file_path = None # Ensure None is returned on failure

        return downloaded_file_path # Return path if successful, None otherwise
    else: print("No best format ID determined for download."); return None

# Testing Block
if __name__ == "__main__":
    print("--- Running youtube_search.py Tests (using yt-dlp 2-step) ---")
    print(f"\n--- Cleaning up temporary video files in {VIDEO_DOWNLOAD_DIR} before tests ---"); cleaned_count_pre = 0
    if os.path.isdir(VIDEO_DOWNLOAD_DIR):
        try:
            for filename in os.listdir(VIDEO_DOWNLOAD_DIR):
                file_path = os.path.join(VIDEO_DOWNLOAD_DIR, filename);
                if os.path.isfile(file_path) and filename.endswith(('.mp4', '.mkv', '.webm', '.part')):
                    try: os.remove(file_path); print(f"Pre-deleted: {filename}"); cleaned_count_pre += 1
                    except OSError as e: print(f"Error pre-deleting file {file_path}: {e}")
        except Exception as e: print(f"Error during pre-cleanup: {e}")
    else: os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)
    print(f"Pre-cleanup finished. Removed {cleaned_count_pre} files.")
    test_videos = {"Short Clip": "6RlIjgQf0UU"}
    successful_downloads = []
    for name, video_id in test_videos.items():
        print(f"\n======= Testing: {name} (ID: {video_id}) =======");
        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id != "InvalidID123" else "invalid_url"
        downloaded_path = download_youtube_video(video_url, video_id, max_filesize_mb=48)
        if downloaded_path: print(f"--> RESULT: Success, saved to: {downloaded_path}"); successful_downloads.append(downloaded_path)
        else: print(f"--> RESULT: Failed or skipped."); print("-" * 20); time.sleep(1)
    print(f"\n--- Keeping {len(successful_downloads)} temporary video files in {VIDEO_DOWNLOAD_DIR} for inspection ---")

# --- END OF FILE youtube_search.py ---