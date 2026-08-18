"""Unit tests for the integrated eShop Deals module in RuTracker Bot."""

import pytest
from services.eshop import (
    CurrencyService,
    DealFilterEngine,
    EShopService,
    GameDeal,
    QualityCriteria,
    RegionalPrice,
    format_eshop_deal_message,
)


def test_eshop_currency_conversion():
    cs = CurrencyService()
    cs._rates = {"USD": 1.0, "EUR": 0.9, "PLN": 4.0, "UAH": 41.50}
    assert cs.convert_to_usd(40.0, "PLN") == 10.0
    assert cs.convert_to_usd(90.0, "EUR") == 100.0
    assert cs.convert_to_uah(40.0, "PLN") == 415.0  # 10 USD * 41.5


def test_eshop_regional_formatting():
    p1 = RegionalPrice(
        country_code="PL",
        country_name="Poland",
        currency="PLN",
        regular_price=40.0,
        discount_price=20.0,
        discount_percent=50.0,
        converted_usd=5.0,
        converted_uah=207.5,
        is_discount=True,
    )
    p2 = RegionalPrice(
        country_code="ZA",
        country_name="South Africa",
        currency="ZAR",
        regular_price=100.0,
        discount_price=60.0,
        discount_percent=40.0,
        converted_usd=3.0,
        converted_uah=124.5,
        is_discount=True,
    )

    deal = GameDeal(
        fs_id="123",
        title="Test Game",
        regular_price=30.0,
        discount_price=15.0,
        discount_percent=50.0,
        regional_prices=[p1, p2],
    )

    msg_ua = format_eshop_deal_message(deal, language="UA")
    assert "Test Game" in msg_ua
    assert "Poland" in msg_ua
    assert "South Africa" in msg_ua
    assert "Ціни в регіонах eShop" in msg_ua
    assert "грн" in msg_ua
