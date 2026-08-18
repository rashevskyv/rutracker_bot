"""Currency and exchange rate management service for eShop prices."""

import logging
import ssl
from datetime import datetime, timezone
from typing import Dict, Optional
import aiohttp

logger = logging.getLogger(__name__)

FALLBACK_USD_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "PLN": 3.95,
    "GBP": 0.78,
    "ZAR": 18.20,
    "JPY": 155.0,
    "NOK": 10.60,
    "AUD": 1.52,
    "CAD": 1.36,
    "CZK": 23.10,
    "BRL": 5.40,
    "MXN": 18.10,
    "CHF": 0.89,
    "NZD": 1.65,
    "SEK": 10.40,
}


class CurrencyService:
    """Provides currency conversion and real-time exchange rates."""

    RATES_API_URL = "https://open.er-api.com/v6/latest/USD"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = False
        self._rates: Dict[str, float] = FALLBACK_USD_RATES.copy()
        self._last_updated: Optional[datetime] = None

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
        """Close managed session."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def refresh_rates(self) -> None:
        """Fetch latest exchange rates."""
        try:
            session = await self._get_session()
            async with session.get(self.RATES_API_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = data.get("rates", {})
                    if rates:
                        self._rates.update(rates)
                        self._last_updated = datetime.now(timezone.utc)
                        logger.debug(f"Updated {len(rates)} currency exchange rates.")
        except Exception as e:
            logger.debug(f"Failed to refresh currency exchange rates: {e}, using fallback.")

    def convert_to_usd(self, amount: float, from_currency: str) -> float:
        """Convert an amount from a given currency to USD."""
        if not amount or from_currency.upper() == "USD":
            return round(amount, 2)

        rate = self._rates.get(from_currency.upper())
        if not rate or rate <= 0:
            return round(amount, 2)

        return round(amount / rate, 2)
