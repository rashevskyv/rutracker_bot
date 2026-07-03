import asyncio
import sys
import os
import html
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession as CurlSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import RUTRACKER_COOKIES, close_clients
from parsers.tracker_parser import parse_tracker_entry
from utils.html_utils import clean_description_html, sanitize_html_for_telegram
from utils.telegram_utils import split_text, check_html_tags

async def main():
    url = "https://rutracker.org/forum/viewtopic.php?t=5734418"
    cookies = RUTRACKER_COOKIES or {}
    print("Using cookies:", cookies)
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://rutracker.org/forum/index.php'
    }
    
    # Let's try parsing the tracker entry
    try:
        parsed_data = await parse_tracker_entry(url, "TEST [Обновлено]")
        if parsed_data:
            page_display_title, title_text_for_youtube, cover_image_url, magnet_link, cleaned_description, torrent_size, torrent_language, genres, raw_update_text = parsed_data
            print("Successfully parsed tracker entry!")
            print("Title:", page_display_title)
            print("Size:", torrent_size)
            print("Raw description length:", len(cleaned_description))
            
            # Now let's try to assemble the message text like in telegram_sender.py
            download_label = f"<b>Скачать [{torrent_size}]:</b>" if torrent_size else "<b>Скачать:</b>"
            base_message_text = (
                f'<a href="{url}">{html.escape(page_display_title)}</a>'
                f"###GAP###"
                f"{download_label}\n"
                f"<code>{magnet_link}</code>"
                f"###GAP###"
                f"{cleaned_description}"
            )
            
            # Since the error occurred on Kefir_ukr (which has language="UA"), let's see how translation is done, 
            # or first check RU version. Let's translate using the actual translate function if possible, or print the text first.
            print("\nChecking HTML tag balance of RU message:")
            unclosed = check_html_tags(base_message_text)
            print("Unclosed tags in full RU message:", unclosed)
            
            # Let's check splits
            MAX_MESSAGE_LENGTH = 4096
            parts = split_text(base_message_text, MAX_MESSAGE_LENGTH)
            print(f"Split into {len(parts)} parts.")
            for idx, part in enumerate(parts):
                unclosed_part = check_html_tags(part)
                print(f"Part {idx+1} unclosed tags:", unclosed_part)
                # Check for "Unexpected end tag" or mismatched tags
                # Try to feed to HTMLTagParser manually to see if it raises any errors or has weird stack
                from html.parser import HTMLParser
                class StrictHTMLParser(HTMLParser):
                    def handle_starttag(self, tag, attrs):
                        pass
                    def handle_endtag(self, tag):
                        pass
                try:
                    StrictHTMLParser().feed(part)
                    print(f"Part {idx+1} is syntactically valid for HTMLParser.")
                except Exception as parse_ex:
                    print(f"Part {idx+1} HTMLParser error:", parse_ex)
                
                # Check where offset 2745 could be
                if len(part) >= 2745:
                    print(f"Context around byte offset 2745 in Part {idx+1}:")
                    print(part[max(0, 2745-100):min(len(part), 2745+100)])
                else:
                    print(f"Part {idx+1} is only {len(part)} bytes long, offset 2745 is out of bounds.")
                    
        else:
            print("parse_tracker_entry returned None!")
    except Exception as e:
        print("Error during main debug:", e)
        import traceback
        traceback.print_exc()
    finally:
        await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
