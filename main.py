# --- START OF FILE main.py ---
import time
import traceback
import html
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, List
import os

from settings_loader import (
    LOG, IS_TEST_MODE, FEED_URL, TEST_LAST_ENTRY_LINK, YOUTUBE_API_KEY,
    last_entry_file_path, current_directory
)
from feed_handler import (
    read_last_entry_link, write_last_entry_link, get_new_feed_entries
)
from tracker_parser import parse_tracker_entry
from youtube_search import search_trailer_on_youtube
from ai_validator import validate_yt_title_with_gpt
from titledb_manager import TitleDBManager, DEFAULT_TMP_SCREENSHOT_DIR
from telegram_sender import send_to_telegram, send_error_to_telegram, notify_mismatched_trailer, send_message_to_admin

# Initialize TitleDB Manager
titledb_json_dir_relative = "titledb"
titledb_json_dir_absolute = os.path.join(current_directory, titledb_json_dir_relative)
db_manager: Optional[TitleDBManager] = None
try:
    db_manager = TitleDBManager(titledb_json_path=titledb_json_dir_relative)
except FileNotFoundError as e:
    print(f"Error initializing TitleDBManager: {e}")
    print("Screenshots from titledb will be unavailable.")

def get_youtube_video_id(url: Optional[str]) -> Optional[str]:
    """Extracts YouTube video ID from various URL formats."""
    if not url: return None
    try:
        parsed_url = urlparse(url)
        if "youtube.com" in parsed_url.netloc:
            if parsed_url.path == "/watch": return parse_qs(parsed_url.query).get("v", [None])[0]
            if parsed_url.path.startswith(("/embed/", "/v/")): return parsed_url.path.split("/")[2]
        elif "youtu.be" in parsed_url.netloc: return parsed_url.path[1:]
    except Exception as e: print(f"Error parsing YouTube URL {url}: {e}")
    return None

