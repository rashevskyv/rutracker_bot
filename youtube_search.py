# --- START OF FILE youtube_search.py ---
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
from typing import Optional, Tuple
import os, time, shutil, traceback, json
import asyncio

logger = logging.getLogger(__name__)

try:
    import yt_dlp; YTDLP_AVAILABLE = True
except ImportError:
    logger.warning("yt-dlp missing. pip install yt-dlp")
    YTDLP_AVAILABLE = False

_SCRIPT_DIR_YT = os.path.dirname(os.path.abspath(__file__))
VIDEO_DOWNLOAD_DIR = os.path.join(_SCRIPT_DIR_YT, "tmp_videos")

async def search_trailer_on_youtube(game_title: str, api_key: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not api_key: return None, None
    cleaned_game_title = re.sub(r'\[.*?\]', '', game_title).strip()
    cleaned_game_title = re.sub(r'\b(Deluxe|Ultimate|Gold|Standard|Complete|GOTY|Edition)\b', '', cleaned_game_title, flags=re.IGNORECASE).strip()
    cleaned_game_title = re.sub(r'[^\w\s\-\:]+$', '', cleaned_game_title).strip()
    if not cleaned_game_title: return None, None
    
    search_queries = [
        f'"{cleaned_game_title}" Nintendo Switch Official Trailer',
        f"{cleaned_game_title} Nintendo Switch Trailer",
        f"{cleaned_game_title} Switch Gameplay Trailer",
        f"{cleaned_game_title} Nintendo Switch Gameplay",
        f"{cleaned_game_title} Official Trailer",
        f"{cleaned_game_title} Gameplay"
    ]
    
    if '/' in cleaned_game_title:
        base_title = cleaned_game_title.split('/', 1)[0].strip()
        if base_title and base_title != cleaned_game_title:
            search_queries.insert(1, f'"{base_title}" Nintendo Switch Gameplay')
            search_queries.insert(2, f'"{base_title}" Nintendo Switch Trailer')

    try:
        youtube = await asyncio.to_thread(build, "youtube", "v3", developerKey=api_key)
        for query in search_queries:
            try:
                list_call = youtube.search().list(q=query, part="id,snippet", type="video", order="relevance", maxResults=1, relevanceLanguage="en", videoDefinition="high")
                search_response = await asyncio.to_thread(list_call.execute)
                items = search_response.get("items", [])
                if items:
                    video = items[0]
                    video_id = video["id"]["videoId"]
                    video_title = video["snippet"]["title"]
                    trailer_url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info(f"Found video: '{video_title}' - URL: {trailer_url} (Query: '{query}')")
                    return trailer_url, video_title
            except HttpError as e:
                 logger.error(f"YT HTTP error (Query: '{query}'): {e}")
                 if hasattr(e, 'resp') and e.resp.status == 403:
                     logger.error("Quota likely exceeded.")
            except Exception as e:
                 logger.error(f"YT unexpected error (Query: '{query}'): {e}")
        return None, None
    except Exception as e:
        logger.error(f"Failed to build YouTube API service: {e}")
        return None, None

async def download_youtube_video(video_url: str, video_id: str, max_filesize_mb: int = 48) -> Optional[str]:
    if not YTDLP_AVAILABLE:
        logger.warning("yt-dlp not available for download.")
        return None
    if not video_url or not video_id: return None
    max_bytes = max_filesize_mb * 1024 * 1024
    os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)
    output_template = os.path.join(VIDEO_DOWNLOAD_DIR, f'{video_id}.%(ext)s')
    downloaded_file_path = None
    best_format_id = None
    final_filename = None

    ydl_opts_info = {'quiet': True, 'no_warnings': True, 'listformats': False, 'skip_download': True, 'noplaylist': True}
    def get_info():
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
             return ydl.extract_info(video_url, download=False)
    
    try:
        info_dict = await asyncio.to_thread(get_info)
        formats = info_dict.get('formats', [])
        eligible_formats = []
        if formats:
            for f in formats:
                filesize = f.get('filesize') or f.get('filesize_approx')
                if filesize is None or filesize > max_bytes: continue
                ext = f.get('ext'); vcodec = f.get('vcodec'); acodec = f.get('acodec')
                if ext == 'mp4' and vcodec != 'none' and acodec != 'none': eligible_formats.append(f)
                elif vcodec != 'none' and acodec != 'none': eligible_formats.append(f)
                elif ext == 'mp4' and vcodec != 'none' and f.get('format_note') != 'storyboard': eligible_formats.append(f)
        if not eligible_formats:
            logger.warning("No suitable formats found under the size limit.")
            return None
        eligible_formats.sort(key=lambda f: (f.get('height', 0), f.get('tbr', 0) or f.get('vbr', 0) or f.get('abr', 0)), reverse=True)
        best_format = eligible_formats[0]
        best_format_id = best_format.get('format_id')
        filesize_mb = (best_format.get('filesize') or best_format.get('filesize_approx', 0)) / (1024*1024)
        logger.info(f"Selected best format: ID={best_format_id}, Res={best_format.get('resolution', 'N/A')}, Ext={best_format.get('ext')}, Size={filesize_mb:.2f}MB")
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp Error getting video info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting video info: {e}")
        return None

    if best_format_id:
        potential_extensions = ['mp4', 'mkv', 'webm', 'part']
        for ext in potential_extensions:
             fpath = os.path.join(VIDEO_DOWNLOAD_DIR, f"{video_id}.{ext}")
             if os.path.exists(fpath):
                 try:
                     os.remove(fpath)
                     logger.debug(f"Removed existing file: {fpath}")
                 except OSError as e:
                     logger.warning(f"Could not remove existing file {fpath}: {e}")
        
        ydl_opts_download = {
            'format': best_format_id, 'outtmpl': output_template, 'noplaylist': True, 
            'quiet': True, 'no_warnings': True, 'noprogress': True, 'retries': 3, 
            'socket_timeout': 30, 'merge_output_format': 'mp4'
        }
        download_success = False
        def perform_download():
            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                ydl.download([video_url])

        try:
            logger.info(f"Attempting download of format {best_format_id}...")
            start_time = time.time()
            await asyncio.to_thread(perform_download)
            for fname in os.listdir(VIDEO_DOWNLOAD_DIR):
                if fname.startswith(video_id) and not fname.endswith(".part"):
                    final_filename = fname
                    break
            if final_filename:
                 downloaded_file_path = os.path.join(VIDEO_DOWNLOAD_DIR, final_filename)
                 end_time = time.time()
                 filesize_bytes = os.path.getsize(downloaded_file_path)
                 filesize_mb = filesize_bytes / (1024*1024)
                 logger.info(f"Download complete: {final_filename} ({filesize_mb:.2f} MB) in {end_time - start_time:.2f}s")
                 if filesize_bytes > max_bytes:
                      logger.warning(f"Downloaded video size ({filesize_mb:.2f} MB) exceeds limit. Deleting.")
                      os.remove(downloaded_file_path)
                      downloaded_file_path = None 
                 else:
                      download_success = True
            else:
                logger.error("yt-dlp finished, but downloaded file not found.")
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp Download Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during final yt-dlp download: {e}")
        finally:
             if not download_success and downloaded_file_path and os.path.exists(downloaded_file_path):
                 logger.info(f"Cleaning up failed/oversized download: {downloaded_file_path}")
                 try: os.remove(downloaded_file_path)
                 except OSError: pass
                 downloaded_file_path = None
        return downloaded_file_path 
    else:
        logger.error("No best format ID determined for download.")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("--- Running youtube_search.py Tests ---")
    # ... (rest of the test block could be updated but usually it's better to keep it simple)