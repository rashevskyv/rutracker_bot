# --- START OF FILE html_utils.py ---
import re
import html
from bs4 import BeautifulSoup, NavigableString, Tag
from typing import Optional, List # Import Optional, List needed for clean_description_html

def clean_description_html(description_html_str: str) -> str:
    """
    Cleans and formats HTML string from tracker description for Telegram.
    Removes unwanted tags, converts spoilers/quotes, formats lists, handles links, etc.
    """
    if not description_html_str: return ""
    description_soup = BeautifulSoup(description_html_str, 'html.parser')
    # Tags to completely remove
    tags_to_remove = ['script', 'style', 'iframe', 'object', 'embed', 'var', 'img', 'hr'] # Added 'hr' here
    # Sections (identified by class) to remove - Keep sp-head initially for spoiler titles
    sections_to_remove_classes = ['attach_wrap', 'attach_fu', 'signature', 'q-head'] # Removed 'sp-head' here

    # Remove unwanted tags
    for tag_name in tags_to_remove:
        for tag in description_soup.find_all(tag_name):
            tag.decompose() # Use decompose to remove the tag and its content

    # Remove unwanted sections by class
    for class_name in sections_to_remove_classes:
        for section in description_soup.find_all(class_=class_name):
            section.decompose()

    # Convert spoilers
    for spoiler in description_soup.find_all("div", class_="sp-wrap"):
        sp_head = spoiler.find("div", class_="sp-head")
        sp_body = spoiler.find("div", class_="sp-body")

        # Get spoiler title
        spoiler_title = "Spoiler" # Default title
        if sp_head:
            for unwanted in sp_head.find_all('span', class_='plusmn'): unwanted.decompose()
            spoiler_title = sp_head.get_text(strip=True).replace(':', '').strip() or spoiler_title

        # Check if spoiler title is 'Скриншоты' and skip if it is
        if spoiler_title.lower() == "скриншоты":
            spoiler.decompose() # Remove the entire spoiler div
            continue # Move to the next spoiler

        # Process spoiler body content preserving structure
        spoiler_content_processed = ""
        if sp_body:
            for br in sp_body.find_all('br'): br.replace_with('\n')
            lines = [line.strip() for line in sp_body.get_text(separator='\n').splitlines() if line.strip()]
            spoiler_content_processed = html.escape("\n".join(lines))
        elif sp_head:
             spoiler_content_processed = ""

        # Replace spoiler div with title and its content directly
        spoiler_replacement = f"\n<b>{html.escape(spoiler_title)}:</b>\n{spoiler_content_processed}\n"
        spoiler.replace_with(NavigableString(spoiler_replacement))


    # Convert quotes
    for quote in description_soup.find_all("div", class_="q-wrap"):
        q_body = quote.find("div", class_="q")
        content = q_body.get_text(strip=True) if q_body else "Quoted Text"
        quote.replace_with(NavigableString(f"\n> {html.escape(content)}\n"))

    # Convert specific span classes to basic HTML tags
    for tag in description_soup.find_all("span", class_="post-u"): tag.name = "u"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-i"): tag.name = "i"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-b"): tag.name = "b"; tag.attrs = {}
    for tag in description_soup.find_all("span", class_="post-strike"): tag.name = "s"; tag.attrs = {}

    # Handle preformatted text
    for tag in description_soup.find_all("pre", class_="post-pre"):
        pre_content = tag.get_text()
        tag.name = "pre"
        tag.string = html.escape(pre_content)
        tag.attrs = {}

    # Unwrap spans used purely for styling (color, size, inline styles)
    spans_to_unwrap = description_soup.find_all('span', {'class': lambda x: x and ('post-color' in x or 'post-size' in x)})
    spans_to_unwrap.extend(description_soup.find_all('span', style=True))
    for tag in spans_to_unwrap: tag.unwrap()

    # Format lists (ul, ol)
    for ul in description_soup.find_all(['ul', 'ol']):
        list_items = []
        is_ordered = ul.name == 'ol'
        i = 1
        for li in ul.find_all('li', recursive=False):
            prefix = f"{i}. " if is_ordered else "• "
            for br in li.find_all('br'): br.replace_with("\n" + " " * len(prefix))
            li_text = html.escape(li.get_text(separator=' ', strip=True))
            list_items.append(f"{prefix}{li_text}")
            if is_ordered: i += 1
        ul.replace_with(NavigableString("\n" + "\n".join(list_items) + "\n"))

    # Process links (a tags)
    for a in description_soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('viewtopic.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('tracker.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('magnet:'):
            magnet_text = html.escape(a.get_text(strip=True) or a['href']) # Escape content
            a.name = 'code'
            a.string = magnet_text
            del a['href']
        else:
            link_text = html.escape(a.get_text(strip=True)) # Escape content
            if not link_text: a.unwrap()
            else: a.string = link_text

    # --- FIX: Remove horizontal rules processing loop ---
    # The 'hr' tag is now removed by the initial decompose loop
    # for hr in description_soup.find_all('hr'):
    #     hr.replace_with('\n---\n') # Removed this line
    # --- END FIX ---

    # Replace <br> and specific span breaks with newlines (after list processing)
    for br_like in description_soup.find_all(['br', 'span'], class_="post-br"): br_like.replace_with('\n')

    # Get the processed HTML content
    cleaned_html = description_soup.decode_contents()

    # Final cleanup pass: Remove disallowed tags
    allowed_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'blockquote']
    def strip_tags(match):
        tag = match.group(1).lower()
        return match.group(0) if tag in allowed_tags else ''
    cleaned_html = re.sub(r'</?([a-zA-Z0-9]+)[^>]*>', strip_tags, cleaned_html)

    # Normalize whitespace and remove extra newlines
    cleaned_html = cleaned_html.replace('\r', '')
    cleaned_html = re.sub(r'[ \t]+\n', '\n', cleaned_html)
    cleaned_html = re.sub(r'\n{3,}', '\n\n', cleaned_html) # Keep collapsing multiple newlines
    cleaned_html = re.sub(r' +', ' ', cleaned_html).strip()
    cleaned_html = cleaned_html.replace(" :", ":")

    # Unescape entities *once* at the very end
    cleaned_html = html.unescape(cleaned_html)

    return cleaned_html