def main_loop():
    print("-------------------------------------")
    print("Starting RuTracker Feed Checker...")
    print(f"Mode: {'Test' if IS_TEST_MODE else 'Production'}")
    print(f"Log enabled: {LOG}")
    print("-------------------------------------")

    entry_link_in_progress = "N/A"; processed_count = 0

    try:
        if IS_TEST_MODE:
            specific_entry_link_for_test = TEST_LAST_ENTRY_LINK
            if not specific_entry_link_for_test or not specific_entry_link_for_test.startswith('http'):
                print("Error: Test mode enabled, but 'test_last_entry_link' is invalid or not set."); return
            entries_to_process = [{'link': specific_entry_link_for_test, 'title': 'TEST_MODE_FETCH_TITLE'}]
            print(f"TEST MODE: Processing single link: {specific_entry_link_for_test}")
        else:
            last_processed_link = read_last_entry_link(last_entry_file_path)
            new_entries = get_new_feed_entries(FEED_URL, last_processed_link)
            if new_entries is None: send_error_to_telegram("Failed to fetch or parse feed."); return
            if not new_entries: print("No new feed entries found."); send_message_to_admin("No new feed entries found."); return
            print(f"Processing {len(new_entries)} new entries...")
            entries_to_process = new_entries

        for entry in entries_to_process:
            entry_link = entry.get('link')
            entry_title_feed_or_placeholder = entry.get('title', 'TEST_MODE_FETCH_TITLE')
            if not entry_link: print("Skipping entry with missing link."); continue
            entry_link_in_progress = entry_link

            print(f"\n--- Processing Entry ---"); print(f"Link: {entry_link}")

            parsed_data = parse_tracker_entry(entry_link, entry_title_feed_or_placeholder)

            if parsed_data:
                page_display_title, title_text_for_youtube, cover_image_url, magnet_link, cleaned_description = parsed_data

                if not page_display_title or page_display_title == "Unknown Title":
                     print(f"Error: Parser failed to extract display title for {entry_link}. Skipping.")
                     send_error_to_telegram(f"Parser failed to extract display title for link: {entry_link}"); continue
                if not title_text_for_youtube:
                     print(f"Warning: Parser failed to extract title block for YT search. Using display title '{page_display_title}' as fallback.")
                     title_text_for_youtube = page_display_title

                print(f"Display Title: '{page_display_title}'")
                print(f"Title for Search/Lookup: '{title_text_for_youtube}'")

                is_updated = "[Обновлено]" in entry_title_feed_or_placeholder or "[Updated]" in entry_title_feed_or_placeholder
                update_prefix = "<b>[Updated]</b> " if is_updated else ""
                title_link_html = f'<a href="{entry_link}">{html.escape(page_display_title)}</a>'
                final_title_for_telegram = f"{update_prefix}{title_link_html}"

                # Search for Trailer & Prepare Thumbnail
                trailer_thumbnail_url = None # Initialize
                video_id_for_thumbnail = None # Initialize video ID
                try:
                    trailer_url, found_yt_title = search_trailer_on_youtube(title_text_for_youtube, YOUTUBE_API_KEY)
                    if trailer_url and found_yt_title:
                        is_title_relevant = validate_yt_title_with_gpt(title_text_for_youtube, found_yt_title)
                        if is_title_relevant:
                            # --- Get video ID ---
                            video_id_for_thumbnail = get_youtube_video_id(trailer_url)
                            if video_id_for_thumbnail:
                                print(f"Trailer validated. Video ID for thumbnail: {video_id_for_thumbnail}")
                            else:
                                print(f"Warning: Could not extract video ID from validated trailer URL: {trailer_url}")
                            # --- Add text link ---
                            if 'Trailer</a>' not in final_title_for_telegram:
                                final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                        else:
                            print(f"Warning: GPT validation deemed YT title not relevant.")
                            notify_mismatched_trailer(title_text_for_youtube, found_yt_title, trailer_url)
                    elif trailer_url:
                         print(f"Warning: Found trailer URL but YT title missing. Adding link cautiously.")
                         if 'Trailer</a>' not in final_title_for_telegram:
                             final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                             print(f"Added Trailer link (unvalidated): {trailer_url}")

                except Exception as yt_err:
                     print(f"Warning: YouTube search/validation failed: {yt_err}")

                # Get and Download Screenshots from TitleDB
                local_screenshot_paths: List[str] = []
                if db_manager:
                    game_db_data = db_manager.find_game_data(title_text_for_youtube)
                    if game_db_data:
                        nsuid_from_db = game_db_data.get('nsuId')
                        screenshot_urls_from_db = game_db_data.get('screenshots', [])
                        if screenshot_urls_from_db and isinstance(screenshot_urls_from_db, list):
                             if LOG: print(f"Found {len(screenshot_urls_from_db)} screenshot URLs in titledb.")
                             local_screenshot_paths = db_manager.download_screenshots(
                                 screenshot_urls_from_db, nsuid=nsuid_from_db, game_title=title_text_for_youtube
                             )

                # Send to Telegram
                try:
                     # --- Pass video_id instead of pre-formatted URL ---
                     send_to_telegram(
                         final_title_for_telegram,
                         cover_image_url,
                         magnet_link,
                         cleaned_description,
                         video_id_for_thumbnail, # Pass only the ID
                         local_screenshot_paths
                     )
                     # ----------------------------------------------------
                     processed_count += 1
                     if not IS_TEST_MODE:
                          write_last_entry_link(last_entry_file_path, entry_link)
                except TypeError as te:
                     print(f"!!! TypeError calling send_to_telegram: {te}. Check function signature.")
                     traceback.print_exc(); send_error_to_telegram(f"TypeError calling send_to_telegram for {entry_link}.")
                     continue
                except Exception as tg_err:
                     print(f"!!! Error sending entry {entry_link} to Telegram: {tg_err}")
                     continue

                # Delay
                if not IS_TEST_MODE and len(entries_to_process) > 1 and entry is not entries_to_process[-1]:
                    print("Waiting 60 seconds before processing next entry...")
                    time.sleep(60)
            else:
                print(f"Failed to parse data for entry: {entry_link}. Skipping.")
                send_error = True;
                if not IS_TEST_MODE and 'new_entries' in locals() and new_entries is None: send_error = False
                if send_error: send_error_to_telegram(f"Failed to parse tracker page: {entry_link}")

        # Loop Finished
        if processed_count > 0: print(f"\nSuccessfully processed {processed_count} entries.")
        elif IS_TEST_MODE and processed_count == 0: print("\nTest run finished, but the test entry failed processing.")
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and not entries_to_process: pass
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and entries_to_process and processed_count == 0:
             print("\nFinished processing feed, but no entries were successfully parsed and sent.")
        entry_link_in_progress = "N/A"

    except Exception as e:
        # Error handling
        error_type = type(e).__name__; error_message = str(e); stack_trace = traceback.format_exc()
        error_details = (f"Unhandled error in main loop.\n"
                         f"Last Link Attempted: {entry_link_in_progress}\n\n"
                         f"<b>Error type</b>: {error_type}\n"
                         f"<b>Error message</b>: {html.escape(error_message)}\n\n"
                         f"<b>Stack Trace</b>:\n<pre>{html.escape(stack_trace)}</pre>")
        print("\n---!!! FATAL ERROR in main_loop !!!---"); traceback.print_exc(limit=5); print("---!!! END ERROR !!!---")
        send_error_to_telegram(error_details)

if __name__ == "__main__":
    main_loop()
# --- END OF FILE main.py ---