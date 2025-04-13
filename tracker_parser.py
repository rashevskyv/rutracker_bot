# --- START OF FILE tracker_parser.py ---
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import re
import time
import html # Import html for escaping
from settings_loader import LOG # Use the refactored settings module
from typing import Optional, Tuple, List # Import Optional, Tuple, List
# --- Import functions moved to html_utils ---
from html_utils import clean_description_html, make_tag
# --------------------------------------------

# fetch_page_content remains the same
def fetch_page_content(url: str, retries: int = 3, delay: int = 5) -> Optional[BeautifulSoup]:
    headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=25); response.raise_for_status()
            if 'text/html' not in response.headers.get('Content-Type', ''): pass
            soup = BeautifulSoup(response.content, "html.parser"); return soup
        except requests.exceptions.Timeout: print(f"Timeout fetching {url} (Attempt {attempt + 1}/{retries})")
        except requests.exceptions.HTTPError as e:
             print(f"HTTP Error fetching {url}: {e.response.status_code}");
             if e.response.status_code == 404: return None
             if 400 <= e.response.status_code < 500 and e.response.status_code != 429: return None
        except requests.exceptions.RequestException as e: print(f"Network-related error fetching {url}: {e}")
        except Exception as e: print(f"An unexpected error occurred fetching {url}: {e}"); break
        if attempt < retries - 1: time.sleep(delay)
        else: print(f"Failed to fetch {url} after {retries} attempts."); return None

# get_last_post_with_phrase remains the same
def get_last_post_with_phrase(phrase: str, base_url: str, max_pages_to_check: int = 5) -> Optional[str]:
    if LOG: print(f"Searching for update phrase '{phrase}'...")
    posts_per_page = 30; last_page_offset = -1
    soup_first_page = fetch_page_content(base_url)
    if soup_first_page:
        last_page_link = soup_first_page.find('a', class_='pg', string='Last')
        match = None
        if last_page_link and 'href' in last_page_link.attrs: match = re.search(r'start=(\d+)', last_page_link['href'])
        if match: last_page_offset = int(match.group(1))
        if last_page_offset == -1:
             page_links = soup_first_page.select('a.pg:not([rel="prev"]):not([rel="next"])'); highest_offset = 0
             for link in page_links: match = re.search(r'start=(\d+)', link.get('href', ''));
             if match: highest_offset = max(highest_offset, int(match.group(1)))
             if highest_offset > 0: last_page_offset = highest_offset
    if last_page_offset == -1: last_page_offset = max(0, (max_pages_to_check - 1) * posts_per_page)
    checked_urls = set()
    for i in range(max_pages_to_check):
        current_offset = max(0, last_page_offset - (i * posts_per_page)); page_url = f"{base_url}&start={current_offset}"
        if page_url in checked_urls: continue; checked_urls.add(page_url)
        soup = fetch_page_content(page_url)
        if not soup:
            if current_offset == 0: break; continue
        user_posts = soup.find_all("tbody", class_=re.compile(r"row[12]"))
        if not user_posts: continue
        for post in reversed(user_posts):
            post_body_div = post.find("div", class_="post_body")
            if not post_body_div: continue
            for br in post_body_div.find_all("br"): br.replace_with("\n")
            post_text_content = post_body_div.get_text(separator=" ", strip=True) # Check text content first
            if phrase in post_text_content:
                if LOG: print(f"Found update phrase '{phrase}' in post on {page_url}")
                relevant_html_content = ""; found_phrase = False; stop_collecting = False
                for element in post_body_div.children:
                    element_str = str(element)
                    # --- FIX STARTS HERE ---
                    if phrase in element_str:
                        found_phrase = True
                        parts = element_str.split(phrase, 1) # parts is defined HERE
                        # Check len(parts) immediately after creation
                        if len(parts) > 1:
                            relevant_html_content += parts[1]
                        continue # Move to next element after finding the phrase in this one
                    # --- FIX ENDS HERE ---

                    if found_phrase and not stop_collecting:
                        is_stop_marker = False
                        if isinstance(element, Tag):
                             if element.name == 'hr' or \
                               (element.get('class') and ('sp-wrap' in element.get('class') or 'q-wrap' in element.get('class'))) or \
                               (element.name == 'span' and element.get('class') and 'post-br' in element.get('class')): is_stop_marker = True
                        if is_stop_marker: stop_collecting = True
                        else: relevant_html_content += element_str

                # Check if anything was collected after the phrase was found
                if not found_phrase: continue # Should not happen if text check passed, but safety

                update_text_html = relevant_html_content.strip()
                post_link_tag = post.find("a", class_="p-link small", href=re.compile(r'viewtopic\.php\?p='))
                post_url = ("https://rutracker.org/forum/" + post_link_tag["href"]) if post_link_tag else base_url
                update_soup = BeautifulSoup(update_text_html, 'html.parser')
                for tag in update_soup.find_all("span", class_="post-u"): tag.name = "u"; tag.attrs = {}
                for tag in update_soup.find_all("span", class_="post-i"): tag.name = "i"; tag.attrs = {}
                for tag in update_soup.find_all("span", class_="post-b"): tag.name = "b"; tag.attrs = {}
                for span in update_soup.find_all('span'): span.unwrap()
                cleaned_update_text = update_soup.decode_contents(); cleaned_update_text = re.sub(r'\s+', ' ', cleaned_update_text).strip()
                update_keyword = "Details";
                if "внесённые изменения" in cleaned_update_text:
                     word = "внесённые изменения"; link_html = f'<a href="{post_url}">{word}</a>'
                     # Check if word actually exists before replacing
                     if word in cleaned_update_text:
                          return f"<b>Обновлено:</b> {cleaned_update_text.replace(word, link_html, 1)}"
                # Return even if cleaned_update_text is empty, but with link
                return f'<b>Обновлено:</b> <a href="{post_url}">{update_keyword}</a>\n{cleaned_update_text}'
        if current_offset == 0: break # Exit loop if first page checked
    return None # Return None if phrase not found after checking pages


