"""Service for fetching game ratings and metadata from RAWG."""

import logging
import ssl
from typing import Dict, Optional
import aiohttp

from services.eshop.models import RatingInfo

logger = logging.getLogger(__name__)


class RatingService:
    """Fetches ratings, Metacritic scores, and descriptions from RAWG API."""

    RAWG_SEARCH_URL = "https://api.rawg.io/api/games"

    def __init__(self, api_key: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self._session = session
        self._owns_session = False
        self._cache: Dict[str, RatingInfo] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={"User-Agent": "RuTrackerBot-eShopDeals/1.0"},
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close session if managed internally."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def get_game_rating(self, title: str) -> Optional[RatingInfo]:
        """Fetch rating info for a specific game title."""
        if not title:
            return None

        clean_title = title.lower().strip()
        if clean_title in self._cache:
            return self._cache[clean_title]

        if not self.api_key:
            return None

        session = await self._get_session()
        params = {
            "key": self.api_key,
            "search": title,
            "page_size": 1,
            "platforms": "7",  # Nintendo Switch
        }

        try:
            async with session.get(self.RAWG_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json(content_type=None)
                results = data.get("results", [])
                if not results:
                    params.pop("platforms", None)
                    async with session.get(self.RAWG_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as broad_resp:
                        if broad_resp.status == 200:
                            broad_data = await broad_resp.json(content_type=None)
                            results = broad_data.get("results", [])

                if not results:
                    return None

                first_match = results[0]
                metacritic = first_match.get("metacritic")
                rawg_rating = float(first_match.get("rating", 0.0) or 0.0)
                ratings_count = int(first_match.get("ratings_count", 0) or 0)
                genres = [g.get("name") for g in first_match.get("genres", []) if g.get("name")]
                banner = first_match.get("background_image")

                rating_info = RatingInfo(
                    metacritic_score=metacritic,
                    rawg_rating=rawg_rating if rawg_rating > 0 else None,
                    rawg_ratings_count=ratings_count,
                    genres=genres,
                    banner_url=banner,
                )
                self._cache[clean_title] = rating_info
                return rating_info
        except Exception as e:
            logger.debug(f"Error querying RAWG for '{title}': {e}")
            return None
