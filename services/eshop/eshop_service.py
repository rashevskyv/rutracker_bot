"""Service for querying Nintendo eShop catalog and active deals."""

import logging
import ssl
from typing import Any, Dict, List, Optional
import aiohttp

from services.eshop.models import GameDeal

logger = logging.getLogger(__name__)


class EShopService:
    """Handles communications with Nintendo Store / Search APIs."""

    BASE_URL = "https://searching.nintendo-europe.com/{locale}/select"
    NINTENDO_BASE_WEB_URL = "https://www.nintendo.com"

    def __init__(self, locale: str = "en", session: Optional[aiohttp.ClientSession] = None):
        self.locale = locale
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
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the underlying session if managed by this service."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    def _parse_game_doc(self, doc: Dict[str, Any]) -> Optional[GameDeal]:
        """Convert a raw Nintendo Search API doc into a GameDeal instance."""
        try:
            fs_id = str(doc.get("fs_id", ""))
            title = doc.get("title") or doc.get("title_master_s")
            if not fs_id or not title:
                return None

            reg_price = float(doc.get("price_regular_f", 0.0) or doc.get("price_lowest_f", 0.0) or 0.0)
            raw_disc_price = doc.get("price_discounted_f")

            has_discount_flag = bool(doc.get("price_has_discount_b", False))
            has_lower_price = (
                raw_disc_price is not None
                and float(raw_disc_price or 0.0) > 0
                and (reg_price == 0 or float(raw_disc_price) < reg_price)
            )

            if has_discount_flag or has_lower_price:
                disc_price = float(raw_disc_price if raw_disc_price is not None else reg_price)
                disc_pct = float(doc.get("price_discount_percentage_f", 0.0) or 0.0)
                if disc_pct == 0.0 and reg_price > 0 and disc_price < reg_price:
                    disc_pct = round(((reg_price - disc_price) / reg_price) * 100, 1)
            else:
                disc_price = reg_price
                disc_pct = 0.0

            nsuid_list = doc.get("nsuid_txt") or doc.get("related_nsuids_txt") or []
            nsuid = nsuid_list[0] if isinstance(nsuid_list, list) and nsuid_list else None

            game_path = doc.get("url", "")
            full_url = f"{self.NINTENDO_BASE_WEB_URL}{game_path}" if game_path.startswith("/") else game_path

            image_url = (
                doc.get("image_url_sq_s")
                or doc.get("image_url")
                or doc.get("wishlist_email_square_image_url_s")
            )
            banner_url = (
                doc.get("wishlist_email_banner640w_image_url_s")
                or doc.get("image_url_h2x1_s")
                or doc.get("wishlist_email_banner460w_image_url_s")
            )

            excerpt = doc.get("excerpt") or doc.get("product_catalog_description_s") or ""
            categories = doc.get("pretty_game_categories_txt") or doc.get("game_categories_txt") or []
            publishers = [doc.get("publisher")] if doc.get("publisher") else []
            system_names = doc.get("system_names_txt") or ["Nintendo Switch"]

            downloads_rank = doc.get("downloads_rank_i")
            hits = doc.get("hits_i")

            return GameDeal(
                fs_id=fs_id,
                title=title,
                regular_price=reg_price,
                discount_price=disc_price,
                discount_percent=disc_pct,
                nsuid=nsuid,
                url=full_url,
                image_url=image_url,
                banner_url=banner_url,
                excerpt=excerpt.strip() if excerpt else None,
                categories=categories,
                publishers=publishers,
                release_date=doc.get("pretty_date_s"),
                downloads_rank=downloads_rank,
                hits=hits,
                system_names=system_names,
            )
        except Exception as e:
            logger.debug(f"Failed to parse game doc: {e}")
            return None

    async def fetch_discounted_games(
        self,
        rows: int = 50,
        sort: str = "popularity desc",
        min_discount_percent: float = 0.0,
    ) -> List[GameDeal]:
        """Fetch Switch games currently on sale from the Nintendo Store."""
        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)

        fq = "type:GAME AND system_type:nintendoswitch* AND price_has_discount_b:true"
        if min_discount_percent > 0:
            fq += f" AND price_discount_percentage_f:[{min_discount_percent} TO 100]"

        params = {
            "q": "*",
            "fq": fq,
            "sort": sort,
            "rows": rows,
            "wt": "json",
        }

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"Nintendo API returned status {resp.status}")
                    return []
                data = await resp.json(content_type=None)
                docs = data.get("response", {}).get("docs", [])
                deals = []
                for doc in docs:
                    deal = self._parse_game_doc(doc)
                    if deal and (min_discount_percent == 0 or deal.discount_percent >= min_discount_percent):
                        deals.append(deal)
                return deals
        except Exception as e:
            logger.error(f"Error fetching discounted games from Nintendo API: {e}")
            return []

    async def search_games(self, query: str, rows: int = 10) -> List[GameDeal]:
        """Search specifically for Nintendo Switch games by name/keyword."""
        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)

        clean_q = query.strip()
        formatted_q = f"*{clean_q}*" if not clean_q.startswith("*") else clean_q

        params = {
            "q": formatted_q,
            "fq": "type:GAME AND system_type:nintendoswitch*",
            "sort": "popularity desc",
            "rows": rows,
            "wt": "json",
        }

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"Nintendo Search API error: {resp.status}")
                    return []
                data = await resp.json(content_type=None)
                docs = data.get("response", {}).get("docs", [])
                results = []
                for doc in docs:
                    deal = self._parse_game_doc(doc)
                    if deal:
                        results.append(deal)
                return results
        except Exception as e:
            logger.error(f"Error searching games with query '{query}': {e}")
            return []
