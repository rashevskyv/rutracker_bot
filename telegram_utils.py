# --- START OF FILE telegram_utils.py ---
import aiohttp
import asyncio
from io import BytesIO
from html.parser import HTMLParser
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096

# --- HTML Parsing for Splitting ---

class HTMLTagParser(HTMLParser):
    """Helper class to track open HTML tags."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tags: List[str] = [] # Stack of open tags

    def handle_starttag(self, tag: str, attrs):
        # We only care about non-self-closing tags for nesting purposes
        if tag not in ('br', 'img', 'hr'):
            self.tags.append(tag)

    def handle_endtag(self, tag: str):
        # If the closing tag matches the last open tag, pop it from the stack
        if tag not in ('br', 'img', 'hr'):
            if self.tags and self.tags[-1] == tag:
                self.tags.pop()

    def get_unclosed_tags(self) -> List[str]:
        """Returns a copy of the current stack of unclosed tags."""
        return self.tags[:]

def check_html_tags(text: str) -> List[str]:
    """
    Parses HTML text and returns a list of unclosed tags.
    Used for ensuring tags are properly closed when splitting messages.
    """
    parser = HTMLTagParser()
    parser.feed(text)
    return parser.get_unclosed_tags()

def close_tags(tags: List[str]) -> str:
    """Generates closing tags for a list of open tags in reverse order."""
    return "".join([f"</{tag}>" for tag in reversed(tags)])


# --- Text Splitting ---

def split_text(text: str, max_length: int) -> List[str]:
    """
    Splits text into parts respecting max_length and HTML tag integrity.

    Args:
        text: The HTML text to split.
        max_length: The maximum length allowed for each part.

    Returns:
        A list of text parts, each respecting the max_length and HTML rules.
    """
    parts: List[str] = []
    current_part = ""
    open_tags_stack: List[str] = [] # Track open tags across lines/parts

    lines = text.split('\n')

    for line_index, line in enumerate(lines):
        line_with_newline = line + ('\n' if line_index < len(lines) - 1 else '')

        # Calculate prefix tags needed for the current line
        prefix_tags = "".join([f"<{tag}>" for tag in open_tags_stack])

        # Calculate projected length if this line is added to the current part
        projected_length = len(current_part) + len(prefix_tags) + len(line_with_newline)

        if projected_length <= max_length:
            # Line fits, add it (with prefix tags) to the current part
            current_part += prefix_tags + line_with_newline
            # Update the open tags stack based on this line's content
            line_parser = HTMLTagParser()
            line_parser.tags = open_tags_stack[:] # Start with current stack
            line_parser.feed(line) # Process only the current line's tags
            open_tags_stack = line_parser.get_unclosed_tags()
        else:
            # Line does not fit
            if current_part:
                # Finish the current part
                part_parser = HTMLTagParser()
                part_parser.feed(current_part) # Parse the whole finished part
                final_open_tags = part_parser.get_unclosed_tags()
                current_part += close_tags(final_open_tags) # Close tags for this part
                parts.append(current_part)
                # Start new part with the current line, reusing the open tags
                open_tags_stack = final_open_tags # Carry over open tags
                current_part = "".join([f"<{tag}>" for tag in open_tags_stack]) + line_with_newline
                # Update open tags based on the new line
                line_parser = HTMLTagParser()
                line_parser.tags = open_tags_stack[:]
                line_parser.feed(line)
                open_tags_stack = line_parser.get_unclosed_tags()
            else:
                # Current part is empty, but the line itself is too long
                # Force split the line (basic split, might break mid-tag if line is huge)
                available_space = max_length - len(prefix_tags)
                parts.append(prefix_tags + line_with_newline[:available_space])
                # Reset for next part (assume the forced split broke tags)
                current_part = ""
                open_tags_stack = []

    # Add the last part if it contains text
    if current_part.strip():
        part_parser = HTMLTagParser()
        part_parser.feed(current_part)
        final_open_tags = part_parser.get_unclosed_tags()
        current_part += close_tags(final_open_tags)
        parts.append(current_part)

    # Return non-empty, stripped parts
    return [p.strip() for p in parts if p.strip()]

# --- Image Downloading for Telegram ---

async def _try_download_image_tg(image_url: str, timeout: int = 15) -> Optional[BytesIO]:
    """Attempts to download an image from a URL into a BytesIO object."""
    if not image_url or not image_url.startswith(('http://', 'https://')):
        logger.debug(f"TG: Invalid image URL: {image_url}")
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0 (TelegramSender)'}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(image_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.read()
                
                content_type = response.headers.get('Content-Type', '').lower()
                if not content_type.startswith('image/'):
                     logger.warning(f"TG: URL is not an image (Content-Type: {content_type}): {image_url}")
                     return None

                img_data = BytesIO(content)
                if img_data.getbuffer().nbytes == 0:
                    logger.warning(f"TG: Download resulted in empty file: {image_url}")
                    return None

                img_data.seek(0)
                return img_data
    except Exception as e:
        logger.error(f"TG: Download failed (Error: {e}): {image_url}")
        return None

async def download_cover_image_tg(image_url: Optional[str], timeout: int = 15) -> Optional[BytesIO]:
    """
    Downloads the cover image, with a fallback placeholder if needed.
    Returns a BytesIO object or None.
    """
    fallback_url = 'https://via.placeholder.com/300x200.png/EEEEEE/000000?text=No+Cover'
    logger.debug("TG: Attempting to download cover image...")

    image = await _try_download_image_tg(image_url, timeout) if image_url else None

    if image:
        logger.debug("TG: Cover image downloaded successfully.")
        return image
    else:
        logger.warning("TG: Cover download failed or URL was empty. Trying fallback...")
        if image_url != fallback_url:
            fallback_image = await _try_download_image_tg(fallback_url, timeout)
            if fallback_image:
                logger.info("TG: Fallback image downloaded.")
                return fallback_image
            else:
                logger.error("TG: Fallback image download also failed.")
        else:
            logger.debug("TG: Original URL was the fallback, not attempting again.")
        return None

async def download_trailer_thumbnail_tg(video_id: Optional[str], timeout: int = 15) -> Tuple[Optional[BytesIO], Optional[str]]:
    """
    Downloads the best available YouTube thumbnail for a video ID.

    Args:
        video_id: The YouTube video ID.
        timeout: Download timeout in seconds.

    Returns:
        A tuple containing:
        - BytesIO object of the thumbnail image (or None if failed).
        - String key representing the resolution ('maxres', 'sd', etc.) or None.
    """
    if not video_id:
        return None, None

    logger.debug(f"TG: Attempting to download trailer thumbnail for video ID: {video_id}")

    # Try resolutions from highest to lowest
    resolutions = [
        ("maxres", "maxresdefault"), # Max resolution
        ("sd", "sddefault"),         # Standard definition
        ("hq", "hqdefault"),         # High quality
        ("mq", "mqdefault"),         # Medium quality
        ("default", "default"),      # Default (low quality)
    ]

    for res_key, filename_part in resolutions:
        url = f"https://img.youtube.com/vi/{video_id}/{filename_part}.jpg"
        image = await _try_download_image_tg(url, timeout)
        if image:
            logger.debug(f"  TG: Successfully downloaded thumbnail ({res_key}): {url}")
            return image, res_key # Return image data and resolution key

    logger.warning(f"  TG: Failed to download any thumbnail for video ID: {video_id}")
    return None, None # Return None if all resolutions failed

# --- END OF FILE telegram_utils.py ---