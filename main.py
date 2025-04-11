# --- START OF FILE main.py ---
import time
import traceback
import html # Import html
import re # Import re for YouTube title check

# Import functions from refactored modules
from settings_loader import (
    LOG, IS_TEST_MODE, FEED_URL, TEST_LAST_ENTRY_LINK, YOUTUBE_API_KEY,
    last_entry_file_path
)
from feed_handler import (
    read_last_entry_link, write_last_entry_link, get_new_feed_entries
)
from tracker_parser import parse_tracker_entry
from youtube_search import search_trailer_on_youtube
# --- Import the new validator function ---
from ai_validator import validate_yt_title_with_gpt
# -----------------------------------------
# Import necessary sender functions
from telegram_sender import send_to_telegram, send_error_to_telegram, notify_mismatched_trailer, send_message_to_admin

def main_loop():
    """The main execution loop of the checker."""
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

        latest_link_processed_in_run = None if IS_TEST_MODE else read_last_entry_link(last_entry_file_path)

        for entry in entries_to_process:
            entry_link = entry.get('link')
            entry_title_feed_or_placeholder = entry.get('title', 'TEST_MODE_FETCH_TITLE')
            if not entry_link: print("Skipping entry with missing link."); continue
            entry_link_in_progress = entry_link

            print(f"\n--- Processing Entry ---"); print(f"Link: {entry_link}")

            parsed_data = parse_tracker_entry(entry_link, entry_title_feed_or_placeholder)

            if parsed_data:
                page_display_title, title_text_for_youtube, image_url, magnet_link, cleaned_description = parsed_data

                if not page_display_title or page_display_title == "Unknown Title":
                     print(f"Error: Parser failed to extract display title for {entry_link}. Skipping.")
                     send_error_to_telegram(f"Parser failed to extract display title for link: {entry_link}")
                     continue
                if not title_text_for_youtube:
                     print(f"Warning: Parser failed to extract title block for YT search for {entry_link}. Using display title as fallback.")
                     title_text_for_youtube = page_display_title

                print(f"Display Title: '{page_display_title}'")
                print(f"Title for YT Search: '{title_text_for_youtube}'")

                is_updated = "[Обновлено]" in entry_title_feed_or_placeholder or "[Updated]" in entry_title_feed_or_placeholder
                update_prefix = "<b>[Updated]</b> " if is_updated else ""
                title_link_html = f'<a href="{entry_link}">{html.escape(page_display_title)}</a>'
                final_title_for_telegram = f"{update_prefix}{title_link_html}"

                # --- Search for Trailer ---
                try:
                    trailer_url, found_yt_title = search_trailer_on_youtube(title_text_for_youtube, YOUTUBE_API_KEY)

                    # --- Validate Title with GPT (if trailer found) ---
                    if trailer_url and found_yt_title:
                        # Call the validator function
                        is_title_relevant = validate_yt_title_with_gpt(title_text_for_youtube, found_yt_title)

                        if is_title_relevant:
                            # Add link only if GPT confirms relevance
                            if 'Trailer</a>' not in final_title_for_telegram:
                                final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                                print(f"Added Trailer link (Validated by GPT): {trailer_url}")
                        else:
                            # If GPT says False or validation failed, notify admin
                            print(f"Warning: GPT validation failed or deemed YouTube title '{found_yt_title}' not relevant for '{title_text_for_youtube}'. NOT adding link.")
                            notify_mismatched_trailer(title_text_for_youtube, found_yt_title, trailer_url)
                    elif trailer_url:
                         # Handle case where URL is found but title is missing from YT response (unlikely)
                         print(f"Warning: Found trailer URL but YT title missing. Cannot validate with GPT. Adding link cautiously.")
                         if 'Trailer</a>' not in final_title_for_telegram:
                              final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'

                except Exception as yt_err:
                     print(f"Warning: YouTube search/validation failed for '{title_text_for_youtube}': {yt_err}")

                # --- Send to Telegram ---
                try:
                     send_to_telegram(final_title_for_telegram, image_url, magnet_link, cleaned_description)
                     processed_count += 1
                     if not IS_TEST_MODE:
                          write_last_entry_link(last_entry_file_path, entry_link)
                except Exception as tg_err:
                     print(f"!!! Error sending entry {entry_link} to Telegram: {tg_err}")
                     continue

                # --- Delay ---
                if not IS_TEST_MODE and len(entries_to_process) > 1 and entry is not entries_to_process[-1]:
                    print("Waiting 60 seconds before processing next entry...")
                    time.sleep(60)
            else:
                print(f"Failed to parse data for entry: {entry_link}. Skipping.")
                send_error = True
                if not IS_TEST_MODE and 'new_entries' in locals() and new_entries is None: send_error = False
                if send_error: send_error_to_telegram(f"Failed to parse tracker page: {entry_link}")

        # --- Loop Finished ---
        if processed_count > 0: print(f"\nSuccessfully processed {processed_count} entries.")
        elif IS_TEST_MODE and processed_count == 0: print("\nTest run finished, but the test entry failed processing.")
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and not entries_to_process: pass
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and entries_to_process and processed_count == 0:
             print("\nFinished processing feed, but no entries were successfully parsed and sent.")
        entry_link_in_progress = "N/A"

    except Exception as e:
        # Error handling remains the same
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