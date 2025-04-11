import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import re
import time
import html # Import html for escaping
from settings_loader import LOG # Use the refactored settings module
from typing import Optional, Tuple, List # Import Optional, Tuple, List

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
            post_text_content = post_body_div.get_text(separator=" ", strip=True)
            if phrase in post_text_content:
                if LOG: print(f"Found update phrase '{phrase}' in post on {page_url}")
                relevant_html_content = ""; found_phrase = False; stop_collecting = False
                for element in post_body_div.children:
                    element_str = str(element)
                    if phrase in element_str: found_phrase = True; parts = element_str.split(phrase, 1);
                    if len(parts) > 1: relevant_html_content += parts[1]; continue
                    if found_phrase and not stop_collecting:
                        is_stop_marker = False
                        if isinstance(element, Tag):
                             if element.name == 'hr' or \
                               (element.get('class') and ('sp-wrap' in element.get('class') or 'q-wrap' in element.get('class'))) or \
                               (element.name == 'span' and element.get('class') and 'post-br' in element.get('class')): is_stop_marker = True
                        if is_stop_marker: stop_collecting = True
                        else: relevant_html_content += element_str
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
                     if word in cleaned_update_text: return f"<b>Updated:</b> {cleaned_update_text.replace(word, link_html, 1)}"
                return f'<b>Updated:</b> <a href="{post_url}">{update_keyword}</a>\n{cleaned_update_text}'
        if current_offset == 0: break
    return None

