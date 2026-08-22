"""Service for querying Nintendo eShop catalog and active deals."""

import asyncio
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
                or doc.get("pack_art_image_url_s")
                or doc.get("wishlist_email_square_image_url_s")
            )
            banner_url = (
                doc.get("image_url_h2x1_s")
                or doc.get("image_url_h16x9_s")
                or doc.get("horizontal_cover_image_url_s")
                or doc.get("wishlist_email_banner640w_image_url_s")
                or doc.get("wishlist_email_banner460w_image_url_s")
                or image_url
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
        start: int = 0,
        sort: str = "popularity desc",
        min_discount_percent: float = 0.0,
        min_price_eur: Optional[float] = None,
        max_price_eur: Optional[float] = None,
        min_rank: Optional[int] = None,
        max_rank: Optional[int] = None,
    ) -> List[GameDeal]:
        """Fetch Switch games currently on sale from the Nintendo Store."""
        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)

        fq = "type:GAME AND system_type:nintendoswitch* AND price_has_discount_b:true"
        if min_discount_percent > 0:
            fq += f" AND price_discount_percentage_f:[{min_discount_percent} TO 100]"
        if min_price_eur is not None and max_price_eur is not None:
            fq += f" AND price_discounted_f:[{max(0.0, min_price_eur):.2f} TO {max_price_eur:.2f}]"
        elif min_price_eur is not None:
            fq += f" AND price_discounted_f:[{max(0.0, min_price_eur):.2f} TO *]"
        elif max_price_eur is not None:
            fq += f" AND price_discounted_f:[* TO {max_price_eur:.2f}]"

        if min_rank is not None and max_rank is not None:
            fq += f" AND downloads_rank_i:[{min_rank} TO {max_rank}]"
        elif min_rank is not None:
            fq += f" AND downloads_rank_i:[{min_rank} TO *]"
        elif max_rank is not None:
            fq += f" AND downloads_rank_i:[* TO {max_rank}]"

        params = {
            "q": "*",
            "fq": fq,
            "sort": sort,
            "start": max(0, start),
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
                return await self.validate_live_prices(deals, require_discount=True)
        except Exception as e:
            logger.error(f"Error fetching discounted games from Nintendo API: {e}")
            return []

    async def fetch_popular_discounted_games(
        self, min_discount_percent: float = 0.0, concurrency: int = 15
    ) -> List[GameDeal]:
        """
        Check discounts specifically across the curated catalog of famous/popular Switch games
        and major publisher releases, eliminating shovelware and verifying with live Price API.
        """
        from services.eshop.popular_catalog import POPULAR_SWITCH_GAMES, MAJOR_PUBLISHERS

        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)
        semaphore = asyncio.Semaphore(concurrency)

        async def _check_title(title: str) -> Optional[GameDeal]:
            params = {
                "q": f'"{title}"',
                "rows": 1,
                "fq": "type:GAME AND system_type:nintendoswitch*",
                "wt": "json",
            }
            async with semaphore:
                try:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            docs = data.get("response", {}).get("docs", [])
                            if docs:
                                doc = docs[0]
                                if doc.get("price_has_discount_b", False):
                                    deal = self._parse_game_doc(doc)
                                    if deal and (min_discount_percent == 0 or deal.discount_percent >= min_discount_percent):
                                        return deal
                except Exception as err:
                    logger.debug(f"Error checking popular title '{title}': {err}")
            return None

        # 1. Query curated top games list
        tasks = [_check_title(t) for t in POPULAR_SWITCH_GAMES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        deals: List[GameDeal] = [r for r in results if isinstance(r, GameDeal)]

        # 2. Also fetch top publisher discounted games (regular price >= 14.99)
        try:
            pub_query = " OR ".join([f'publisher:"{p}"' for p in MAJOR_PUBLISHERS[:12]])
            fq = f"type:GAME AND system_type:nintendoswitch* AND price_has_discount_b:true AND price_regular_f:[14.99 TO 100] AND ({pub_query})"
            if min_discount_percent > 0:
                fq += f" AND price_discount_percentage_f:[{min_discount_percent} TO 100]"
            params = {
                "q": "*",
                "fq": fq,
                "sort": "popularity desc",
                "rows": 30,
                "wt": "json",
            }
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    for doc in data.get("response", {}).get("docs", []):
                        deal = self._parse_game_doc(doc)
                        if deal:
                            deals.append(deal)
        except Exception as e:
            logger.debug(f"Error fetching publisher deals: {e}")

        # Deduplicate by fs_id / title
        seen = set()
        unique_deals = []
        for d in deals:
            key = d.fs_id or d.title.lower()
            if key not in seen:
                seen.add(key)
                unique_deals.append(d)

        # Strictly validate all deals against live Nintendo Price API to eliminate ghost/expired discounts
        return await self.validate_live_prices(unique_deals, require_discount=True)

    async def validate_live_prices(
        self, deals: List[GameDeal], country: str = "DE", require_discount: bool = True
    ) -> List[GameDeal]:
        """
        Validate candidate deals against Nintendo's official real-time Price API (https://api.ec.nintendo.com/v1/price).
        Solr catalog index can retain stale discount flags for expired sales. Real-time Price API is the ground truth.
        """
        if not deals:
            return []

        session = await self._get_session()
        validated: List[GameDeal] = []

        chunk_size = 50
        for i in range(0, len(deals), chunk_size):
            chunk = deals[i : i + chunk_size]
            nsuid_map = {str(d.nsuid): d for d in chunk if d.nsuid}
            if not nsuid_map:
                if not require_discount:
                    validated.extend(chunk)
                continue

            ids_param = ",".join(nsuid_map.keys())
            url = f"https://api.ec.nintendo.com/v1/price?country={country}&lang=en&ids={ids_param}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        for price_obj in data.get("prices", []):
                            t_id = str(price_obj.get("title_id"))
                            deal = nsuid_map.get(t_id)
                            if not deal:
                                continue

                            reg_info = price_obj.get("regular_price") or {}
                            disc_info = price_obj.get("discount_price")

                            reg_raw = reg_info.get("raw_value")
                            disc_raw = disc_info.get("raw_value") if disc_info else None

                            if reg_raw is not None:
                                try:
                                    deal.regular_price = float(reg_raw)
                                except ValueError:
                                    pass

                            if disc_raw is not None:
                                try:
                                    deal.discount_price = float(disc_raw)
                                    if deal.regular_price and deal.regular_price > 0:
                                        deal.discount_percent = round(
                                            ((deal.regular_price - deal.discount_price) / deal.regular_price) * 100,
                                            1,
                                        )
                                    validated.append(deal)
                                except ValueError:
                                    pass
                            elif not require_discount:
                                deal.discount_price = deal.regular_price
                                deal.discount_percent = 0.0
                                validated.append(deal)
                            else:
                                logger.debug(
                                    f"Rejecting ghost discount for '{deal.title}': Solr had discount, but live Price API shows regular price ({deal.regular_price} EUR)."
                                )
                    else:
                        if not require_discount:
                            validated.extend(chunk)
            except Exception as e:
                logger.debug(f"Live Price API validation error: {e}")
                if not require_discount:
                    validated.extend(chunk)

        return validated

    async def search_games(self, query: str, rows: int = 10) -> List[GameDeal]:
        """Search specifically for Nintendo Switch games by name/keyword."""
        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)

        clean_q = query.strip()
        if " " in clean_q:
            formatted_q = clean_q
        else:
            formatted_q = f"*{clean_q}*" if not clean_q.startswith("*") else clean_q

        params = {
            "q": formatted_q,
            "q.op": "AND",
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
                return await self.validate_live_prices(results, require_discount=False)
        except Exception as e:
            logger.error(f"Error searching games with query '{query}': {e}")
            return []

    async def get_game_by_fs_id(self, fs_id: str) -> Optional[GameDeal]:
        """Fetch game details directly by its unique Nintendo fs_id."""
        if not fs_id:
            return None
        session = await self._get_session()
        url = self.BASE_URL.format(locale=self.locale)
        params = {
            "q": "*",
            "fq": f"type:GAME AND fs_id:{fs_id}",
            "rows": 1,
            "wt": "json",
        }
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    docs = data.get("response", {}).get("docs", [])
                    if docs:
                        deal = self._parse_game_doc(docs[0])
                        if deal:
                            validated = await self.validate_live_prices([deal], require_discount=False)
                            return validated[0] if validated else deal
        except Exception as e:
            logger.debug(f"Error fetching game by fs_id '{fs_id}': {e}")
        return None

