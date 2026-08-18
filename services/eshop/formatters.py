"""Message formatters for eShop game deal cards with regional breakdown."""

import html
from typing import Optional
from services.eshop.currency_service import CurrencyService

_default_currency_service = CurrencyService()


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

    price_text = (
        f"💰 <s>{deal.regular_price:.2f} {curr}</s> ➡️ <b>{deal.discount_price:.2f} {curr}</b> "
        f"(<b>-{deal.discount_percent:.0f}%</b>){conv_part}"
    )

    # Categories
    categories_text = ""
    if deal.categories:
        clean_cats = [html.escape(c) for c in deal.categories[:3]]
        genre_label = "Жанри" if is_ua else "Genres"
        categories_text = f"🏷 <b>{genre_label}:</b> {', '.join(clean_cats)}\n"

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
            region_lines.append(
                f"{medal} {p.flag_emoji} {p.country_name}: <b>{p.discount_price:.2f} {p.currency}</b>{disc_label} (<i>{conv_str}</i>)"
            )

        pl_price = deal.get_price_for_country("PL")
        if pl_price and "PL" not in cheapest_codes:
            disc_label = f" (-{pl_price.discount_percent:.0f}%)" if pl_price.is_discount and pl_price.discount_percent > 0 else ""
            conv_str = _format_price_conv(pl_price)
            region_lines.append(
                f"🇵🇱 Poland: <b>{pl_price.discount_price:.2f} {pl_price.currency}</b>{disc_label} (<i>{conv_str}</i>)"
            )

        us_price = deal.get_price_for_country("US")
        if us_price and "US" not in cheapest_codes:
            disc_label = f" (-{us_price.discount_percent:.0f}%)" if us_price.is_discount and us_price.discount_percent > 0 else ""
            conv_str = _format_price_conv(us_price)
            region_lines.append(
                f"🇺🇸 USA: <b>{us_price.discount_price:.2f} {us_price.currency}</b>{disc_label} (<i>{conv_str}</i>)"
            )

    regional_text = ""
    if region_lines:
        reg_header = "🌍 <b>Ціни в регіонах eShop:</b>" if is_ua else "🌍 <b>Regional Prices & Best Deals:</b>"
        regional_text = f"{reg_header}\n" + "\n".join(region_lines) + "\n"

    # Excerpt / Description
    desc_text = ""
    if deal.excerpt:
        clean_excerpt = html.escape(deal.excerpt.strip())
        if len(clean_excerpt) > 200:
            clean_excerpt = clean_excerpt[:197] + "..."
        desc_text = f"📝 <i>{clean_excerpt}</i>\n"

    # Store link
    link_text = ""
    if deal.url:
        link_label = "Відкрити в Nintendo eShop" if is_ua else "Open in Nintendo eShop"
        link_text = f"🛒 <a href='{deal.url}'>{link_label}</a>"

    lines = [
        f"🎮 <b>{title_escaped}</b>\n",
        price_text,
        f"📊 {rating_text}",
        categories_text,
        regional_text,
        desc_text,
        link_text,
    ]

    return "\n".join([line for line in lines if line])
