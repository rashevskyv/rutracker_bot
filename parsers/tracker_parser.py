# --- START OF FILE tracker_parser.py ---
import aiohttp
import asyncio
from bs4 import BeautifulSoup, NavigableString, Tag
import re
import time
import html # Import html for escaping
import logging
from typing import Optional, Tuple, List # Import Optional, Tuple, List
# --- Import functions moved to html_utils ---
from utils.html_utils import clean_description_html, make_tag, sanitize_html_for_telegram
from core.settings_loader import get_session
# --------------------------------------------

logger = logging.getLogger(__name__)

# fetch_page_content remains the same
async def fetch_page_content(url: str, retries: int = 3, delay: int = 5) -> Optional[BeautifulSoup]:
    headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}
    session = get_session()
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=25, headers=headers) as response:
                response.raise_for_status()
                content = await response.read()
                soup = BeautifulSoup(content, "html.parser")
                return soup
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error fetching {url}: {e}")
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP Error fetching {url}: {e.status}")
            if e.status == 404: return None
            if 400 <= e.status < 500 and e.status != 429: return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url} (Attempt {attempt + 1}/{retries})")
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching {url}: {e}")
            break
        if attempt < retries - 1: await asyncio.sleep(delay)
        else: logger.error(f"Failed to fetch {url} after {retries} attempts."); return None

# get_last_post_with_phrase remains the same
async def get_last_post_with_phrase(phrase: str, base_url: str, max_pages_to_check: int = 5) -> Optional[str]:
    logger.debug(f"Searching for update phrase '{phrase}'...")
    posts_per_page = 30; last_page_offset = -1
    soup_first_page = await fetch_page_content(base_url)
    if soup_first_page:
        last_page_link = soup_first_page.find('a', class_='pg', string='Last')
        match = None
        if last_page_link and 'href' in last_page_link.attrs: match = re.search(r'start=(\d+)', last_page_link['href'])
        if match: last_page_offset = int(match.group(1))
        if last_page_offset == -1:
             page_links = soup_first_page.select('a.pg:not([rel="prev"]):not([rel="next"])'); highest_offset = 0
             for link in page_links:
                 match = re.search(r'start=(\d+)', link.get('href', ''))
                 if match:
                     highest_offset = max(highest_offset, int(match.group(1)))
             if highest_offset > 0: last_page_offset = highest_offset
    if last_page_offset == -1: last_page_offset = max(0, (max_pages_to_check - 1) * posts_per_page)
    checked_urls = set()
    for i in range(max_pages_to_check):
        current_offset = max(0, last_page_offset - (i * posts_per_page)); page_url = f"{base_url}&start={current_offset}"
        if page_url in checked_urls: continue; checked_urls.add(page_url)
        soup = await fetch_page_content(page_url)
        if not soup:
            if current_offset == 0: break; continue
        user_posts = soup.find_all("tbody", class_=re.compile(r"row[12]"))
        if not user_posts: continue
        for post in reversed(user_posts):
            post_body_div = post.find("div", class_="post_body")
            if not post_body_div: continue

            # Remove quote blocks before checking for phrase
            post_body_copy = post_body_div.__copy__()
            for quote in post_body_copy.find_all("div", class_="q-wrap"):
                quote.decompose()

            for br in post_body_copy.find_all("br"): br.replace_with("\n")
            post_text_content = post_body_copy.get_text(separator=" ", strip=True) # Check text content without quotes
            if phrase in post_text_content:
                logger.info(f"Found update phrase '{phrase}' in post on {page_url}")
                relevant_html_content = ""; found_phrase = False; stop_collecting = False
                for element in post_body_div.children:
                    element_str = str(element)
                    if phrase in element_str:
                        found_phrase = True
                        parts = element_str.split(phrase, 1)
                        if len(parts) > 1:
                            relevant_html_content += parts[1]
                        continue 

                    if found_phrase and not stop_collecting:
                        is_stop_marker = False
                        if isinstance(element, Tag):
                             if element.name == 'hr' or \
                                (element.get('class') and ('sp-wrap' in element.get('class') or 'q-wrap' in element.get('class'))) or \
                                (element.name == 'span' and element.get('class') and 'post-br' in element.get('class')): is_stop_marker = True
                        if is_stop_marker: stop_collecting = True
                        else: relevant_html_content += element_str

                if not found_phrase: continue 

                update_text_html = relevant_html_content.strip()
                # Strips leading commas, periods, and other common separator punctuation
                update_text_html = re.sub(r'^[.,\s!?:;-]+', '', update_text_html).strip()
                
                post_link_tag = post.find("a", class_="p-link small", href=re.compile(r'viewtopic\.php\?p='))
                post_url = ("https://rutracker.org/forum/" + post_link_tag["href"]) if post_link_tag else base_url
                cleaned_update_text = sanitize_html_for_telegram(update_text_html)
                update_keyword = "Details";
                if "внесённые изменения" in cleaned_update_text:
                     word = "внесённые изменения"; link_html = f'<a href="{post_url}">{word}</a>'
                     if word in cleaned_update_text:
                          return f"<b>Обновлено:</b> {cleaned_update_text.replace(word, link_html, 1)}"
                return f'<b>Обновлено:</b> <a href="{post_url}">{update_keyword}</a>\n{cleaned_update_text}'
        if current_offset == 0: break 
    return None 


