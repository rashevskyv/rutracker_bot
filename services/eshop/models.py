"""Data models for eShop game deals, ratings, and regional pricing."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class RegionalPrice:
    """Represents a game price in a specific country/region."""

    country_code: str
    country_name: str
    currency: str
    regular_price: float
    discount_price: float
    discount_percent: float
    converted_usd: float
    is_discount: bool = False

    @property
    def flag_emoji(self) -> str:
        """Return a flag emoji corresponding to the country code."""
        flags = {
            "US": "🇺🇸",
            "PL": "🇵🇱",
            "ZA": "🇿🇦",
            "JP": "🇯🇵",
            "NO": "🇳🇴",
            "GB": "🇬🇧",
            "AU": "🇦🇺",
            "CZ": "🇨🇿",
            "BR": "🇧🇷",
            "MX": "🇲🇽",
            "CA": "🇨🇦",
            "NZ": "🇳🇿",
            "SE": "🇸🇪",
            "CH": "🇨🇭",
            "EU": "🇪🇺",
            "DE": "🇩🇪",
            "FR": "🇫🇷",
            "ES": "🇪🇸",
            "IT": "🇮🇹",
        }
        return flags.get(self.country_code.upper(), "🌐")


@dataclass
class QualityCriteria:
    """Quality filtering criteria for game deals."""

    min_discount_percent: float = 30.0
    min_metacritic_score: int = 70
    min_rawg_rating: float = 3.5
    max_price: Optional[float] = None
    require_rating: bool = False


@dataclass
class RatingInfo:
    """Rating information retrieved from external providers."""

    metacritic_score: Optional[int] = None
    rawg_rating: Optional[float] = None
    rawg_ratings_count: int = 0
    genres: List[str] = field(default_factory=list)
    description: Optional[str] = None
    banner_url: Optional[str] = None


@dataclass
class GameDeal:
    """Represents a game deal found on Nintendo eShop."""

    fs_id: str
    title: str
    regular_price: float
    discount_price: float
    discount_percent: float
    currency: str = "EUR"
    nsuid: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    banner_url: Optional[str] = None
    excerpt: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    publishers: List[str] = field(default_factory=list)
    release_date: Optional[str] = None
    downloads_rank: Optional[int] = None
    hits: Optional[int] = None
    metacritic_score: Optional[int] = None
    rawg_rating: Optional[float] = None
    rawg_ratings_count: int = 0
    regional_prices: List[RegionalPrice] = field(default_factory=list)

    @property
    def savings(self) -> float:
        """Calculate absolute amount saved in base currency."""
        return round(max(0.0, self.regular_price - self.discount_price), 2)

    def get_cheapest_regions(self, count: int = 3) -> List[RegionalPrice]:
        """Return the top N cheapest regions sorted by converted USD price."""
        if not self.regional_prices:
            return []
        sorted_prices = sorted(self.regional_prices, key=lambda p: p.converted_usd)
        return sorted_prices[:count]

    def get_price_for_country(self, country_code: str) -> Optional[RegionalPrice]:
        """Find the price for a specific country code (e.g. 'PL', 'US')."""
        target = country_code.upper()
        for p in self.regional_prices:
            if p.country_code.upper() == target:
                return p
        return None

    def matches_criteria(self, criteria: QualityCriteria) -> bool:
        """Check whether the deal passes quality filtering."""
        if self.discount_percent < criteria.min_discount_percent:
            return False

        if criteria.max_price is not None and self.discount_price > criteria.max_price:
            return False

        has_metacritic = self.metacritic_score is not None
        has_rawg = self.rawg_rating is not None and self.rawg_rating > 0

        if criteria.require_rating and not (has_metacritic or has_rawg):
            return False

        if has_metacritic and self.metacritic_score < criteria.min_metacritic_score:
            if not (has_rawg and self.rawg_rating >= criteria.min_rawg_rating):
                return False

        if has_rawg and not has_metacritic and self.rawg_rating < criteria.min_rawg_rating:
            return False

        return True
