"""Landscape covers (920x430 grids) from SteamGridDB, by exact game name."""
import logging
import re
from typing import List, Optional
from urllib.parse import quote

from core.settings_loader import get_session

logger = logging.getLogger(__name__)

API = "https://www.steamgriddb.com/api/v2"


def normalize_name(name: str) -> str:
    """As normalizeName() in github.com/iArtem88/rutracker-games."""
    name = re.sub(r"[’'`]", "", name.lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name).split())


def candidate_names(title: str) -> List[str]:
    """'BANG! BANG! BANDITS バン！… [Nintendo Switch 2] (порт)' -> ['BANG! BANG! BANDITS']."""
    title = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)
    # Latin only: Japanese and Russian alternative names are never on SteamGridDB as such
    title = "".join(c for c in title if ord(c) < 0x250)
    names = []
    for name in [title] + re.split(r"\s+(?:/|—|–|-)\s+", title):
        name = " ".join(name.split()).strip(" /—–-:")
        if normalize_name(name) and name not in names:
            names.append(name)
    return names


async def _api(path: str, api_key: str) -> list:
    async with get_session().get(f"{API}{path}", headers={"Authorization": f"Bearer {api_key}"}, timeout=15) as response:
        response.raise_for_status()
        return (await response.json()).get("data") or []


async def find_landscape_cover(title: str, api_key: Optional[str]) -> Optional[str]:
    """URL of a 920x430 (or 460x215) static grid of the game named exactly as the release, or None."""
    if not api_key:
        return None
    try:
        for name in candidate_names(title):
            wanted = normalize_name(name)
            for game in await _api(f"/search/autocomplete/{quote(name, safe='')}", api_key):
                # Exact names only: a near match is another game. Some games have duplicates without grids
                if normalize_name(game.get("name", "")) != wanted:
                    continue
                grids = await _api(f"/grids/game/{game['id']}?dimensions=920x430,460x215&types=static&nsfw=false&humor=false", api_key)
                if grids:
                    logger.info(f"SteamGridDB cover: '{game['name']}' ({game['id']}) {grids[0]['url']}")
                    return grids[0]["url"]
    except Exception as e:
        logger.warning(f"SteamGridDB lookup failed for '{title}': {e}")
    return None
