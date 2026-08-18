import os
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from services.eshop.models import GameDeal, QualityCriteria
from services.eshop.eshop_service import EShopService
from services.eshop.rating_service import RatingService
from services.eshop.region_price_service import RegionPriceService

logger = logging.getLogger(__name__)

DESCRIPTIONS_CACHE_FILE = os.path.join("data", "eshop_descriptions.json")


def _load_descriptions_cache() -> dict:
    if os.path.exists(DESCRIPTIONS_CACHE_FILE):
        try:
            with open(DESCRIPTIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_descriptions_cache(data: dict) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(DESCRIPTIONS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class DealFilterEngine:
    """Coordinates fetching, rating enrichment, regional pricing, and quality filtering."""

    def __init__(
        self,
        eshop_service: EShopService,
        rating_service: RatingService,
        region_price_service: Optional[RegionPriceService] = None,
    ):
        self.eshop = eshop_service
        self.ratings = rating_service
        self.region_prices = region_price_service

    async def enrich_deal(self, deal: GameDeal, fetch_regions: bool = True) -> GameDeal:
        """Enrich a single deal with ratings, regional prices, and Ukrainian description."""
        if self.ratings.api_key:
            info = await self.ratings.get_game_rating(deal.title)
            if info:
                deal.metacritic_score = info.metacritic_score
                deal.rawg_rating = info.rawg_rating
                deal.rawg_ratings_count = info.rawg_ratings_count
                if info.banner_url and not deal.banner_url:
                    deal.banner_url = info.banner_url
                if info.genres:
                    for g in info.genres:
                        if g not in deal.categories:
                            deal.categories.append(g)

        if fetch_regions and self.region_prices and (deal.nsuid or deal.title):
            prices = await self.region_prices.get_regional_prices_for_game(deal.nsuid or "", game_title=deal.title)
            if prices:
                deal.regional_prices = prices

        # Translate game description to Ukrainian if present
        if deal.excerpt and deal.excerpt.strip():
            try:
                from services.translation import translate_eshop_synopsis
                deal.excerpt = await translate_eshop_synopsis(
                    title=deal.title, synopsis=deal.excerpt, fs_id=deal.fs_id
                )
            except Exception as e:
                logger.debug(f"Failed to translate excerpt for {deal.title}: {e}")

        return deal

    async def enrich_batch(
        self, deals: List[GameDeal], fetch_regions: bool = True, concurrency: int = 5
    ) -> List[GameDeal]:
        """Enrich multiple deals concurrently with rate-limiting semaphore."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _enrich_with_sem(deal: GameDeal) -> GameDeal:
            async with semaphore:
                return await self.enrich_deal(deal, fetch_regions=fetch_regions)

        return await asyncio.gather(*[_enrich_with_sem(d) for d in deals])

    def calculate_deal_score(self, deal: GameDeal) -> float:
        """
        Calculate an overall deal quality score.
        Higher score = better game + better discount.
        """
        rating_score = 50.0
        if deal.metacritic_score is not None:
            rating_score = float(deal.metacritic_score)
        elif deal.rawg_rating is not None and deal.rawg_rating > 0:
            rating_score = deal.rawg_rating * 20.0

        popularity_bonus = 0.0
        if deal.downloads_rank and deal.downloads_rank < 5000:
            popularity_bonus = max(0.0, (5000 - deal.downloads_rank) / 500.0)

        discount_score = deal.discount_percent * 0.5
        return rating_score + discount_score + popularity_bonus

    async def get_best_deals(
        self,
        criteria: QualityCriteria,
        limit: int = 10,
        fetch_rows: int = 40,
        include_regional_prices: bool = True,
    ) -> List[GameDeal]:
        """
        Fetch deals, enrich with ratings, filter by quality criteria,
        sort by overall score, and attach regional price comparisons.
        """
        # 1. Fetch genuine popular hits and major publisher releases on sale
        deals = await self.eshop.fetch_popular_discounted_games(
            min_discount_percent=criteria.min_discount_percent
        )

        # Fallback if catalog check was empty
        if not deals:
            deals = await self.eshop.fetch_discounted_games(
                rows=fetch_rows,
                sort="popularity desc",
                min_discount_percent=criteria.min_discount_percent,
            )

        if not deals:
            return []

        if self.ratings.api_key:
            deals = await self.enrich_batch(deals, fetch_regions=False)

        qualified_deals = [d for d in deals if d.matches_criteria(criteria)]
        qualified_deals.sort(key=self.calculate_deal_score, reverse=True)

        top_deals = qualified_deals[:limit]

        if include_regional_prices and self.region_prices:
            if hasattr(self.region_prices, "currency_service") and self.region_prices.currency_service:
                await self.region_prices.currency_service.refresh_rates()
            top_deals = await self.enrich_batch(top_deals, fetch_regions=True)

        return top_deals

    async def get_candidate_deals(
        self, criteria: QualityCriteria, limit: int = 10
    ) -> List[GameDeal]:
        """Fetch and preliminarily rank candidate popular discounted games quickly without full enrichment."""
        deals = await self.eshop.fetch_popular_discounted_games(
            min_discount_percent=criteria.min_discount_percent
        )
        if not deals:
            deals = await self.eshop.fetch_discounted_games(
                rows=30, sort="popularity desc", min_discount_percent=criteria.min_discount_percent
            )
        if not deals:
            return []

        qualified = [d for d in deals if d.discount_percent >= criteria.min_discount_percent]
        qualified.sort(key=lambda d: (d.discount_percent, d.regular_price), reverse=True)
        return qualified[:limit]

    async def get_flexible_deals(
        self,
        limit: int = 5,
        rank_range: Optional[tuple] = None,
        price_range_uah: Optional[tuple] = None,
        sort_by: str = "popularity",
        is_random: bool = False,
        criteria: Optional[QualityCriteria] = None,
        currency_service: Optional[Any] = None,
    ) -> List[GameDeal]:
        """
        Fetch discounted games with flexible rank ranges, price limits, sorting orders, or random sampling.
        """
        import random
        min_disc = criteria.min_discount_percent if criteria else 0.0

        # 1. Determine Solr start & rows
        if rank_range:
            start_rank, end_rank = rank_range
            start = max(0, start_rank - 1)
            rows = max(10, min(150, end_rank - start_rank + 1))
        else:
            start = 0
            rows = max(35, limit * 5)

        # 2. Determine Solr sort
        solr_sort_map = {
            "price_asc": "price_discounted_f asc",
            "price_desc": "price_discounted_f desc",
            "discount": "price_discount_percentage_f desc",
            "new": "pretty_date_s desc",
            "popularity": "popularity desc",
            "rating": "popularity desc",
            "random": "popularity desc",
        }
        solr_sort = solr_sort_map.get(sort_by, "popularity desc")

        # 3. Fetch candidate batch
        deals: List[GameDeal] = []
        if not rank_range and sort_by in ["popularity", "random"] and not price_range_uah:
            # Use curated catalog first for default popularity queries
            deals = await self.eshop.fetch_popular_discounted_games(min_discount_percent=min_disc)

        if not deals:
            deals = await self.eshop.fetch_discounted_games(
                rows=rows,
                start=start,
                sort=solr_sort,
                min_discount_percent=min_disc,
            )

        if not deals:
            return []

        # 4. Filter by price range (in UAH) if specified
        if price_range_uah:
            min_p, max_p = price_range_uah
            filtered_by_price = []
            for d in deals:
                price_val = d.discount_price
                if currency_service and hasattr(currency_service, "convert"):
                    price_val = currency_service.convert(d.discount_price, d.currency, "UAH")
                if min_p <= price_val <= max_p:
                    filtered_by_price.append(d)
            deals = filtered_by_price

        if not deals:
            return []

        # 5. Selection / Sorting
        if is_random:
            selected = random.sample(deals, min(limit, len(deals)))
        elif sort_by == "rating":
            if self.ratings and self.ratings.api_key:
                deals = await self.enrich_batch(deals[:min(20, len(deals))], fetch_regions=False)
                deals.sort(key=self.calculate_deal_score, reverse=True)
            selected = deals[:limit]
        elif sort_by == "discount":
            deals.sort(key=lambda d: d.discount_percent, reverse=True)
            selected = deals[:limit]
        elif sort_by == "price_asc":
            deals.sort(key=lambda d: d.discount_price)
            selected = deals[:limit]
        elif sort_by == "price_desc":
            deals.sort(key=lambda d: d.discount_price, reverse=True)
            selected = deals[:limit]
        else:
            selected = deals[:limit]

        return selected

