"""Nintendo eShop Deals Module for RuTracker Bot."""

from services.eshop.models import GameDeal, QualityCriteria, RegionalPrice
from services.eshop.eshop_service import EShopService
from services.eshop.currency_service import CurrencyService
from services.eshop.region_price_service import RegionPriceService
from services.eshop.rating_service import RatingService
from services.eshop.deal_filter import DealFilterEngine
from services.eshop.formatters import format_eshop_deal_message

__all__ = [
    "GameDeal",
    "QualityCriteria",
    "RegionalPrice",
    "EShopService",
    "CurrencyService",
    "RegionPriceService",
    "RatingService",
    "DealFilterEngine",
    "format_eshop_deal_message",
]
