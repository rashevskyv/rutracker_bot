"""Service for fetching multi-regional pricing from Nintendo eShop."""

import asyncio
import logging
import ssl
from typing import Dict, List, Optional
import aiohttp

from services.eshop.models import RegionalPrice
from services.eshop.currency_service import CurrencyService

logger = logging.getLogger(__name__)

TRACKED_REGIONS: Dict[str, str] = {
    "PL": "Poland",
    "US": "United States",
    "ZA": "South Africa",
    "JP": "Japan",
    "NO": "Norway",
    "GB": "United Kingdom",
    "AU": "Australia",
    "CZ": "Czech Republic",
    "BR": "Brazil",
    "MX": "Mexico",
    "CA": "Canada",
    "NZ": "New Zealand",
}


class RegionPriceService:
    """Queries Nintendo eShop Price API across multiple regions."""

    PRICE_API_URL = "https://api.ec.nintendo.com/v1/price"

    def __init__(
        self,
        currency_service: CurrencyService,
        session: Optional[aiohttp.ClientSession] = None,
        tracked_regions: Optional[Dict[str, str]] = None,
    ):
        self.currency_service = currency_service
        self.tracked_regions = tracked_regions or TRACKED_REGIONS
        self._session = session
        self._owns_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close managed session."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def fetch_region_price(
        self, session: aiohttp.ClientSession, country_code: str, country_name: str, nsuid: str
    ) -> Optional[RegionalPrice]:
        """Fetch price for a single country code."""
        params = {
            "country": country_code,
            "lang": "en",
            "ids": nsuid,
        }

        try:
            async with session.get(self.PRICE_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=6)) as resp:
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

                return RegionalPrice(
                    country_code=country_code,
                    country_name=country_name,
                    currency=currency,
                    regular_price=regular_price,
                    discount_price=effective_price,
                    discount_percent=discount_pct,
                    converted_usd=converted_usd,
                    is_discount=is_discount,
                )
        except Exception as e:
            logger.debug(f"Failed to fetch price for {country_code}: {e}")
            return None

    async def get_regional_prices_for_game(self, nsuid: str) -> List[RegionalPrice]:
        """Fetch prices for an NSUID across all tracked regions concurrently."""
        if not nsuid:
            return []

        session = await self._get_session()
        tasks = [
            self.fetch_region_price(session, code, name, nsuid)
            for code, name in self.tracked_regions.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_prices = [r for r in results if isinstance(r, RegionalPrice)]
        return valid_prices
