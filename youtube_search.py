import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from settings_loader import LOG # Use the refactored settings module
from typing import Optional, Tuple # Import Optional, Tuple

def search_trailer_on_youtube(game_title: str, api_key: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Searches for a game trailer on YouTube using the provided API key.

    Args:
        game_title: The title of the game.
        api_key: The YouTube Data API v3 key.

    Returns:
        A tuple containing:
            - The URL of the found trailer video (Optional[str]).
            - The title of the found video (Optional[str]).
    """
    if not api_key: return None, None # Skip if no key

    # Clean title (basic cleaning)
    cleaned_game_title = re.sub(r'\[.*?\]', '', game_title).strip()
    cleaned_game_title = re.sub(r'\b(Deluxe|Ultimate|Gold|Standard|Complete|GOTY|Edition)\b', '', cleaned_game_title, flags=re.IGNORECASE).strip()
    cleaned_game_title = re.sub(r'[^\w\s\-\:]+$', '', cleaned_game_title).strip()
    if not cleaned_game_title: return None, None # Skip if title becomes empty

    search_queries = [ # Queries from specific to general
        f'"{cleaned_game_title}" Nintendo Switch Official Trailer',
        f"{cleaned_game_title} Nintendo Switch Trailer",
        f"{cleaned_game_title} Switch Gameplay Trailer",
        f"{cleaned_game_title} Official Trailer",
        f"{cleaned_game_title} Gameplay",
    ]
    if '/' in cleaned_game_title: # Handle titles with '/'
        base_title = cleaned_game_title.split('/', 1)[0].strip()
        if base_title != cleaned_game_title: search_queries.insert(1, f'"{base_title}" Nintendo Switch Gameplay')

    if LOG: print(f"Cleaned game title for YouTube search: '{cleaned_game_title}'")

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        for query in search_queries:
            try:
                search_response = youtube.search().list(
                    q=query, part="id,snippet", type="video", order="relevance",
                    maxResults=1, relevanceLanguage="en", videoDefinition="high",
                ).execute()
                items = search_response.get("items", [])
                if items: # Found a result for this query
                    video = items[0]; video_id = video["id"]["videoId"]; video_title = video["snippet"]["title"]
                    trailer_url = f"https://www.youtube.com/watch?v={video_id}"
                    print(f"Found video: '{video_title}' - URL: {trailer_url} (Query: '{query}')")
                    return trailer_url, video_title # Return first relevant result found
            except HttpError as e: # Correctly handle HttpError
                 print(f"YT HTTP error (Query: '{query}'): {e}")
                 # Check status code within the except block
                 if hasattr(e, 'resp') and e.resp.status == 403:
                      print("Quota likely exceeded or API key issue.")
                      # Decide if we should stop searching or just continue
                      # return None, None # Uncomment to stop on quota error
            except Exception as e:
                 print(f"YT unexpected error (Query: '{query}'): {e}")
        # If loop finishes without returning, no results found
        return None, None
    except Exception as e:
         print(f"Failed to build YouTube API service: {e}")
         return None, None
