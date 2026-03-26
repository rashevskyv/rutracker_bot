# --- START OF FILE html_utils.py ---
import re
import html
from bs4 import BeautifulSoup, NavigableString, Tag
from typing import Optional, List # Import Optional, List needed for clean_description_html

def sanitize_html_for_telegram(html_str: str) -> str:
    """
    Core function to sanitize HTML for Telegram's HTML parse mode.
    Removes disallowed tags, unwraps styling-only tags, and ensures proper formatting.
    """
    if not html_str: return ""
    # Pre-unescape to handle any pre-escaped entities from tracker or previous steps (prevents double-escaping)
    html_str = html.unescape(html_str)
    
    # Replace <br> tags with newlines before BeautifulSoup parsing to preserve line breaks
    html_str = re.sub(r'<(br|BR)\s*/?>', '\n', html_str)
    
    soup = BeautifulSoup(html_str, 'html.parser')
    
    # 1. Tags to completely remove (and their content)
    tags_to_remove = ['script', 'style', 'iframe', 'object', 'embed', 'var', 'img', 'hr']
    for tag_name in tags_to_remove:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 2. Unwrap spans and other structural tags that don't add value
    # Specifically Rutracker classes
    for tag in soup.find_all("span", class_="post-u"): tag.name = "u"; tag.attrs = {}
    for tag in soup.find_all("span", class_="post-i"): tag.name = "i"; tag.attrs = {}
    for tag in soup.find_all("span", class_="post-b"): tag.name = "b"; tag.attrs = {}
    for tag in soup.find_all("span", class_="post-strike"): tag.name = "s"; tag.attrs = {}
    
    # Generic unwrap for other spans or style-only tags
    for tag in soup.find_all('span'): tag.unwrap()
    
    # 3. Get the HTML content (this will escape text content properly)
    cleaned_html = soup.decode_contents()

    # 3.5. Replace any <br> tags that BeautifulSoup may have re-generated during decode
    cleaned_html = re.sub(r'<(br|BR)\s*/?>', '\n', cleaned_html)

    # 4. Final regex pass to ensure ONLY allowed tags remain
    # Telegram allowed tags: b, strong, i, em, u, ins, s, strike, del, a, code, pre, blockquote, tg-spoiler
    allowed_tags = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'code', 'pre', 'blockquote', 'tg-spoiler']
    
    # We use BeautifulSoup again to clean attributes and ensure tags are strictly what Telegram wants
    final_soup = BeautifulSoup(cleaned_html, 'html.parser')
    for tag in final_soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
        else:
            # Clean all attributes except 'href' for 'a' tags
            attrs = dict(tag.attrs)
            tag.attrs = {}
            if tag.name == 'a' and 'href' in attrs:
                tag.attrs['href'] = attrs['href']
            # For other tags, we keep them clean of attributes

    cleaned_html = final_soup.decode_contents()

    # 5. Normalize whitespace
    cleaned_html = cleaned_html.replace('\r', '')
    cleaned_html = re.sub(r'[ \t]+\n', '\n', cleaned_html)
    cleaned_html = re.sub(r'\n{2,}', '\n\n', cleaned_html) # Max 1 empty line
    # Remove gaps between list items
    cleaned_html = re.sub(r'\n{2,}(\s*(?:•|\d+\.) )', r'\n\1', cleaned_html)
    cleaned_html = cleaned_html.strip()
    
    return cleaned_html


