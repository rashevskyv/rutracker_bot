# --- START OF FILE youtube_search.py ---
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
from typing import Optional, Tuple, List
import asyncio

logger = logging.getLogger(__name__)

# Module-level cache for YouTube API client (build() is expensive — HTTP to discovery endpoint)
_youtube_client = None
_youtube_api_key_used = None


async def _get_youtube_client(api_key: str):
    """Lazily initialize and cache the YouTube API client."""
    global _youtube_client, _youtube_api_key_used
    if _youtube_client is None or _youtube_api_key_used != api_key:
        _youtube_client = await asyncio.to_thread(build, "youtube", "v3", developerKey=api_key)
        _youtube_api_key_used = api_key
        logger.info("YouTube API client initialized and cached.")
    return _youtube_client


async def search_trailer_on_youtube(
    game_title: str, api_key: Optional[str]
) -> List[Tuple[Optional[str], Optional[str]]]:
    """
    Search YouTube for trailers matching the given game title.
    Returns up to 3 unique (url, title) candidates across all search queries,
    for the caller to validate and pick the best match.
    """
    if not api_key:
        return []

    cleaned_game_title = re.sub(r'\[.*?\]', '', game_title).strip()
    cleaned_game_title = re.sub(
        r'\b(Deluxe|Ultimate|Gold|Standard|Complete|GOTY|Edition)\b', '',
        cleaned_game_title, flags=re.IGNORECASE
    ).strip()
    cleaned_game_title = re.sub(r'[^\w\s\-\:]+$', '', cleaned_game_title).strip()

    if not cleaned_game_title:
        return []

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

    candidates: List[Tuple[str, str]] = []
    seen_ids: set = set()

    try:
        youtube = await _get_youtube_client(api_key)
        for query in search_queries:
            if len(candidates) >= 3:
                break
            try:
                list_call = youtube.search().list(
                    q=query,
                    part="id,snippet",
                    type="video",
                    order="relevance",
                    maxResults=3,
                    relevanceLanguage="en",
                    videoDefinition="high"
                )
                search_response = await asyncio.to_thread(list_call.execute)
                items = search_response.get("items", [])
                for item in items:
                    if len(candidates) >= 3:
                        break
                    video_id = item["id"]["videoId"]
                    if video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)
                    video_title = item["snippet"]["title"]
                    trailer_url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info(f"Candidate: '{video_title}' — {trailer_url} (Query: '{query}')")
                    candidates.append((trailer_url, video_title))

            except HttpError as e:
                logger.error(f"YT HTTP error (Query: '{query}'): {e}")
                if hasattr(e, 'resp') and e.resp.status == 403:
                    logger.error("YouTube quota likely exceeded.")
                    break
            except Exception as e:
                logger.error(f"YT unexpected error (Query: '{query}'): {e}")

        return candidates

    except Exception as e:
        logger.error(f"Failed to build YouTube API service: {e}")
        return []

# --- END OF FILE youtube_search.py ---