# make_tag remains the same
def make_tag(description: str, keyword: str) -> str:
    """
    Finds a keyword line (like 'Genre: ...' or 'Год выпуска: ...')
    and converts the items after the keyword into clickable hashtags.
    Modifies the description string in place (conceptually).
    """
    tag_header_pattern = re.compile(
        r"<b>" + re.escape(keyword) + r"</b>\s*:\s*(.*?)\s*(\n|<br|$)",
        re.IGNORECASE | re.DOTALL
    )
    match = tag_header_pattern.search(description)

    if match:
        line_after_header = match.group(1).strip() # The content (e.g., "Action, RPG")
        placeholder = "@@COMMA@@"
        temp_line = re.sub(r'<[^>]+>', lambda m: m.group(0).replace(',', placeholder), line_after_header)
        items = [item.replace(placeholder, ',').strip() for item in temp_line.split(',')]
        formatted_tags = []
        for item in items:
            if not item: continue
            item_soup = BeautifulSoup(item, 'html.parser')
            tag_text = item_soup.get_text(strip=True)
            clean_tag_text = re.sub(r'\W+', '', tag_text)
            if not clean_tag_text: continue
            link_tag = item_soup.find('a')
            if link_tag:
                link_href = link_tag.get('href', '#')
                link_text_escaped = html.escape(tag_text)
                formatted_tag = f" #{clean_tag_text} (<a href=\"{link_href}\">{link_text_escaped}</a>)"
            else:
                formatted_tag = f" #{clean_tag_text}"
            formatted_tags.append(formatted_tag)

        if formatted_tags:
            formatted_line = ", ".join(formatted_tags)
            start_index = match.start(1)
            end_index = match.end(1)
            description = description[:start_index] + formatted_line + description[end_index:]

    return description
# --- END OF FILE html_utils.py ---