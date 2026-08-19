"""Service for fetching multi-regional pricing from Nintendo eShop with caching and fallback."""

import asyncio
import json
import logging
import os
import re
import ssl
import time
from typing import Any, Dict, List, Optional
import aiohttp

from services.eshop.models import RegionalPrice
from services.eshop.currency_service import CurrencyService

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join("data", "eshop_region_prices_cache.json")
CACHE_TTL_SECONDS = 12 * 3600  # 12 hours

EUROPE_PAL_REGIONS: Dict[str, str] = {
    "PL": "Poland",
    "ZA": "South Africa",
    "NO": "Norway",
    "GB": "United Kingdom",
    "AU": "Australia",
    "CZ": "Czech Republic",
    "NZ": "New Zealand",
    "SE": "Sweden",
    "CH": "Switzerland",
}

AMERICA_REGIONS: Dict[str, str] = {
    "US": "United States",
    "CA": "Canada",
    "MX": "Mexico",
    "BR": "Brazil",
    "AR": "Argentina",
    "CO": "Colombia",
    "CL": "Chile",
    "PE": "Peru",
}

ASIA_OTHER_REGIONS: Dict[str, str] = {
    "TH": "Thailand",
    "HK": "Hong Kong",
    "JP": "Japan",
}

TRACKED_REGIONS: Dict[str, str] = {**EUROPE_PAL_REGIONS, **AMERICA_REGIONS, **ASIA_OTHER_REGIONS}