# clean_description_html remains the same
def clean_description_html(description_html_str: str) -> str:
    if not description_html_str: return ""
    description_soup = BeautifulSoup(description_html_str, 'html.parser')
    tags_to_remove = ['script', 'style', 'iframe', 'object', 'embed', 'var', 'img']
    sections_to_remove_classes = ['attach_wrap', 'attach_fu', 'signature', 'sp-head', 'q-head']
    for tag_name in tags_to_remove:
        for tag in description_soup.find_all(tag_name): tag.decompose()
    for class_name in sections_to_remove_classes:
        for section in description_soup.find_all(class_=class_name): section.decompose()
    for spoiler in description_soup.find_all("div", class_="sp-wrap"):
        sp_body = spoiler.find("div", class_="sp-body"); content = sp_body.get_text(strip=True) if sp_body else "Spoiler Content"
        spoiler.replace_with(NavigableString(f"\n<tg-spoiler>{html.escape(content)}</tg-spoiler>\n"))
    for quote in description_soup.find_all("div", class_="q-wrap"):
        q_body = quote.find("div", class_="q"); content = q_body.get_text(strip=True) if q_body else "Quoted Text"
        quote.replace_with(NavigableString(f"\n> {html.escape(content)}\n"))
    for tag in description_soup.find_all("span", class_="post-u"): tag.name = "u"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-i"): tag.name = "i"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-b"): tag.name = "b"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-strike"): tag.name = "s"; tag.attrs = {}
    for tag in description_soup.find_all("pre", class_="post-pre"):
         pre_content = tag.get_text(); tag.name = "pre"; tag.string = html.escape(pre_content); tag.attrs = {}
    spans_to_unwrap = description_soup.find_all('span', {'class': lambda x: x and ('post-color' in x or 'post-size' in x)})
    spans_to_unwrap.extend(description_soup.find_all('span', style=True))
    for tag in spans_to_unwrap: tag.unwrap()
    for ul in description_soup.find_all(['ul', 'ol']):
        list_items = []; is_ordered = ul.name == 'ol'; i = 1
        for li in ul.find_all('li', recursive=False):
            prefix = f"{i}. " if is_ordered else "• "
            for br in li.find_all('br'): br.replace_with("\n" + " " * len(prefix))
            li_text = li.get_text(separator=' ', strip=True); list_items.append(f"{prefix}{li_text}")
            if is_ordered: i += 1
        ul.replace_with(NavigableString("\n" + "\n".join(list_items) + "\n"))
    for a in description_soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('viewtopic.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('tracker.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('magnet:'):
             magnet_text = a.get_text(strip=True) or a['href']; a.name = 'code'; a.string = magnet_text; del a['href']
        else:
             link_text = a.get_text(strip=True);
             if not link_text: a.unwrap()
             else: a.string = link_text
    for hr in description_soup.find_all('hr'): hr.replace_with('\n---\n')
    for br_like in description_soup.find_all(['br', 'span'], class_="post-br"): br_like.replace_with('\n')
    cleaned_html = description_soup.decode_contents()
    allowed_tags = ['b', 'i', 'u', 's', 'tg-spoiler', 'a', 'code', 'pre', 'blockquote']
    def strip_tags(match): tag = match.group(1).lower(); return match.group(0) if tag in allowed_tags else ''
    cleaned_html = re.sub(r'</?([a-zA-Z0-9]+)[^>]*>', strip_tags, cleaned_html)
    cleaned_html = cleaned_html.replace('\r', ''); cleaned_html = re.sub(r'[ \t]+\n', '\n', cleaned_html)
    cleaned_html = re.sub(r'\n{3,}', '\n\n', cleaned_html); cleaned_html = re.sub(r' +', ' ', cleaned_html).strip()
    cleaned_html = cleaned_html.replace(" :", ":"); cleaned_html = html.unescape(cleaned_html)
    return cleaned_html

# make_tag remains the same
def make_tag(description: str, keyword: str) -> str:
    tag_header_pattern = re.compile(r"<b>" + re.escape(keyword) + r"</b>\s*:\s*(.*?)\s*(\n|<br|$)", re.IGNORECASE | re.DOTALL)
    match = tag_header_pattern.search(description)
    if match:
        line_after_header = match.group(1).strip(); placeholder = "@@COMMA@@"
        temp_line = re.sub(r'<[^>]+>', lambda m: m.group(0).replace(',', placeholder), line_after_header)
        items = [item.replace(placeholder, ',').strip() for item in temp_line.split(',')]
        formatted_tags = []
        for item in items:
            if not item: continue
            item_soup = BeautifulSoup(item, 'html.parser'); tag_text = item_soup.get_text(strip=True)
            clean_tag_text = re.sub(r'\W+', '', tag_text);
            if not clean_tag_text: continue
            link_tag = item_soup.find('a')
            if link_tag: link_href = link_tag.get('href', '#'); formatted_tag = f" #{clean_tag_text} (<a href=\"{link_href}\">more...</a>)"
            else: formatted_tag = f" #{clean_tag_text}"
            formatted_tags.append(formatted_tag)
        if formatted_tags:
            formatted_line = ", ".join(formatted_tags); start_index = match.start(1); end_index = match.end(1)
            description = description[:start_index] + formatted_line + description[end_index:]
    return description


def parse_tracker_entry(entry_url: str, entry_title_from_feed: str) -> Optional[Tuple[str, str, Optional[str], str, str]]:
    """
    Parses a single RuTracker entry page. Separates initial title text (for YT search)
    from the display title (from <title> tag) and the main description.

    Returns:
        A tuple containing:
        (page_display_title, title_text_for_youtube, image_url, magnet_link, cleaned_description)
        Returns None if essential parsing fails.
    """
    soup = fetch_page_content(entry_url)
    if not soup: return None

    # --- Extract Page Display Title ---
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

    # --- Find Post Body ---
    post_body = soup.find("div", class_="post_body")
    if not post_body: print(f"Could not find main post body in {entry_url}."); return None

    # --- Separate Title Block (for YT search) from Description Block ---
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

    # --- Process Title Block (for YT search) ---
    if title_elements_html:
        title_soup = BeautifulSoup("".join(title_elements_html), 'html.parser')
        for br in title_soup.find_all('br'): br.decompose()
        title_text_for_youtube = title_soup.get_text(separator=' ', strip=True)
        title_text_for_youtube = re.sub(r'\s+', ' ', title_text_for_youtube).strip()
    if not title_text_for_youtube or len(title_text_for_youtube) < 3:
        title_text_for_youtube = page_display_title # Fallback

    # --- Clean Description Block ---
    cleaned_description = clean_description_html("".join(description_elements_html))

    # --- Check for Updates ---
    is_updated = "[Обновлено]" in entry_title_from_feed or "[Updated]" in entry_title_from_feed
    last_post_text = None
    if is_updated:
        update_phrases = ["Раздача обновлена", "Distribution updated"]
        base_url = entry_url.split('&start=')[0]
        for phrase in update_phrases:
            last_post_text = get_last_post_with_phrase(phrase, base_url)
            if last_post_text: break

    # --- Extract Image ---
    image_url: Optional[str] = None
    try:
        main_image = post_body.find("img", class_=re.compile(r"postImgAligned|img-right"), src=True)
        if main_image: image_url = main_image['src']
        else:
            image_tag_var = post_body.find("var", class_="postImg", title=True)
            if image_tag_var: image_url = image_tag_var["title"]
    except Exception as e: print(f"Warning: Error extracting image URL: {e}")

    # --- Extract Magnet Link ---
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

    # --- Apply Tags and Updates ---
    final_description = make_tag(cleaned_description, "Жанр")
    final_description = make_tag(final_description, "Genre")
    final_description = make_tag(final_description, "Год выпуска")
    final_description = make_tag(final_description, "Release year")
    if last_post_text: final_description += f"\n\n{last_post_text}"

    # --- CORRECTED RETURN STATEMENT ---
    # Return: Title for display, Title for YT, Image, Magnet, Description
    return page_display_title, title_text_for_youtube, image_url, magnet_link, final_description
