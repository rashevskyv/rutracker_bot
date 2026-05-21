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

    # 3. Filter to Telegram-allowed tags only and clean attributes (single pass)
    # Telegram allowed tags: b, strong, i, em, u, ins, s, strike, del, a, code, pre, blockquote, tg-spoiler
    allowed_tags = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'code', 'pre', 'blockquote', 'tg-spoiler'}
    
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
        else:
            # Clean all attributes except 'href' for 'a' tags
            if tag.name == 'a':
                href = tag.attrs.get('href')
                tag.attrs = {'href': href} if href else {}
            else:
                tag.attrs = {}

    # 4. Serialize to string
    cleaned_html = soup.decode_contents()
    
    # Replace any <br> tags that BeautifulSoup may have re-generated during decode
    cleaned_html = re.sub(r'<(br|BR)\s*/?>', '\n', cleaned_html)

    # 5. Normalize whitespace
    cleaned_html = cleaned_html.replace('\r', '')
    
    # Ensure all colons are absolutely glued to the preceding word/tag (no space before colon, never detached)
    # Move trailing spaces out of bold/strong tags first to clean the boundaries
    cleaned_html = re.sub(r'([\s\u200b\xa0]+)(</(?:b|strong)>)', r'\2\1', cleaned_html)
    
    # Glue colon inside bold/strong tags and push trailing spaces out: <b>Word : </b> -> <b>Word:</b> 
    cleaned_html = re.sub(r'<(b|strong)>([^:<]+?)(?:[\s\u200b\xa0]*:[\s\u200b\xa0]*)</\1>', r'<\1>\2:</\1> ', cleaned_html)
    
    # Clean spaces/newlines before colons outside/after tags: <b>Word</b>  : -> <b>Word</b>:
    cleaned_html = re.sub(r'(</(?:b|strong|i|em|u|ins|code|a)>)[\s\u200b\xa0\n]*:', r'\1:', cleaned_html)
    
    # Clean spaces/newlines before colons in plain words (except inside URL protocols or magnet links):
    cleaned_html = re.sub(r'(?<!http)(?<!https)(?<!magnet)(\w)[\s\u200b\xa0\n]*:', r'\1:', cleaned_html)
    
    # Snap any orphaned colon at the start of a line back to the end of the previous line (attached)
    cleaned_html = re.sub(r'\n+\s*:', ':', cleaned_html)
    
    # Ensure exactly one space after a colon if it is followed by non-newline text (ignoring HTML tag brackets to prevent breaking snap)
    cleaned_html = re.sub(r':(?=[^\s\n<])', ': ', cleaned_html)
    
    # Collapse multiple spaces/tabs after a colon into a single space
    cleaned_html = re.sub(r':[ \t\u200b\xa0]{2,}', ': ', cleaned_html)

    # Convert horizontal bullet lists to properly separated vertical lists (e.g. "Item 1 • Item 2" -> "Item 1\n• Item 2")
    # We look for a bullet preceded by spaces that follows some text on the SAME line.
    cleaned_html = re.sub(r'(?<=\S)[ \t]+•[ \t]*', '\n• ', cleaned_html)
    
    # Fix orphaned bullets that have nothing on their line or are followed by newlines
    # (e.g. "• \n\n<b>Описание</b>" -> "• <b>Описание</b>")
    cleaned_html = re.sub(r'•[ \t]*\n+', '• ', cleaned_html)

    # Remove trailing bullet if it's completely empty at the end of the text
    cleaned_html = re.sub(r'\n•\s*$', '', cleaned_html)

    # Remove standalone exclamation marks or punctuation on empty lines (often left over from image stripping)
    cleaned_html = re.sub(r'\n\s*[!.,?;:-]\s*\n', '\n', cleaned_html)

    cleaned_html = re.sub(r'[ \t]+\n', '\n', cleaned_html)
    cleaned_html = re.sub(r'\n{2,}', '\n\n', cleaned_html) # Max 1 empty line
    # Remove gaps between list items
    cleaned_html = re.sub(r'\n{2,}(\s*(?:•|\d+\.) )', r'\n\1', cleaned_html)
    
    def classify_header(header_text: str) -> str:
        # Remove HTML tags and colons, lowercase, and clean extra punctuation/spaces
        clean = re.sub(r'<[^>]+>', '', header_text)
        clean = clean.replace(':', '').strip().lower()
        clean = re.sub(r'\s+', ' ', clean)
        
        sections = {
            'особенности', 'особливості', 'features',
            'системные требования', 'системні вимоги', 'system requirements',
            'системные', 'системні',
            'доп информация', 'додаткова інформація', 'additional info', 'доп. інформація', 'доп. информация',
            'доп', 'додаткова', 'additional',
            'скриншоты', 'screenshots',
            'скачать', 'download'
        }
        
        inline_with_gap = {
            'описание', 'опис', 'description',
            'обновлено', 'оновлено', 'updated'
        }
        
        if clean in sections or any(clean.startswith(s) for s in sections):
            return 'section'
            
        if clean in inline_with_gap or any(clean.startswith(iw) for iw in inline_with_gap):
            return 'inline_with_gap'
            
        return 'parameter'

    # Process all bold capital words/phrases with a colon line-by-line
    lines = cleaned_html.split('\n')
    
    # Pre-merge split parameter lines (where header is on one line and value is on the next line(s))
    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            merged_lines.append(line)
            i += 1
            continue
            
        header_match = re.match(
            r'^[•\-\*\s]*(<b>[A-ZА-ЯЁІЇЄҐ][^<]*?:</b>|<b>[A-ZА-ЯЁІЇЄҐ][^<]*?</b>:)[ \t\u200b\xa0]*(.*)',
            line
        )
        if header_match:
            header_html = header_match.group(1).strip()
            value_html = header_match.group(2).strip()
            subtype = classify_header(header_html)
            
            # Merging applies only to 'parameter' and 'inline_with_gap' subtypes
            if subtype in ('parameter', 'inline_with_gap'):
                combined_value = value_html
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        j += 1
                        continue
                    
                    next_header_match = re.match(
                        r'^[•\-\*\s]*(<b>[A-ZА-ЯЁІЇЄҐ][^<]*?:</b>|<b>[A-ZА-ЯЁІЇЄҐ][^<]*?</b>:)',
                        next_line
                    )
                    if next_header_match:
                        break
                        
                    if (next_stripped.startswith(('<blockquote>', '</blockquote>', '<pre>', '</pre>')) or 
                        next_stripped.startswith(('•', '-', '*', '■', '▪', '◦', '○'))):
                        break
                        
                    if combined_value:
                        combined_value += " " + next_stripped
                    else:
                        combined_value = next_stripped
                    j += 1
                
                if combined_value:
                    merged_lines.append(f"{header_html} {combined_value}")
                else:
                    merged_lines.append(header_html)
                i = j
            else:
                merged_lines.append(line)
                i += 1
        else:
            merged_lines.append(line)
            i += 1
            
    lines = merged_lines
    processed_lines = []
    last_line_type = None
    
    # Pre-parse each line to classify its type
    parsed_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            parsed_lines.append(('empty', '', '', ''))
            continue
            
        # Match bold capital header (colon inside or outside) with optional bullets/spaces
        header_match = re.match(
            r'^[•\-\*\s]*(<b>[A-ZА-ЯЁІЇЄҐ][^<]*?:</b>|<b>[A-ZА-ЯЁІЇЄҐ][^<]*?</b>:)[ \t\u200b\xa0]*(.*)',
            line
        )
        if header_match:
            header_html = header_match.group(1).strip()
            value_html = header_match.group(2).strip()
            header_type = classify_header(header_html)
            parsed_lines.append(('header', header_type, header_html, value_html))
        else:
            parsed_lines.append(('other', '', '', line))
            
    for i, (ltype, subtype, part1, part2) in enumerate(parsed_lines):
        if ltype == 'empty':
            # Skip empty lines between consecutive parameters to keep the block compact
            next_non_empty = None
            for j in range(i + 1, len(parsed_lines)):
                if parsed_lines[j][0] != 'empty':
                    next_non_empty = parsed_lines[j]
                    break
            
            if last_line_type == 'parameter' and next_non_empty and next_non_empty[0] == 'header' and next_non_empty[1] == 'parameter':
                continue
                
            processed_lines.append("")
            
        elif ltype == 'header':
            if subtype == 'section':
                if processed_lines and processed_lines[-1] != "":
                    processed_lines.append("")
                processed_lines.append(part1)
                if part2:
                    processed_lines.append(part2)
                last_line_type = 'section'
                
            elif subtype == 'inline_with_gap':
                if last_line_type != 'parameter' and processed_lines and processed_lines[-1] != "":
                    processed_lines.append("")
                if part2:
                    processed_lines.append(f"{part1} {part2}")
                else:
                    processed_lines.append(part1)
                last_line_type = 'inline_with_gap'
                
            elif subtype == 'parameter':
                # Add gap when starting a parameters block from other content
                if last_line_type != 'parameter' and processed_lines and processed_lines[-1] != "":
                    processed_lines.append("")
                if part2:
                    processed_lines.append(f"{part1} {part2}")
                else:
                    processed_lines.append(part1)
                last_line_type = 'parameter'
                
        else:  # ltype == 'other'
            processed_lines.append(part2)
            stripped = part2.strip()
            if stripped != '<blockquote>' and stripped != '</blockquote>':
                last_line_type = 'other'
                
    cleaned_html = '\n'.join(processed_lines)

    header_pattern = r'<b>[A-ZА-ЯЁІЇЄҐ][^<\n]*?</b>\s*:?'

    # Auto-wrap "Additional Info" sections in blockquote if they are not already wrapped.
    additional_info_header = r'<b>(?:Дод\. інформаці|Додатков|Доп\.|Additional)[^<\n]*?</b>\s*:?'
    
    def wrap_additional_info_block(match):
        header = match.group(1)
        content = match.group(2).strip()
        if not content:
            return match.group(0)
        # Strip leading colons, spaces, and newlines before checking blockquote
        content_clean = re.sub(r'^[ \t\u200b\xa0:]+', '', content).strip()
        if content_clean.startswith('<blockquote>'):
            return f"\n{header}\n{content_clean}"
        return f"\n{header}<blockquote>\n{content_clean}\n</blockquote>"

    cleaned_html = re.sub(
        r'(?:\n|^)(' + additional_info_header + r')\s*\n*([\s\S]+?)(?=\n*(?:' + header_pattern + r'|$))',
        wrap_additional_info_block,
        cleaned_html,
        flags=re.IGNORECASE
    )

    # 4. Auto-add bullets to "Features" and "System Requirements" sections if they contain plain lines without bullets.
    def add_bullets_to_section_content(content: str) -> str:
        lines = content.split('\n')
        # 1. Merge line fragments (broken lines starting with lowercase letters/punctuation, or <= 3 chars)
        merged_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                merged_lines.append(line)
                continue
            
            plain_text = re.sub(r'<[^>]+>', '', stripped).strip()
            # If the current line starts with a lowercase letter or punctuation, or has <= 3 characters of plain text,
            # and the previous line is not empty and is not a blockquote boundary, merge them.
            if (merged_lines and 
                merged_lines[-1].strip() and 
                not merged_lines[-1].strip().startswith('<blockquote') and 
                not merged_lines[-1].strip().startswith('</blockquote') and 
                (re.match(r'^[a-zа-яёіїєґ\.,;!\?\)]', plain_text) or len(plain_text) <= 3)):
                
                prev = merged_lines[-1]
                if prev.endswith('-'):
                    merged_lines[-1] = prev[:-1] + line.lstrip()
                else:
                    merged_lines[-1] = prev + " " + line.lstrip()
            else:
                merged_lines.append(line)

        processed_lines = []
        for line in merged_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('<blockquote') or stripped.startswith('</blockquote'):
                processed_lines.append(line)
                continue
            plain_text = re.sub(r'<[^>]+>', '', stripped).strip()
            if not plain_text:
                processed_lines.append(line)
                continue
            if plain_text.startswith(('•', '-', '*', '■', '▪', '◦', '○')) or re.match(r'^\d+\.', plain_text):
                processed_lines.append(line)
            else:
                match_spaces = re.match(r'^(\s*)(.*)', line)
                spaces = match_spaces.group(1)
                remaining = match_spaces.group(2)
                processed_lines.append(f"{spaces}• {remaining}")
        return '\n'.join(processed_lines)

    features_system_header = r'<b>(?:Особливост|Особенност|Features|Системн|Систем|System)[^<\n]*?</b>\s*:?'
    
    cleaned_html = re.sub(
        r'(?:\n|^)(' + features_system_header + r')\s*\n*([\s\S]+?)(?=\n*(?:' + header_pattern + r'|$))',
        lambda m: f"\n{m.group(1)}\n" + add_bullets_to_section_content(m.group(2)),
        cleaned_html,
        flags=re.IGNORECASE
    )

    # Clean up and align blockquotes (strict alignment to prevent empty lines at start/end of blockquote)
    cleaned_html = re.sub(r'\s*<blockquote>\s*', '\n<blockquote>', cleaned_html)
    cleaned_html = re.sub(r'\s*</blockquote>\s*', '</blockquote>\n', cleaned_html)
    cleaned_html = re.sub(r'<blockquote>\s*', '<blockquote>', cleaned_html)
    cleaned_html = re.sub(r'\s*</blockquote>', '</blockquote>', cleaned_html)
    
    # Flatten nested/duplicate blockquotes (e.g. <blockquote><blockquote> -> <blockquote>)
    cleaned_html = re.sub(r'<blockquote>\s*<blockquote>', '<blockquote>', cleaned_html)
    cleaned_html = re.sub(r'</blockquote>\s*</blockquote>', '</blockquote>', cleaned_html)
    
    # Strip double newlines inside blockquotes to maintain clean structure
    cleaned_html = re.sub(r'(<blockquote>[\s\S]*?</blockquote>)', lambda m: re.sub(r'\n{2,}', '\n', m.group(1)), cleaned_html)

    # Under the strict rule, each metadata field must have an empty line before it, so we do not collapse them.

    # Ensure game title headers (bold WITHOUT colon, e.g. "<b>Game Name</b>")
    # have a blank line after them before the metadata block starts
    cleaned_html = re.sub(r'(<b>[^<]+</b>)\n(<b>[^<]+</b>:)', r'\1\n\n\2', cleaned_html)
    cleaned_html = cleaned_html.strip()
    # Final safety pass: collapse any 3+ consecutive newlines introduced by structural operations above
    cleaned_html = re.sub(r'\n{3,}', '\n\n', cleaned_html)
    
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

    # Convert large font-size spans to bold (game titles in multi-game posts)
    for span in description_soup.find_all("span", style=True):
        style = span.get("style", "")
        size_match = re.search(r"font-size:\s*(\d+)", style)
        if size_match and int(size_match.group(1)) >= 18:
            span.name = "b"
            span.attrs = {}

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
    Also cleans up ###GAP### markers used internally for spacing.
    """
    if not text:
        return ""

    # 0. Clean up ###GAP### markers (convert to double newlines)
    text = re.sub(r'(?:\s*###GAP###\s*)+', '\n\n', text)
    text = re.sub(r'###\s*-?\s*', '', text)  # Remove stray ### markers
    # Collapse any 3+ consecutive newlines to max one blank line
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 1. Bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # 2. Italic: *text* -> <i>text</i> (Careful with existing underscore-based markers if needed)
    # We only handle *asterisks* to avoid breaking underscores in links/names
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    # 3. Inline code: `text` -> <code>text</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    return text


def make_tag(description: str, keyword: str) -> str:
    """
    Finds ALL keyword lines (like 'Genre: ...' or 'Год выпуска: ...')
    and converts the items after each keyword into clickable hashtags.
    Handles multiple occurrences for multi-game posts.
    """
    tag_header_pattern = re.compile(
        r"<b>" + re.escape(keyword) + r"(?:\s*:\s*)?</b>\s*:?\s*(.*?)\s*(\n|<br|$)",
        re.IGNORECASE | re.DOTALL
    )

    offset = 0
    while True:
        match = tag_header_pattern.search(description, offset)
        if not match:
            break

        line_after_header = match.group(1).strip()
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
                formatted_tag = f"#{clean_tag_text} (<a href=\"{link_href}\">{link_text_escaped}</a>)"
            else:
                formatted_tag = f"#{clean_tag_text}"
            formatted_tags.append(formatted_tag)

        if formatted_tags:
            formatted_line = ", ".join(formatted_tags)
            start_index = match.start(1)
            end_index = match.end(1)
            description = description[:start_index] + formatted_line + description[end_index:]
            offset = start_index + len(formatted_line)
        else:
            offset = match.end()

    return description
# --- END OF FILE html_utils.py ---
