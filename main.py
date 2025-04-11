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
# Import necessary sender functions including send_message_to_admin
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
            # --- TEST MODE ---
            specific_entry_link_for_test = TEST_LAST_ENTRY_LINK
            if not specific_entry_link_for_test or not specific_entry_link_for_test.startswith('http'):
                print("Error: Test mode enabled, but 'test_last_entry_link' is invalid or not set."); return
            entries_to_process = [{'link': specific_entry_link_for_test, 'title': 'TEST_MODE_FETCH_TITLE'}]
            print(f"TEST MODE: Processing single link: {specific_entry_link_for_test}")
        else:
            # --- PRODUCTION MODE ---
            last_processed_link = read_last_entry_link(last_entry_file_path)
            new_entries = get_new_feed_entries(FEED_URL, last_processed_link)

            if new_entries is None:
                # Error fetching feed
                send_error_to_telegram("Failed to fetch or parse feed.")
                return # Exit if feed fetch fails

            if not new_entries:
                # No new entries found
                message = "No new feed entries found."
                print(message)
                # --- ADDED: Send notification to admin ---
                send_message_to_admin(message)
                # -----------------------------------------
                return # Exit normally if no new entries

            # New entries found
            print(f"Processing {len(new_entries)} new entries...")
            entries_to_process = new_entries

        # --- Process Entries ---
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

                try:
                    trailer_url, found_yt_title = search_trailer_on_youtube(title_text_for_youtube, YOUTUBE_API_KEY)
                    if trailer_url and found_yt_title:
                        compare_search_title = re.sub(r'[^\w\s]+', '', title_text_for_youtube.lower()).strip()
                        compare_yt_title = re.sub(r'[^\w\s]+', '', found_yt_title.lower()).strip()
                        title_matched = compare_search_title in compare_yt_title

                        if title_matched:
                            if 'Trailer</a>' not in final_title_for_telegram:
                                final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                                print(f"Added Trailer link (Title matched YT Search Title): {trailer_url}")
                        else:
                            print(f"Warning: YouTube title '{found_yt_title}' might not match search title '{title_text_for_youtube}'. NOT adding link.")
                            notify_mismatched_trailer(title_text_for_youtube, found_yt_title, trailer_url)
                    elif trailer_url:
                         print(f"Warning: Found trailer URL but YT title missing. Adding link cautiously.")
                         if 'Trailer</a>' not in final_title_for_telegram:
                              final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                except Exception as yt_err:
                     print(f"Warning: YouTube search failed for '{title_text_for_youtube}': {yt_err}")

                try:
                     send_to_telegram(final_title_for_telegram, image_url, magnet_link, cleaned_description)
                     processed_count += 1
                     if not IS_TEST_MODE:
                          latest_link_processed_in_run = entry_link
                          write_last_entry_link(last_entry_file_path, latest_link_processed_in_run)
                except Exception as tg_err:
                     print(f"!!! Error sending entry {entry_link} to Telegram: {tg_err}")
                     continue

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
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and not entries_to_process:
            # This case handles when the feed was fetched successfully but was empty initially (already handled above)
            # Or when all fetched entries failed processing
            pass
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and entries_to_process and processed_count == 0:
             print("\nFinished processing feed, but no entries were successfully parsed and sent.")
        entry_link_in_progress = "N/A"

    except Exception as e:
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