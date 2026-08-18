import os
import json
import asyncio
import logging
from typing import List, Optional

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

        if fetch_regions and self.region_prices and deal.nsuid:
            prices = await self.region_prices.get_regional_prices_for_game(deal.nsuid)
            if prices:
                deal.regional_prices = prices

        # Translate game description to Ukrainian if present
        if deal.excerpt and deal.excerpt.strip():
            cache = _load_descriptions_cache()
            key = deal.fs_id or deal.title
            if key in cache and cache[key]:
                deal.excerpt = cache[key]
            else:
                try:
                    from services import gpt
                    prompt = (
                        "Translate the following Nintendo Switch game synopsis into natural, engaging Ukrainian in 1-2 short sentences for a Telegram post.\n"
                        "Keep it concise, clear, and output ONLY the Ukrainian text without markdown formatting, quotes, or notes.\n\n"
                        f"Game Title: {deal.title}\n"
                        f"Original Synopsis:\n{deal.excerpt.strip()}"
                    )
                    trans = await gpt.complete(prompt, max_tokens=250, label="eShop Excerpt")
                    if trans and trans.strip():
                        cleaned_trans = trans.strip().replace('"', '').replace('«', '').replace('»', '')
                        deal.excerpt = cleaned_trans
                        cache[key] = cleaned_trans
                        _save_descriptions_cache(cache)
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
