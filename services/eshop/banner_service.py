"""Service for downloading and rendering high-resolution platform badges on game cover images."""

import asyncio
import io
import logging
import re
import ssl
from typing import List, Optional
import aiohttp
from PIL import Image, ImageDraw, ImageFont

from services.eshop.models import GameDeal

logger = logging.getLogger(__name__)


def _get_upgraded_image_urls(url: Optional[str]) -> List[str]:
    """Generate high-resolution candidates for Nintendo CDN URLs."""
    if not url:
        return []
    candidates = []
    # If URL contains _image500w or similar, build 1600w and 1200w variants
    if "_image500w." in url:
        candidates.append(url.replace("_image500w.", "_image1600w."))
        candidates.append(url.replace("_image500w.", "_image1200w."))
        candidates.append(url.replace("_image500w.", "_image800w."))
    elif "_banner_image_wishlist_640w." in url:
        candidates.append(url.replace("_banner_image_wishlist_640w.", "_banner_image_wishlist_1600w."))
        candidates.append(url.replace("_banner_image_wishlist_640w.", "_banner_image_wishlist_1200w."))
    elif "_banner_image_wishlist_460w." in url:
        candidates.append(url.replace("_banner_image_wishlist_460w.", "_banner_image_wishlist_1600w."))
        candidates.append(url.replace("_banner_image_wishlist_460w.", "_banner_image_wishlist_1200w."))

    candidates.append(url)
    return candidates


def overlay_platform_badge(image_bytes: bytes, deal: GameDeal) -> io.BytesIO:
    """
    Overlay a refined, sleek, high-definition platform badge (Switch, Switch 2, or Switch 1 & 2)
    on top of the game cover image using 2x supersampling and lossless color preservation.
    """
    base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base_img.size

    # Ensure minimum high-res canvas size for crisp display
    if w < 1000 or h < 550:
        target_w = max(1200, w * 2)
        target_h = int(h * (target_w / w))
        base_img = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        w, h = base_img.size

    # Badge specs
    if deal.is_switch_2_exclusive:
        badge_text = "Nintendo Switch 2  •  EXCLUSIVE"
        bg_fill = (195, 5, 25, 245)
        border_col = (255, 215, 60, 230)  # Gold accent border
        border_w = 3
    elif "Nintendo Switch 2" in deal.system_names or (
        "Nintendo Switch" in deal.system_names and "Nintendo Switch 2" in deal.system_names
    ):
        badge_text = "Nintendo Switch 1 & 2"
        bg_fill = (228, 0, 15, 245)
        border_col = (255, 255, 255, 230)
        border_w = 2
    else:
        badge_text = "Nintendo Switch"
        bg_fill = (228, 0, 15, 245)
        border_col = (255, 255, 255, 230)
        border_w = 2

    # Render at 2x scale for anti-aliasing / supersampling
    scale = 2
    sw, sh = w * scale, h * scale
    overlay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = int(sh * 0.040)
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    bbox = font.getbbox(badge_text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x = int(font_size * 0.75)
    pad_y = int(font_size * 0.40)
    margin = int(min(sw, sh) * 0.035)
    x0, y0 = margin, margin

    # Joy-Con vector icon dimensions
    icon_h = int(th * 1.05)
    icon_w = int(icon_h * 0.44)
    gap = max(3, int(icon_w * 0.3))
    total_icon_w = icon_w * 2 + gap

    x1 = x0 + pad_x + total_icon_w + int(font_size * 0.45) + tw + pad_x
    y1 = y0 + th + pad_y * 2
    radius = int((y1 - y0) / 2)

    # Ambient drop shadow
    for i in range(4):
        s_off = (i + 1) * 2
        s_alpha = int(45 / (i + 1))
        draw.rounded_rectangle(
            [x0 + s_off, y0 + s_off, x1 + s_off, y1 + s_off],
            radius=radius,
            fill=(0, 0, 0, s_alpha),
        )

    # Pill background
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=bg_fill,
        outline=border_col,
        width=max(2, int(scale * border_w * 0.75)),
    )

    # Joy-Con icons (Left & Right)
    cur_x = x0 + pad_x
    cur_y = y0 + pad_y + int((th - icon_h) / 2)
    # Left Joy-Con capsule
    draw.rounded_rectangle(
        [cur_x, cur_y, cur_x + icon_w, cur_y + icon_h],
        radius=int(icon_w * 0.45),
        fill=(255, 255, 255, 255),
    )
    # Right Joy-Con capsule
    draw.rounded_rectangle(
        [cur_x + icon_w + gap, cur_y, cur_x + icon_w * 2 + gap, cur_y + icon_h],
        radius=int(icon_w * 0.45),
        fill=(255, 255, 255, 255),
    )

    # Badge text
    text_x = cur_x + total_icon_w + int(font_size * 0.45)
    text_y = y0 + pad_y - bbox[1]
    draw.text((text_x, text_y), badge_text, fill=(255, 255, 255, 255), font=font)

    # Downscale overlay using LANCZOS onto base image
    overlay = overlay.resize((w, h), Image.Resampling.LANCZOS)
    final_img = Image.alpha_composite(base_img, overlay).convert("RGB")

    out_buf = io.BytesIO()
    # Save with ultra high quality, 4:4:4 color preservation (no compression artifacts)
    final_img.save(out_buf, format="JPEG", quality=96, subsampling=0, optimize=True)
    out_buf.seek(0)
    return out_buf


async def download_and_badge_cover(
    deal: GameDeal, session: Optional[aiohttp.ClientSession] = None
) -> Optional[io.BytesIO]:
    """
    Download game cover image with high-resolution fallback and apply the platform badge overlay.
    Returns BytesIO buffer or None on failure.
    """
    urls_to_try = []
    if deal.banner_url:
        urls_to_try.extend(_get_upgraded_image_urls(deal.banner_url))
    if deal.image_url:
        urls_to_try.extend(_get_upgraded_image_urls(deal.image_url))

    if not urls_to_try:
        return None

    # Deduplicate preserving order
    seen = set()
    unique_urls = []
    for u in urls_to_try:
        if u and u not in seen:
            seen.add(u)
            unique_urls.append(u)

    owns_session = False
    if session is None or session.closed:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        session = aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        owns_session = True

    try:
        for target_url in unique_urls:
            try:
                async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 5000:  # Valid image payload
                            return overlay_platform_badge(data, deal)
            except Exception as item_err:
                logger.debug(f"Failed to fetch image from {target_url}: {item_err}")
    except Exception as e:
        logger.debug(f"Failed in download_and_badge_cover for '{deal.title}': {e}")
    finally:
        if owns_session and session and not session.closed:
            await session.close()

    return None