# --- clean_description_html and make_tag moved to html_utils.py ---


# parse_tracker_entry remains the same (uses functions from html_utils)
def parse_tracker_entry(entry_url: str, entry_title_from_feed: str) -> Optional[Tuple[str, str, Optional[str], str, str]]:
    soup = fetch_page_content(entry_url)
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

    post_body = soup.find("div", class_="post_body")
    if not post_body: print(f"Could not find main post body in {entry_url}."); return None

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

    # Use the imported cleaning function
    cleaned_description = clean_description_html("".join(description_elements_html))

    is_updated = "[Обновлено]" in entry_title_from_feed or "[Updated]" in entry_title_from_feed
    last_post_text = None
    if is_updated:
        update_phrases = ["Раздача обновлена", "Distribution updated"]
        base_url = entry_url.split('&start=')[0]
        for phrase in update_phrases:
            last_post_text = get_last_post_with_phrase(phrase, base_url)
            if last_post_text: break

    image_url: Optional[str] = None
    try:
        main_image = post_body.find("img", class_=re.compile(r"postImgAligned|img-right"), src=True)
        if main_image: image_url = main_image['src']
        else:
            image_tag_var = post_body.find("var", class_="postImg", title=True)
            if image_tag_var: image_url = image_tag_var["title"]
    except Exception as e: print(f"Warning: Error extracting image URL: {e}")

    magnet_link: Optional[str] = None
    try:
        magnet_tag = soup.find("a", class_="magnet-link", href=True); match = None
        if magnet_tag: full_magnet_link = magnet_tag["href"]; match = re.search(r'(magnet:\?xt=urn:btih:[a-zA-Z0-9]+)', full_magnet_link)
        if match: magnet_link = match.group(1)
        if not magnet_link:
            magnet_tag_fallback = soup.find("a", href=re.compile(r'magnet:\?xt='));
            if magnet_tag_fallback: full_magnet_link = magnet_tag_fallback["href"]; match = re.search(r'(magnet:\?xt=urn:btih:[a-zA-Z0-9]+)', full_magnet_link)
            if match: magnet_link = match.group(1)
        if not magnet_link: print("Error: Magnet link could not be extracted."); return None
    except Exception as e: print(f"Error extracting magnet link: {e}"); return None

    # Use the imported tagging function
    final_description = make_tag(cleaned_description, "Жанр")
    final_description = make_tag(final_description, "Genre")
    final_description = make_tag(final_description, "Год выпуска")
    final_description = make_tag(final_description, "Release year")
    if last_post_text: final_description += f"\n\n{last_post_text}"

    # Return: Title for display, Title for YT, Image, Magnet, Description
    return page_display_title, title_text_for_youtube, image_url, magnet_link, final_description

# --- END OF FILE tracker_parser.py ---