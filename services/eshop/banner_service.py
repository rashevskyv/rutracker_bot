"""Service for downloading and rendering platform badges on game cover images."""

import asyncio
import io
import logging
import ssl
from typing import Optional
import aiohttp
from PIL import Image, ImageDraw, ImageFont

from services.eshop.models import GameDeal

logger = logging.getLogger(__name__)


def overlay_platform_badge(image_bytes: bytes, deal: GameDeal) -> io.BytesIO:
    """
    Overlay a stylish, high-contrast platform badge (Switch, Switch 2, or Switch 1 & 2)
    on top of the game cover image.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    # Mode determination
    if deal.is_switch_2_exclusive:
        badge_text = "Nintendo Switch 2  •  EXCLUSIVE"
        bg_fill = (180, 0, 25, 245)
        border_col = (255, 215, 0, 255)  # Gold border for exclusive
        border_w = 3
    elif "Nintendo Switch 2" in deal.system_names or (
        "Nintendo Switch" in deal.system_names and "Nintendo Switch 2" in deal.system_names
    ):
        badge_text = "Nintendo Switch 1 & 2"
        bg_fill = (220, 10, 30, 240)
        border_col = (255, 255, 255, 220)
        border_w = 2
    else:
        badge_text = "Nintendo Switch"
        bg_fill = (230, 0, 18, 240)
        border_col = (255, 255, 255, 220)
        border_w = 2

    # Responsive sizing
    font_size = max(18, int(h * 0.045))
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

    pad_x = int(font_size * 0.8)
    pad_y = int(font_size * 0.45)
    margin = int(min(w, h) * 0.04)
    x0, y0 = margin, margin

    # Mini Joycon dimensions
    icon_h = int(th * 1.0)
    icon_w = int(icon_h * 0.42)
    gap = int(icon_w * 0.3)
    total_icon_w = icon_w * 2 + gap

    x1 = x0 + pad_x + total_icon_w + int(font_size * 0.5) + tw + pad_x
    y1 = y0 + th + pad_y * 2
    radius = int(font_size * 0.5)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Subtle drop shadow
    draw.rounded_rectangle([x0 + 3, y0 + 3, x1 + 3, y1 + 3], radius=radius, fill=(0, 0, 0, 150))
    # 2. Pill background
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg_fill, outline=border_col, width=border_w)

    # 3. Mini Joy-Cons icon
    cur_x = x0 + pad_x
    cur_y = y0 + pad_y + int((th - icon_h) / 2)
    draw.rounded_rectangle(
        [cur_x, cur_y, cur_x + icon_w, cur_y + icon_h],
        radius=max(2, int(icon_w * 0.35)),
        fill=(255, 255, 255),
    )
    draw.rounded_rectangle(
        [cur_x + icon_w + gap, cur_y, cur_x + icon_w * 2 + gap, cur_y + icon_h],
        radius=max(2, int(icon_w * 0.35)),
        fill=(255, 255, 255),
    )

    # 4. Badge text
    text_x = cur_x + total_icon_w + int(font_size * 0.5)
    draw.text((text_x, y0 + pad_y), badge_text, fill=(255, 255, 255), font=font)

    # Composite and save to buffer
    final_img = Image.alpha_composite(img, overlay).convert("RGB")
    out_buf = io.BytesIO()
    final_img.save(out_buf, format="JPEG", quality=92)
    out_buf.seek(0)
    return out_buf


async def download_and_badge_cover(
    deal: GameDeal, session: Optional[aiohttp.ClientSession] = None
) -> Optional[io.BytesIO]:
    """
    Download game cover image and apply the platform badge overlay.
    Returns BytesIO buffer or None on failure.
    """
    img_url = deal.banner_url or deal.image_url
    if not img_url:
        return None

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
        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.read()
                return overlay_platform_badge(data, deal)
    except Exception as e:
        logger.debug(f"Failed to download/badge image for '{deal.title}': {e}")
    finally:
        if owns_session and session and not session.closed:
            await session.close()

    return None
