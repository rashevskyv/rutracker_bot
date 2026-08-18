"""Message formatters for eShop game deal cards with regional breakdown."""

import html
import re
from typing import Optional
from services.eshop.models import GameDeal
from services.eshop.currency_service import CurrencyService

_default_currency_service = CurrencyService()

COUNTRY_NAMES_UA = {
    "PL": "Польща",
    "US": "США",
    "TH": "Таїланд",
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
    """Format a GameDeal instance into an attractive HTML message for Telegram."""
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

    price_text = (
        f"{prefix_label}<s>{deal.regular_price:.2f} {curr}</s> ➡️ <b>{deal.discount_price:.2f} {curr}</b> "
        f"(<b>-{deal.discount_percent:.0f}%</b>){conv_part}"
    )

    # Categories / Genres (Untranslated English with Hashtags)
    categories_text = ""
    if deal.categories:
        hashtags = [_format_genre_hashtag(c) for c in deal.categories[:4]]
        valid_tags = [t for t in hashtags if t]
        if valid_tags:
            categories_text = f"🏷 {' '.join(valid_tags)}\n"

    # Regional Price Comparison Section
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
            region_lines.append(
                f"{medal} {p.flag_emoji} {c_name}: <b>{p.discount_price:.2f} {p.currency}</b>{disc_label} (<i>{conv_str}</i>)"
            )

        # Pinned regions to always show if available and not already in top 3
        pinned_targets = [
            ("PL", "Poland", "Польща", "🇵🇱"),
            ("US", "USA", "США", "🇺🇸"),
            ("TH", "Thailand", "Таїланд", "🇹🇭"),
            ("TR", "Turkey", "Туреччина", "🇹🇷"),
        ]

        for code, name_en, name_ua, flag in pinned_targets:
            if code not in cheapest_codes:
                p_price = deal.get_price_for_country(code)
                if p_price:
                    disc_label = f" (-{p_price.discount_percent:.0f}%)" if p_price.is_discount and p_price.discount_percent > 0 else ""
                    conv_str = _format_price_conv(p_price)
                    c_name = name_ua if is_ua else name_en
                    region_lines.append(
                        f"{flag} {c_name}: <b>{p_price.discount_price:.2f} {p_price.currency}</b>{disc_label} (<i>{conv_str}</i>)"
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

    # Store link
    link_text = ""
    if deal.url:
        link_label = "Відкрити в Nintendo eShop" if is_ua else "Open in Nintendo eShop"
        link_text = f"🛒 <a href='{deal.url}'>{link_label}</a>"

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