def _load_cache() -> Dict[str, Any]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(data: Dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _is_title_match(title1: str, title2: str) -> bool:
    """Check if two game titles match by checking meaningful token sets and containment."""
    if not title1 or not title2:
        return False

    def _get_tokens(s: str) -> set:
        s = re.sub(r"\[.*?\]|\(.*?\)", "", s.lower())
        s = re.sub(r"[^\w\s]", " ", s)
        tokens = set(s.split())
        stop_words = {
            "the", "a", "an", "and", "of", "for", "in", "to", "nintendo", "switch",
            "edition", "deluxe", "bundle", "game", "digital", "hd", "remastered", "remake"
        }
        meaningful = tokens - stop_words
        return meaningful or tokens

    w1 = _get_tokens(title1)
    w2 = _get_tokens(title2)
    if not w1 or not w2:
        return False

    # True if one is exact subset of another (e.g. 'Hogwarts Legacy' in 'Hogwarts Legacy: Digital Deluxe')
    if w1.issubset(w2) or w2.issubset(w1):
        return True

    # Word-level Jaccard index
    return (len(w1 & w2) / len(w1 | w2)) >= 0.65


class RegionPriceService:
    """Fetches real-time localized eShop pricing across global Nintendo regions."""

    # Nintendo eShop Price API (v1)
    PRICE_API_URL = "https://api.ec.nintendo.com/v1/price"

    # Nintendo of America Algolia Search API
    ALGOLIA_US_URL = "https://u3b6gr4ua3-dsn.algolia.net/1/indexes/store_game_en_us/query"
    ALGOLIA_HEADERS = {
        "X-Algolia-API-Key": "9a96da137365c71d6092520cb2a48721",
        "X-Algolia-Application-Id": "U3B6GR4UA3",
        "Content-Type": "application/json",
    }

    def __init__(
        self,
        currency_service: Optional[CurrencyService] = None,
        tracked_regions: Optional[Dict[str, str]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.currency_service = currency_service or CurrencyService()
        self.tracked_regions = tracked_regions or TRACKED_REGIONS
        self._session = session
        self._owns_session = False
        self._cache = _load_cache()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close managed session and persist cache."""
        _save_cache(self._cache)
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def get_us_data_by_title(self, title: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """Query Nintendo of America Algolia index for US details (NSUID, msrp, salePrice)."""
        if not title:
            return None
        clean_title = re.sub(r"\[.*?\]|\(.*?\)", "", title).strip()
        try:
            payload = {"query": clean_title, "hitsPerPage": 5}
            async with session.post(
                self.ALGOLIA_US_URL,
                json=payload,
                headers=self.ALGOLIA_HEADERS,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hits = data.get("hits", [])
                    for hit in hits:
                        hit_title = hit.get("title", "")
                        if _is_title_match(clean_title, hit_title):
                            return hit
        except Exception as e:
            logger.debug(f"Could not query Algolia for '{title}': {e}")
        return None

    async def get_us_nsuid_by_title(self, title: str, session: aiohttp.ClientSession) -> Optional[str]:
        """Query Nintendo of America Algolia index to resolve US NSUID for the title."""
        hit = await self.get_us_data_by_title(title, session)
        if hit and hit.get("nsuid"):
            return str(hit["nsuid"])
        return None

    async def fetch_region_price(
        self, session: aiohttp.ClientSession, country_code: str, country_name: str, nsuid: str
    ) -> Optional[RegionalPrice]:
        """Fetch price for a single country code and NSUID."""
        params = {
            "country": country_code,
            "lang": "en",
            "ids": nsuid,
        }

        try:
            async with session.get(self.PRICE_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json(content_type=None)
                prices = data.get("prices", [])
                if not prices:
                    return None

                item = prices[0]
                disc_obj = item.get("discount_price")
                reg_obj = item.get("regular_price")

                curr_obj = disc_obj or reg_obj
                if not curr_obj:
                    return None

                currency = curr_obj.get("currency", "")
                raw_val = curr_obj.get("raw_value")
                if not raw_val or not currency:
                    return None

                effective_price = float(raw_val)
                regular_price = float(reg_obj.get("raw_value", effective_price)) if reg_obj else effective_price
                is_discount = disc_obj is not None

                discount_pct = 0.0
                if is_discount and regular_price > 0 and effective_price < regular_price:
                    discount_pct = round(((regular_price - effective_price) / regular_price) * 100, 1)

                converted_usd = self.currency_service.convert_to_usd(effective_price, currency)
                converted_uah = self.currency_service.convert_to_uah(effective_price, currency)

                return RegionalPrice(
                    country_code=country_code,
                    country_name=country_name,
                    currency=currency,
                    regular_price=regular_price,
                    discount_price=effective_price,
                    discount_percent=discount_pct,
                    converted_usd=converted_usd,
                    converted_uah=converted_uah,
                    is_discount=is_discount,
                )
        except Exception as e:
            logger.debug(f"Failed to fetch price for {country_code}: {e}")
            return None

    async def get_regional_prices_for_game(
        self, nsuid: str, game_title: Optional[str] = None
    ) -> List[RegionalPrice]:
        """Fetch prices across all tracked regions, using cache, rate-limiting, and Algolia fallback."""
        if not nsuid and not game_title:
            return []

        # 1. Check in-memory / JSON cache
        cache_key = f"{nsuid}_{game_title or ''}".strip("_")
        now_ts = time.time()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if (now_ts - entry.get("timestamp", 0)) < CACHE_TTL_SECONDS:
                cached_list = []
                for p_dict in entry.get("prices", []):
                    try:
                        cached_list.append(RegionalPrice(**p_dict))
                    except Exception:
                        pass
                if cached_list:
                    return cached_list

        session = await self._get_session()
        sem = asyncio.Semaphore(4)

        async def _fetch_with_sem(cc: str, cname: str, nid: str) -> Optional[RegionalPrice]:
            async with sem:
                await asyncio.sleep(0.02)
                return await self.fetch_region_price(session, cc, cname, nid)

        tasks = []

        # 2. European / PAL regions using primary European NSUID
        if nsuid:
            for code, name in EUROPE_PAL_REGIONS.items():
                tasks.append(_fetch_with_sem(code, name, nsuid))

        # 3. Americas regions using resolved US NSUID / Algolia
        us_data = None
        us_nsuid = None
        if game_title:
            us_data = await self.get_us_data_by_title(game_title, session)
            if us_data and us_data.get("nsuid"):
                us_nsuid = str(us_data["nsuid"])

        if us_nsuid:
            for code, name in AMERICA_REGIONS.items():
                tasks.append(_fetch_with_sem(code, name, us_nsuid))
        elif nsuid:
            for code, name in AMERICA_REGIONS.items():
                tasks.append(_fetch_with_sem(code, name, nsuid))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_prices = [r for r in results if isinstance(r, RegionalPrice)]

        # 4. Fallback: If US is not in valid_prices but Algolia returned US pricing
        has_us = any(p.country_code == "US" for p in valid_prices)
        if not has_us and us_data:
            sale_price = us_data.get("salePrice")
            msrp = us_data.get("msrp") or us_data.get("lowestPrice")
            if msrp is not None or sale_price is not None:
                reg_p = float(msrp) if msrp is not None else float(sale_price)
                eff_p = float(sale_price) if sale_price is not None else reg_p
                is_disc = sale_price is not None and sale_price < reg_p
                disc_pct = round(((reg_p - eff_p) / reg_p) * 100, 1) if (is_disc and reg_p > 0) else 0.0
                valid_prices.append(
                    RegionalPrice(
                        country_code="US",
                        country_name="United States",
                        currency="USD",
                        regular_price=reg_p,
                        discount_price=eff_p,
                        discount_percent=disc_pct,
                        converted_usd=eff_p,
                        converted_uah=self.currency_service.convert_to_uah(eff_p, "USD"),
                        is_discount=is_disc,
                    )
                )

        # 5. Store in cache if we obtained prices
        if valid_prices:
            self._cache[cache_key] = {
                "timestamp": now_ts,
                "prices": [
                    {
                        "country_code": p.country_code,
                        "country_name": p.country_name,
                        "currency": p.currency,
                        "regular_price": p.regular_price,
                        "discount_price": p.discount_price,
                        "discount_percent": p.discount_percent,
                        "converted_usd": p.converted_usd,
                        "converted_uah": p.converted_uah,
                        "is_discount": p.is_discount,
                    }
                    for p in valid_prices
                ],
            }
            _save_cache(self._cache)

        return valid_prices
