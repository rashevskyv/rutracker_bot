"""
Interactive Telegram Bot runner for RuTracker Bot.
Runs polling loop and responds to commands (/deals, /search, /subscribe_deals, etc.).
"""

import asyncio
import logging
import os
import sys

from core.logger_setup import setup_logging
from core.settings_loader import (
    bot,
    load_config,
    default_settings_path,
    local_settings_path,
)
from services.eshop import (
    CurrencyService,
    DealFilterEngine,
    EShopService,
    QualityCriteria,
    RatingService,
    RegionPriceService,
)
from services.eshop.bot_commands import register_eshop_handlers

logger = logging.getLogger("bot_interactive")


async def main():
    setup_logging()
    logger.info("Starting RuTracker Bot interactive mode with eShop Deals support...")

    cfg = load_config(local_settings_path) or load_config(default_settings_path) or {}
    eshop_cfg = cfg.get("ESHOP_DEALS", {})

    min_discount = float(eshop_cfg.get("min_discount_percent", 30.0))
    min_metacritic = int(eshop_cfg.get("min_metacritic_score", 70))
    min_rawg = float(eshop_cfg.get("min_rawg_rating", 3.5))
    rawg_key = os.environ.get("RAWG_API_KEY") or eshop_cfg.get("rawg_api_key")

    global_criteria = QualityCriteria(
        min_discount_percent=min_discount,
        min_metacritic_score=min_metacritic,
        min_rawg_rating=min_rawg,
    )

    currency_service = CurrencyService()
    await currency_service.refresh_rates()

    region_price_service = RegionPriceService(currency_service=currency_service)
    eshop_service = EShopService()
    rating_service = RatingService(api_key=rawg_key)

    filter_engine = DealFilterEngine(
        eshop_service=eshop_service,
        rating_service=rating_service,
        region_price_service=region_price_service,
    )

    # Register command handlers
    register_eshop_handlers(
        bot=bot,
        filter_engine=filter_engine,
        eshop_service=eshop_service,
        global_criteria=global_criteria,
        currency_service=currency_service,
    )

    logger.info("Interactive handlers registered. Starting bot polling...")
    try:
        await bot.polling(non_stop=True)
    finally:
        await eshop_service.close()
        await rating_service.close()
        await region_price_service.close()
        await currency_service.close()
        logger.info("Bot interactive mode stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