async def get_update_from_author_post(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """
    Fallback: search for 'Обновлено до' pattern in author's posts.
    Used when the standard 'Раздача обновлена' phrase is not found.
    Takes the last (most recent) update entry.
    """
    logger.debug("Fallback: searching for 'Обновлено до' pattern in posts...")

    # Get the first post's author
    first_post = soup.find("tbody", class_=re.compile(r"row[12]"))
    if not first_post:
        return None
    author_el = first_post.find("p", class_=re.compile(r"nick"))
    if not author_el:
        return None
    author_name = author_el.get_text(strip=True)

    # Search all posts by this author for "Обновлено до" pattern
    all_posts = soup.find_all("tbody", class_=re.compile(r"row[12]"))
    last_update_text = None
    last_post_url = None

    for post in all_posts:
        post_author = post.find("p", class_=re.compile(r"nick"))
        if not post_author or post_author.get_text(strip=True) != author_name:
            continue

        post_body_div = post.find("div", class_="post_body")
        if not post_body_div:
            continue

        post_text = post_body_div.get_text()
        # Find all "Обновлено до" entries
        updates = re.findall(r'Обновлено\s+до\s+[^\n]+', post_text)
        if updates:
            last_update_text = updates[-1].strip()
            # Get post URL
            post_link = post.find("a", class_="p-link small", href=re.compile(r'viewtopic\.php\?p='))
            if post_link:
                last_post_url = "https://rutracker.org/forum/" + post_link["href"]

    if last_update_text and last_post_url:
        logger.info(f"Found fallback update text: {last_update_text}")
        return f'<b>Обновлено:</b> <a href="{last_post_url}">Details</a>\n{html.escape(last_update_text)}'
    elif last_update_text:
        logger.info(f"Found fallback update text (no post link): {last_update_text}")
        return f'<b>Обновлено:</b> {html.escape(last_update_text)}'

    return None


# --- clean_description_html and make_tag moved to html_utils.py ---


# parse_tracker_entry remains the same (uses functions from html_utils)
async def parse_tracker_entry(entry_url: str, entry_title_from_feed: str) -> Optional[Tuple[str, str, Optional[str], str, str, str, str]]:
    soup = await fetch_page_content(entry_url)
    if not soup: return None

    page_display_title = "Unknown Title"
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text(); parts = title_text.split('::')
        if len(parts) > 1: page_display_title = parts[0].strip()
        else: page_display_title = title_text.replace('- Rutracker.org', '').strip()
    else:
        header_tag = soup.find('h1', id='topic-title');
        if header_tag: page_display_title = header_tag.get_text().strip()
    page_display_title = page_display_title.replace("[Nintendo Switch]", "").replace("[Обновлено]", "").replace("[Updated]", "").strip()

    # Extract torrent size and language
    torrent_size = "N/A"
    torrent_language = "N/A"

    try:
        # Find size in the download info section
        dl_list = soup.find("div", id="tor-size-humn")
        if dl_list:
            torrent_size = dl_list.get_text(strip=True)

        # Try alternative location for size
        if torrent_size == "N/A":
            size_span = soup.find("span", id="tor-size-humn")
            if size_span:
                torrent_size = size_span.get_text(strip=True)
    except Exception as e:
        logger.warning(f"Could not extract torrent size: {e}")

    # Find post body BEFORE trying to use it for language extraction
    post_body = soup.find("div", class_="post_body")
    if not post_body:
        logger.error(f"Could not find main post body in {entry_url}.")
        return None

    try:
        # Extract language from post body
        lang_patterns = [
            (r'Язык\s*(?:интерфейса)?[:\s]+([A-Za-zА-Яа-я,\s]+)', 'ru'),
            (r'Language[:\s]+([A-Za-z,\s]+)', 'en'),
            (r'Мова[:\s]+([A-Za-zА-Яа-я,\s]+)', 'ua')
        ]

        post_text = post_body.get_text()
        for pattern, _ in lang_patterns:
            match = re.search(pattern, post_text, re.IGNORECASE)
            if match:
                lang_text = match.group(1).strip()
                # Normalize common language codes
                lang_map = {
                    'английский': 'ENG', 'english': 'ENG', 'eng': 'ENG',
                    'русский': 'RUS', 'russian': 'RUS', 'rus': 'RUS',
                    'японский': 'JAP', 'japanese': 'JAP', 'jap': 'JAP',
                    'мультиязычный': 'MULTI', 'multi': 'MULTI', 'multilanguage': 'MULTI'
                }
                lang_lower = lang_text.lower()
                for key, value in lang_map.items():
                    if key in lang_lower:
                        torrent_language = value
                        break
                if torrent_language == "N/A":
                    torrent_language = lang_text.upper()[:10]
                break
    except Exception as e:
        logger.warning(f"Could not extract language: {e}")

    title_elements_html = []; description_elements_html = []; collecting_title = True
    description_start_keywords = ["Год выпуска", "Release year", "Жанр", "Genre", "Разработчик", "Developer", "Описание", "Description"]
    stop_title_collection_tags = ['hr', 'div', 'ol', 'ul']
    title_text_for_youtube = None

    for element in post_body.children:
        element_str = str(element); stop = False
        if collecting_title:
            if isinstance(element, Tag):
                if element.name in stop_title_collection_tags:
                    if (element.get('class') and ('sp-wrap' in element.get('class') or 'q-wrap' in element.get('class'))) \
                       or element.name == 'hr' or element.name in ['ol', 'ul']: stop = True
                elif element.name == 'b':
                     b_text = element.get_text(strip=True).replace(':', '')
                     if b_text in description_start_keywords: stop = True
                elif element.name == 'span' and element.find('br') and not element.find(text=True, recursive=False): stop = True
                elif element.name == 'img' and 'postImgAligned' in element.get('class', []): stop = True
            if stop: collecting_title = False; description_elements_html.append(element_str); continue
        if collecting_title:
             if not (isinstance(element, Tag) and element.name == 'img' and 'postImgAligned' in element.get('class', [])):
                  title_elements_html.append(element_str)
        else: description_elements_html.append(element_str)

    if title_elements_html:
        title_soup = BeautifulSoup("".join(title_elements_html), 'html.parser')
        for br in title_soup.find_all('br'): br.decompose()
        title_text_for_youtube = title_soup.get_text(separator=' ', strip=True)
        title_text_for_youtube = re.sub(r'\s+', ' ', title_text_for_youtube).strip()
    if not title_text_for_youtube or len(title_text_for_youtube) < 3:
        title_text_for_youtube = page_display_title

    cleaned_description = clean_description_html("".join(description_elements_html))

    is_updated = "[Обновлено]" in entry_title_from_feed or "[Updated]" in entry_title_from_feed
    last_post_text = None
    if is_updated:
        update_phrases = ["Раздача обновлена", "Distribution updated"]
        base_url = entry_url.split('&start=')[0]
        for phrase in update_phrases:
            last_post_text = await get_last_post_with_phrase(phrase, base_url)
            if last_post_text: break

        # Fallback: look for "Обновлено до" pattern in author's posts
        if not last_post_text:
            last_post_text = await get_update_from_author_post(soup, base_url)

    image_url: Optional[str] = None
    try:
        main_image = post_body.find("img", class_=re.compile(r"postImgAligned|img-right"), src=True)
        if main_image: image_url = main_image['src']
        else:
            image_tag_var = post_body.find("var", class_="postImg", title=True)
            if image_tag_var: image_url = image_tag_var["title"]
    except Exception as e: logger.warning(f"Warning: Error extracting image URL: {e}")

    magnet_link: Optional[str] = None
    try:
        magnet_tag = soup.find("a", class_="magnet-link", href=True)
        match = None
        if magnet_tag:
            full_magnet_link = magnet_tag["href"]
            match = re.search(r'(magnet:\?xt=urn:btih:[a-zA-Z0-9]+)', full_magnet_link)
        
        if match:
            magnet_link = match.group(1)
        
        if not magnet_link:
            magnet_tag_fallback = soup.find("a", href=re.compile(r'magnet:\?xt='))
            if magnet_tag_fallback:
                full_magnet_link = magnet_tag_fallback["href"]
                match = re.search(r'(magnet:\?xt=urn:btih:[a-zA-Z0-9]+)', full_magnet_link)
                if match:
                    magnet_link = match.group(1)
        
        if not magnet_link:
            logger.error("Error: Magnet link could not be extracted.")
            return None
    except Exception as e:
        logger.error(f"Error extracting magnet link: {e}")
        return None

    final_description = make_tag(cleaned_description, "Жанр")
    final_description = make_tag(final_description, "Genre")
    final_description = make_tag(final_description, "Год выпуска")
    final_description = make_tag(final_description, "Release year")
    if last_post_text: final_description += f"\n\n{last_post_text}"

    return page_display_title, title_text_for_youtube, image_url, magnet_link, final_description, torrent_size, torrent_language

# --- END OF FILE tracker_parser.py ---