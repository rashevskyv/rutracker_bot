"""Message formatters for eShop game deal cards with regional breakdown and direct regional store links."""

import html
import re
import urllib.parse
from typing import Optional
from services.eshop.models import GameDeal
from services.eshop.currency_service import CurrencyService

_default_currency_service = CurrencyService()

COUNTRY_NAMES_UA = {
    "PL": "Польща",
    "US": "США",
    "TH": "Тайланд",
    "TR": "Туреччина",
    "ZA": "ПАР",
    "JP": "Японія",
    "NO": "Норвегія",
    "GB": "Велика Британія",
    "AU": "Австралія",
    "CZ": "Чехія",
    "BR": "Бразилія",
    "MX": "Мексика",
    "CA": "Канада",
    "NZ": "Нова Зеландія",
    "SE": "Швеція",
    "CH": "Швейцарія",
    "DE": "Німеччина",
    "FR": "Франція",
    "ES": "Іспанія",
    "IT": "Італія",
    "HK": "Гонконг",
    "AR": "Аргентина",
    "CO": "Колумбія",
    "CL": "Чилі",
    "PE": "Перу",
}

GENRE_TRANSLATIONS = {
    "Action": "Екшен",
    "Adventure": "Пригоди",
    "Role-Playing": "RPG",
    "Strategy": "Стратегія",
    "Puzzle": "Головоломка",
    "Platformer": "Платформер",
    "Arcade": "Аркада",
    "Simulation": "Симулятор",
    "Sports": "Спорт",
    "Racing": "Гонки",
    "Fighting": "Файтинг",
    "Shooter": "Шутер",
    "Music": "Музика",
    "Party": "Вечірка",
    "Board Game": "Настільні",
    "Education": "Освіта",
    "Communication": "Спілкування",
    "Lifestyle": "Лайфстайл",
    "Utility": "Утиліти",
    "Other": "Інше",
}


def get_region_eshop_url(country_code: str, title: str, game_url: str = "") -> str:
    """Build direct official Nintendo eShop link for a specific region."""
    q = urllib.parse.quote_plus(title)
    code = (country_code or "").upper()
    if code == "US":
        return f"https://www.nintendo.com/us/search/#q={q}"
    elif code == "CA":
        return f"https://www.nintendo.com/en-ca/search/#q={q}"
    elif code in ["GB", "PL", "DE", "FR", "ES", "IT", "NL", "PT", "CZ", "SE", "NO", "CH"]:
        return f"https://www.nintendo.com/en-gb/Search/Search-299117.html?q={q}"
    elif code == "ZA":
        return f"https://www.nintendo.co.za/Search/Search-299117.html?q={q}"
    elif code == "TH":
        return f"https://store.nintendo.com/th/search/?q={q}"
    elif code == "AR":
        return f"https://store.nintendo.com.ar/catalogsearch/result/?q={q}"
    elif code == "CL":
        return f"https://store.nintendo.cl/catalogsearch/result/?q={q}"
    elif code == "PE":
        return f"https://store.nintendo.com.pe/catalogsearch/result/?q={q}"
    elif code == "BR":
        return f"https://store.nintendo.com.br/catalogsearch/result/?q={q}"
    elif code == "MX":
        return f"https://www.nintendo.com/es-mx/search/#q={q}"
    elif code in ["AU", "NZ"]:
        return f"https://www.nintendo.com/au/search/#q={q}"
    elif code == "JP":
        return f"https://store-jp.nintendo.com/search/?q={q}"
    elif code == "HK":
        return f"https://www.nintendo.com.hk/search/?q={q}"
    elif game_url:
        return game_url
    return f"https://www.nintendo.com/en-gb/Search/Search-299117.html?q={q}"


def _format_genre_hashtag(genre: str) -> str:
    """Format genre into clean English hashtag without translation."""
    if not genre:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9]", "", genre.title().replace(" ", "").replace("-", ""))
    if clean.lower() in ["roleplaying", "roleplayinggame"]:
        clean = "RPG"
    return f"#{clean}" if clean else ""