def clean_description_html(description_html_str: str) -> str:
    if not description_html_str: return ""
    description_soup = BeautifulSoup(description_html_str, 'html.parser')
    
    # Sections (identified by class) to remove - Keep sp-head initially for spoiler titles
    sections_to_remove_classes = ['attach_wrap', 'attach_fu', 'signature'] 

    # Remove unwanted sections by class
    for class_name in sections_to_remove_classes:
        for section in description_soup.find_all(class_=class_name):
            section.decompose()

    # 1. Process links (a tags) FIRST so they are preserved inside spoilers and quotes
    for a in description_soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('viewtopic.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('tracker.php'): a['href'] = 'https://rutracker.org/forum/' + href
        elif href.startswith('magnet:'):
            magnet_text = html.escape(a.get_text(strip=True) or a['href'])
            a.name = 'code'
            a.string = magnet_text
            del a['href']
        else:
            # Keep the link text but also preserve spacing
            link_text = a.get_text() # No strip=True here to avoid joining words
            if not link_text or not link_text.strip():
                a.unwrap()
            else:
                a.string = link_text # BeautifulSoup will escape this

    # 2. Convert spoilers
    for target_spoiler in description_soup.find_all("div", class_="sp-wrap"):
        sp_head = target_spoiler.find("div", class_="sp-head")
        sp_body = target_spoiler.find("div", class_="sp-body")

        spoiler_title = "Spoiler"
        if sp_head:
            for unwanted in sp_head.find_all('span', class_='plusmn'): unwanted.decompose()
            spoiler_title = sp_head.get_text(strip=True).replace(':', '').strip() or spoiler_title

        # Check if spoiler title is 'Скриншоты' and skip if it is
        if "скриншот" in spoiler_title.lower():
            target_spoiler.decompose()
            continue

        blockquote = description_soup.new_tag("blockquote")
        
        # Title goes BEFORE the blockquote, not inside it
        b_title = description_soup.new_tag("b")
        b_title.string = f"{spoiler_title}:"
        # We'll insert title before blockquote after replacement

        if sp_body:
            # Code: c-wrap -> <code>
            for c_wrap in sp_body.find_all("div", class_="c-wrap"):
                c_head = c_wrap.find("div", class_="c-head")
                if c_head: c_head.decompose()
                c_body_tag = c_wrap.find("div", class_="c-body")
                if c_body_tag:
                    code_tag = description_soup.new_tag("code")
                    code_tag.string = c_body_tag.get_text(strip=True)
                    c_wrap.replace_with(code_tag)
                else:
                    c_wrap.decompose()

            # Nested quotes -> unwrap
            for q_wrap in sp_body.find_all("div", class_="q-wrap"):
                q_head = q_wrap.find("div", class_="q-head")
                if q_head: q_head.decompose()
                q = q_wrap.find("div", class_="q")
                if q: q.unwrap()
                q_wrap.unwrap()

            # p -> \n
            for p in sp_body.find_all("p"):
                p.append(description_soup.new_string("\n"))
                p.unwrap()

            # hr -> \n
            for hr in sp_body.find_all("hr"):
                hr.replace_with(description_soup.new_string("\n"))

            # br -> \n
            for br in sp_body.find_all(["br", "span"], class_="post-br"):
                br.replace_with(description_soup.new_string("\n"))

            for child in list(sp_body.children):
                blockquote.append(child)

        # Insert: \n\n + <b>Title:</b>\n + <blockquote> (title outside the quote)
        title_with_newlines = description_soup.new_string(f"\n\n")
        target_spoiler.replace_with(title_with_newlines)
        title_with_newlines.insert_after(b_title)
        b_title.insert_after(description_soup.new_string("\n"))
        b_title.next_sibling.insert_after(blockquote)


    # Handle code blocks
    for c_wrap in description_soup.find_all("div", class_="c-wrap"):
        c_body = c_wrap.find("div", class_="c-body")
        if c_body:
            # Use get_text to avoid any stray HTML tags inside
            content = html.escape(c_body.get_text(separator=' ', strip=True))
        else:
            content = ""
        # Output content without 'Код:' prefix and without <code> tags
        replacement = NavigableString(f"\n{content}\n") if content else NavigableString("")
        c_wrap.replace_with(replacement)

    # 3. Convert quotes and format their content exactly like spoilers
    for quote in description_soup.find_all("div", class_="q-wrap"):
        q_head = quote.find("div", class_="q-head")
        q_body = quote.find("div", class_="q")
        
        blockquote = description_soup.new_tag("blockquote")
        
        title_text = ""
        if q_head:
            # Extract title and remove 'писал(а):'
            title_text = q_head.get_text(strip=True)
            title_text = re.sub(r'(?i)\s*писал\(а\):?', '', title_text).strip()
            q_head.decompose()
            
        if title_text:
            b_title = description_soup.new_tag("b")
            b_title.string = f"{title_text}:"
            # Title will be inserted before blockquote below
            
        if q_body:
            # Code: c-wrap -> <code>
            for c_wrap in q_body.find_all("div", class_="c-wrap"):
                c_head_inner = c_wrap.find("div", class_="c-head")
                if c_head_inner: c_head_inner.decompose()
                c_body_inner = c_wrap.find("div", class_="c-body")
                if c_body_inner:
                    code_tag = description_soup.new_tag("code")
                    code_tag.string = c_body_inner.get_text(strip=True)
                    c_wrap.replace_with(code_tag)
                else:
                    c_wrap.decompose()

            # Nested quotes -> unwrap
            for sq in q_body.find_all("div", class_="q-wrap"):
                sq_head = sq.find("div", class_="q-head")
                if sq_head: sq_head.decompose()
                sq_q = sq.find("div", class_="q")
                if sq_q: sq_q.unwrap()
                sq.unwrap()

            # p -> \n
            for p in q_body.find_all("p"):
                p.append(description_soup.new_string("\n"))
                p.unwrap()

            # hr -> \n
            for hr in q_body.find_all("hr"):
                hr.replace_with(description_soup.new_string("\n"))

            # br -> \n
            for br in q_body.find_all(["br", "span"], class_="post-br"):
                br.replace_with(description_soup.new_string("\n"))

            for child in list(q_body.children):
                blockquote.append(child)

        if title_text:
            # Insert: \n\n + <b>Title:</b>\n + <blockquote> (title outside quote)
            title_newline = description_soup.new_string("\n\n")
            quote.replace_with(title_newline)
            title_newline.insert_after(b_title)
            b_title.insert_after(description_soup.new_string("\n"))
            b_title.next_sibling.insert_after(blockquote)
        else:
            quote.replace_with(blockquote)

    # Replace horizontal rules with structural gaps
    for hr in description_soup.find_all("hr"):
        hr.replace_with(NavigableString("###GAP###"))

    # Handle preformatted text
    for tag in description_soup.find_all("pre", class_="post-pre"):
        pre_content = tag.get_text()
        tag.name = "pre"
        tag.string = html.escape(pre_content)
        tag.attrs = {}

    # Handle lists: Convert <li> to bullets using Tag-based insertion to preserve inner HTML
    for ul in description_soup.find_all(["ul", "ol"]):
        # User requested dots for all lists
        for i, li in enumerate(ul.find_all("li", recursive=False), 1):
            prefix = "\n• "
            bullet_prefix = NavigableString(prefix)
            li.insert_before(bullet_prefix)
            li.unwrap()  # Remove <li> wrapper but keep its children in place
        ul.unwrap()  # Remove <ul>/<ol> container

    # Replace <br> and specific span breaks with newlines
    for br_like in description_soup.find_all(['br', 'span'], class_="post-br"): br_like.replace_with('\n')

    # Get the processed HTML content
    intermediate_html = description_soup.decode_contents()

    # Use the shared sanitizer for final cleanup
    cleaned_html = sanitize_html_for_telegram(intermediate_html)

    return cleaned_html


def convert_markdown_to_html(text: str) -> str:
    """
    Simpler converter that handles common Markdown bold/italic patterns
    that might be returned by AI or exist in text, and converts them to HTML.
    Does NOT handle complex nesting well, but is safe for simple bold/italic/code.
    """
    if not text:
        return ""

    # 1. Bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # 2. Italic: *text* -> <i>text</i> (Careful with existing underscore-based markers if needed)
    # We only handle *asterisks* to avoid breaking underscores in links/names
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    # 3. Inline code: `text` -> <code>text</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    return text


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