# --- START OF FILE telegram_utils.py ---
import aiohttp
import asyncio
import re
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
    Splits HTML text into parts respecting max_length and tag integrity.
    Uses tokenization and preserves full start tags (with attributes).
    """
    if not text: return []
    
    # Tokenize: Split into tags, markers, and text segments
    # Include ###GAP### as a special token
    token_pattern = re.compile(r'(###GAP###|<[^>]+?>|[^<#]+|#)')
    tokens = token_pattern.findall(text)
    
    parts: List[str] = []
    current_part_tokens: List[str] = []
    current_length = 0
    # open_tags stores tuples of (tag_name, full_start_tag)
    open_tags: List[Tuple[str, str]] = []
    # open_tags_history stores the STATE of open_tags AFTER each token in current_part_tokens
    open_tags_history: List[List[Tuple[str, str]]] = []
    
    skip_next_whitespace = False
    for i, token in enumerate(tokens):
        # Skip any whitespace token immediately following a GAP split or conversion
        if skip_next_whitespace and token.isspace():
            continue
        skip_next_whitespace = False

        if token == "###GAP###":
            # If we are already mostly full (e.g. > 50%), split at this gap to keep sections together
            # BUT: Never split at gap if we are inside a blockquote or pre tag to keep them unified
            sensitive_tags = ["blockquote", "pre"]
            is_inside_sensitive = any(t[0] in sensitive_tags for t in open_tags)

            if current_length > max_length * 0.5 and not is_inside_sensitive:
                suffix = "".join([f"</{t[0]}>" for t in reversed(open_tags)])
                parts.append("".join(current_part_tokens).strip() + suffix)
                
                prefix = "".join([t[1] for t in open_tags])
                current_part_tokens = [prefix]
                current_length = len(prefix)
                open_tags_history = [open_tags[:]]
                skip_next_whitespace = True # Skip whitespace after split
            else:
                # If not splitting, convert GAP marker to exactly ONE blank line separation (\n\n)
                # We strip any already existing trailing newlines to avoid doubling up
                while current_part_tokens and current_part_tokens[-1].isspace():
                    last = current_part_tokens.pop()
                    current_length -= len(last)
                    if open_tags_history: open_tags_history.pop()
                
                gap_text = "\n\n"
                current_part_tokens.append(gap_text)
                current_length += len(gap_text)
                open_tags_history.append(open_tags[:])
                skip_next_whitespace = True # Skip whitespace after conversion
            continue # Gap marker itself is processed
            
        tag_name = None
        full_start_tag = None
        is_start = False
        is_end = False
        
        if token.startswith('<'):
            if token.startswith('</'):
                is_end = True
                m = re.match(r'</([a-zA-Z0-9-]+)', token)
                if m: tag_name = m.group(1).lower()
            elif not token.endswith('/>'):
                # Ignore self-closing tags
                is_start = True
                m = re.match(r'<([a-zA-Z0-9-]+)', token)
                if m:
                    tag_name = m.group(1).lower()
                    full_start_tag = token
                if tag_name in ('br', 'hr', 'img'):
                    is_start = False
        
        # Calculate overhead (closing tags)
        temp_open_tags = open_tags[:]
        if is_start and tag_name: temp_open_tags.append((tag_name, full_start_tag))
        elif is_end and tag_name and temp_open_tags and temp_open_tags[-1][0] == tag_name: temp_open_tags.pop()
        
        suffix_len = sum(len(f"</{t[0]}>") for t in reversed(temp_open_tags))
        
        # Check fit
        if current_length + len(token) + suffix_len <= max_length:
            current_part_tokens.append(token)
            current_length += len(token)
            if is_start and tag_name: open_tags.append((tag_name, full_start_tag))
            elif is_end and tag_name:
                if open_tags and open_tags[-1][0] == tag_name: open_tags.pop()
            open_tags_history.append(open_tags[:])
        else:
            # Token doesn't fit, finalize current part
            # BACKTRACKING: If we are inside a blockquote, try to move the WHOLE blockquote to the next part
            bq_found = False
            bq_start_idx = -1
            
            # Look for the last opened blockquote in current part
            for j in range(len(open_tags) - 1, -1, -1):
                if open_tags[j][0] == "blockquote":
                    bq_found = True
                    bq_tag = open_tags[j][1]
                    # Find where this blockquote started in current_part_tokens
                    for k in range(len(current_part_tokens) - 1, -1, -1):
                        if current_part_tokens[k] == bq_tag:
                            bq_start_idx = k
                            break
                    break
            
            # If we found a blockquote that started in this part, move it to the next part
            # (only if we have at least SOME content before it, otherwise we have no choice but to split)
            if bq_found and bq_start_idx > 0:
                # Part until just BEFORE the blockquote start
                backtracked_content = current_part_tokens[:bq_start_idx]
                moved_content = current_part_tokens[bq_start_idx:]
                
                # The tags that were open BEFORE the blockquote started are at index bq_start_idx-1 in history
                new_open_tags = open_tags_history[bq_start_idx-1]
                
                suffix = "".join([f"</{t[0]}>" for t in reversed(new_open_tags)])
                parts.append("".join(backtracked_content).strip() + suffix)
                
                # Start new part with the moved content + the current token
                open_tags = new_open_tags[:]
                prefix = "".join([t[1] for t in open_tags])
                
                # Process each moved token to restore open_tags state
                current_part_tokens = [prefix]
                open_tags_history = [open_tags[:]]
                for mt in moved_content:
                    # Update tags for each moved token
                    m_is_start = False; m_is_end = False; m_tag = None
                    if mt.startswith('<') and not mt.endswith('/>'):
                        if mt.startswith('</'):
                            m_is_end = True; m_m = re.match(r'</([a-zA-Z0-9-]+)', mt)
                            if m_m: m_tag = m_m.group(1).lower()
                        else:
                            m_is_start = True; m_m = re.match(r'<([a-zA-Z0-9-]+)', mt)
                            if m_m: m_tag = m_m.group(1).lower()
                            if m_tag in ('br', 'hr', 'img'): m_is_start = False
                    
                    if m_is_start and m_tag: open_tags.append((m_tag, mt))
                    elif m_is_end and m_tag and open_tags and open_tags[-1][0] == m_tag: open_tags.pop()
                    
                    current_part_tokens.append(mt)
                    open_tags_history.append(open_tags[:])
                
                # Finally add the token that triggered the split
                if is_start and tag_name: open_tags.append((tag_name, token))
                elif is_end and tag_name and open_tags and open_tags[-1][0] == tag_name: open_tags.pop()
                current_part_tokens.append(token)
                open_tags_history.append(open_tags[:])
                
                current_length = sum(len(t) for t in current_part_tokens)
            else:
                # Normal split
                suffix = "".join([f"</{t[0]}>" for t in reversed(open_tags)])
                parts.append("".join(current_part_tokens).strip() + suffix)
                
                # Start new part
                prefix = "".join([t[1] for t in open_tags])
                current_part_tokens = [prefix, token]
                current_length = len(prefix) + len(token)
                
                open_tags_history = [open_tags[:]] # Status AFTER prefix
                if is_start and tag_name: open_tags.append((tag_name, full_start_tag))
                elif is_end and tag_name and open_tags and open_tags[-1][0] == tag_name: open_tags.pop()
                open_tags_history.append(open_tags[:]) # Status AFTER token

    if current_part_tokens:
        suffix = "".join([f"</{t[0]}>" for t in reversed(open_tags)])
        parts.append("".join(current_part_tokens).strip() + suffix)

    # Combine parts with a temporary marker, normalize all GAPs, then split back.
    # This ensures exactly one blank line for GAP whether we split at it or not,
    # and collapses consecutive gaps into one.
    full_content = "###SPLIT_MARKER###".join(parts)
    full_content = re.sub(r'(?:\s*###GAP###\s*)+', '\n\n', full_content)
    
    # --- Final strict formatting rules enforcement ---
    # 1. Snap leading colons to the preceding word, eating any whitespace/newlines
    full_content = re.sub(r'\s+:', ':', full_content)
    
    # 2. Delete orphaned bullets (bullets with no text after them on the same line)
    # Using (?m) for multiple lines so `^•` matches cleanly.
    full_content = re.sub(r'(?m)^[ \t]*•[ \t]*(?=\n|$)', '', full_content)
    full_content = re.sub(r'•[ \t]*(?=\n)', '', full_content)
    
    # 3. Ensure no excessive empty lines (replace 3+ newlines with exactly 2 newlines, leaving 1 empty line)
    full_content = re.sub(r'\n{3,}', '\n\n', full_content)
    
    return [p.strip() for p in full_content.split('###SPLIT_MARKER###') if p.strip()]

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