def format_eshop_deal_message(
    deal: GameDeal, language: str = "UA", currency_service: Optional[CurrencyService] = None
) -> str:
    """Format a GameDeal instance into an attractive HTML message for Telegram with clickable regional prices."""
    title_escaped = html.escape(deal.title)
    is_ua = language.upper() == "UA"
    cs = currency_service or _default_currency_service

    # Rating lines
    ratings = []
    if deal.metacritic_score is not None:
        ratings.append(f"⭐ <b>Metacritic:</b> {deal.metacritic_score}/100")
    if deal.rawg_rating is not None and deal.rawg_rating > 0:
        ratings.append(f"🌟 <b>RAWG:</b> {deal.rawg_rating:.1f}/5.0")
    if not ratings and deal.downloads_rank and deal.downloads_rank < 90000:
        rank_label = "Популярність" if is_ua else "Popularity Rank"
        ratings.append(f"🔥 <b>{rank_label}:</b> #{deal.downloads_rank}")

    unrated_label = "<i>Без оцінки</i>" if is_ua else "<i>Unrated</i>"
    rating_text = " | ".join(ratings) if ratings else unrated_label

    # Price and discount
    curr = deal.currency if deal.currency else "EUR"
    uah_val = cs.convert_to_uah(deal.discount_price, curr)
    usd_val = cs.convert_to_usd(deal.discount_price, curr)

    conv_part = ""
    if uah_val > 0 and usd_val > 0 and curr.upper() not in ["UAH"]:
        conv_part = f" (<i>~{uah_val:.0f} грн / ${usd_val:.2f}</i>)"

    region_prefix = "🇪🇺 " if curr.upper() == "EUR" else ("🇺🇸 " if curr.upper() == "USD" else "")
    region_name = "Європа" if (curr.upper() == "EUR" and is_ua) else ("Europe" if curr.upper() == "EUR" else "")
    prefix_label = f"💰 {region_prefix}<b>{region_name}:</b> " if region_name else "💰 "
    has_discount = deal.discount_percent > 0 and (deal.regular_price is None or deal.regular_price > deal.discount_price)

    main_store_url = deal.url or get_region_eshop_url("GB" if curr.upper() == "EUR" else "US", deal.title)
    if has_discount and deal.regular_price is not None:
        price_text = (
            f"{prefix_label}<s>{deal.regular_price:.2f} {curr}</s> ➡️ <a href='{main_store_url}'><b>{deal.discount_price:.2f} {curr}</b></a> "
            f"(<b>-{deal.discount_percent:.0f}%</b>){conv_part}"
        )
    else:
        disp_price = deal.discount_price if deal.discount_price is not None else (deal.regular_price or 0.0)
        price_text = f"{prefix_label}<a href='{main_store_url}'><b>{disp_price:.2f} {curr}</b></a>{conv_part}"

    # Categories / Genres (Untranslated English with Hashtags)
    categories_text = ""
    if deal.categories:
        hashtags = [_format_genre_hashtag(c) for c in deal.categories[:4]]
        valid_tags = [t for t in hashtags if t]
        if valid_tags:
            categories_text = f"🏷 {' '.join(valid_tags)}\n"

    # Regional Price Comparison Section with clickable store links
    region_lines = []
    if deal.regional_prices:
        cheapest_3 = deal.get_cheapest_regions(3)
        medals = ["🥇", "🥈", "🥉"]
        cheapest_codes = set()

        def _format_price_conv(p) -> str:
            if p.converted_uah > 0 and p.converted_usd > 0:
                return f"~{p.converted_uah:.0f} грн / ${p.converted_usd:.2f}"
            if p.converted_uah > 0:
                return f"~{p.converted_uah:.0f} грн"
            return f"~${p.converted_usd:.2f}"

        for idx, p in enumerate(cheapest_3):
            cheapest_codes.add(p.country_code.upper())
            medal = medals[idx] if idx < len(medals) else "•"
            disc_label = f" (-{p.discount_percent:.0f}%)" if p.is_discount and p.discount_percent > 0 else ""
            conv_str = _format_price_conv(p)
            c_name = COUNTRY_NAMES_UA.get(p.country_code.upper(), p.country_name) if is_ua else p.country_name
            p_url = get_region_eshop_url(p.country_code, deal.title, deal.url)
            price_link = f"<a href='{p_url}'><b>{p.discount_price:.2f} {p.currency}</b></a>"
            region_lines.append(
                f"{medal} {p.flag_emoji} {c_name}: {price_link}{disc_label} (<i>{conv_str}</i>)"
            )

        # Pinned regions to always show if available and not already in top 3:
        # ПАР (ZA), Тайланд (TH), Польща (PL), Норвегія (NO)
        pinned_targets = [
            ("ZA", "South Africa", "ПАР", "🇿🇦"),
            ("TH", "Thailand", "Тайланд", "🇹🇭"),
            ("PL", "Poland", "Польща", "🇵🇱"),
            ("NO", "Norway", "Норвегія", "🇳🇴"),
            ("US", "USA", "США", "🇺🇸"),
        ]

        for code, name_en, name_ua, flag in pinned_targets:
            if code not in cheapest_codes:
                p_price = deal.get_price_for_country(code)
                if p_price:
                    disc_label = f" (-{p_price.discount_percent:.0f}%)" if p_price.is_discount and p_price.discount_percent > 0 else ""
                    conv_str = _format_price_conv(p_price)
                    c_name = name_ua if is_ua else name_en
                    p_url = get_region_eshop_url(code, deal.title, deal.url)
                    price_link = f"<a href='{p_url}'><b>{p_price.discount_price:.2f} {p_price.currency}</b></a>"
                    region_lines.append(
                        f"{flag} {c_name}: {price_link}{disc_label} (<i>{conv_str}</i>)"
                    )

    regional_text = ""
    if region_lines:
        reg_header = "🌍 <b>Ціни в регіонах eShop:</b>" if is_ua else "🌍 <b>Regional Prices & Best Deals:</b>"
        regional_text = f"{reg_header}\n" + "\n".join(region_lines) + "\n"

    # Excerpt / Description
    desc_text = ""
    if deal.excerpt:
        clean_excerpt = html.escape(deal.excerpt.strip())
        if len(clean_excerpt) > 300:
            clean_excerpt = clean_excerpt[:297] + "..."
        desc_text = f"📝 <i>{clean_excerpt}</i>\n"

    # Platform
    platform_label = "Платформа" if is_ua else "Platform"
    platform_text = f"🕹 <b>{platform_label}:</b> {deal.platform_label}"

    # Store and eShop-Prices links
    eshop_prices_url = f"https://eshop-prices.com/games?q={urllib.parse.quote_plus(deal.title)}"
    links = []
    if deal.url:
        links.append(f"🛒 <a href='{deal.url}'>Nintendo eShop</a>")
    links.append(f"🌐 <a href='{eshop_prices_url}'>eShop-Prices.com</a>")
    link_text = " | ".join(links)

    lines = [
        f"🎮 <b>{title_escaped}</b>\n",
        price_text,
        f"📊 {rating_text}",
        platform_text,
        categories_text,
        regional_text,
        desc_text,
        link_text,
    ]

    return "\n".join([line for line in lines if line])
