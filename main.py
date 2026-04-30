# --- START OF FILE main.py ---
import asyncio
import time
import traceback
import html
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, List
import os
import logging

from settings_loader import (
    LOG, IS_TEST_MODE, FEED_URL, TEST_LAST_ENTRY_LINK, YOUTUBE_API_KEY,
    last_entry_file_path, current_directory, close_clients
)
from feed_handler import (
    read_last_entry_link, write_last_entry_link, get_new_feed_entries
)
from tracker_parser import parse_tracker_entry
from youtube_search import search_trailer_on_youtube
from ai_validator import validate_yt_title_with_gpt
from titledb_manager import TitleDBManager, DEFAULT_TMP_SCREENSHOT_DIR
from telegram_sender import send_to_telegram, send_error_to_telegram, notify_mismatched_trailer, send_message_to_admin, send_document_to_admin
from daily_digest import digest_manager

logger = logging.getLogger(__name__)

# Initialize TitleDB Manager
titledb_json_dir_relative = "titledb"
titledb_json_dir_absolute = os.path.join(current_directory, titledb_json_dir_relative)
db_manager: Optional[TitleDBManager] = None
try:
    db_manager = TitleDBManager(titledb_json_path=titledb_json_dir_relative)
except FileNotFoundError as e:
    logger.error(f"Error initializing TitleDBManager: {e}")
    logger.warning("Screenshots from titledb will be unavailable.")

def get_youtube_video_id(url: Optional[str]) -> Optional[str]:
    """Extracts YouTube video ID from various URL formats."""
    if not url: return None
    try:
        parsed_url = urlparse(url)
        if "youtube.com" in parsed_url.netloc:
            if parsed_url.path == "/watch": return parse_qs(parsed_url.query).get("v", [None])[0]
            if parsed_url.path.startswith(("/embed/", "/v/")): return parsed_url.path.split("/")[2]
        elif "youtu.be" in parsed_url.netloc: return parsed_url.path[1:]
    except Exception as e: logger.error(f"Error parsing YouTube URL {url}: {e}")
    return None

async def main_loop():
    logger.info("-------------------------------------")
    logger.info("Starting RuTracker Feed Checker...")
    logger.info(f"Mode: {'Test' if IS_TEST_MODE else 'Production'}")
    logger.info(f"Log enabled: {LOG}")
    logger.info("-------------------------------------")

    entry_link_in_progress = "N/A"; processed_count = 0

    try:
        if IS_TEST_MODE:
            specific_entry_link_for_test = TEST_LAST_ENTRY_LINK
            if not specific_entry_link_for_test or not specific_entry_link_for_test.startswith('http'):
                logger.error("Test mode enabled, but 'test_last_entry_link' is invalid or not set."); return
            # Use the actual title from the feed if available, otherwise a placeholder
            entries_to_process = [{'link': specific_entry_link_for_test, 'title': 'TEST_MODE_FETCH_TITLE'}]
            logger.info(f"TEST MODE: Processing single link: {specific_entry_link_for_test}")
        else:
            last_processed_link = await asyncio.to_thread(read_last_entry_link, last_entry_file_path)
            new_entries = await get_new_feed_entries(FEED_URL, last_processed_link)
            if new_entries is None: await send_error_to_telegram("Failed to fetch or parse feed."); return
            if not new_entries: logger.info("No new feed entries found."); await send_message_to_admin("No new feed entries found."); return
            logger.info(f"Processing {len(new_entries)} new entries...")
            entries_to_process = new_entries

        # Create a single per-cycle log file for all entries
        cycle_log_file = "log_tg_send.txt"
        with open(cycle_log_file, "w", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"=== BOT RUN CYCLE {datetime.now().isoformat()} ===\n")
            f.write(f"Entries to process: {len(entries_to_process)}\n\n")

        for entry in entries_to_process:
            entry_link = entry.get('link')
            entry_title_feed_or_placeholder = entry.get('title', 'TEST_MODE_FETCH_TITLE')
            if not entry_link: logger.warning("Skipping entry with missing link."); continue
            entry_link_in_progress = entry_link

            logger.info(f"\n--- Processing Entry ---")
            logger.info(f"Link: {entry_link}")

            # Pass entry_link to the parser
            parsed_data = await parse_tracker_entry(entry_link, entry_title_feed_or_placeholder)

            if parsed_data:
                page_display_title, title_text_for_youtube, cover_image_url, magnet_link, cleaned_description, torrent_size, torrent_language = parsed_data

                if not page_display_title or page_display_title == "Unknown Title":
                     logger.error(f"Parser failed to extract display title for {entry_link}. Skipping.")
                     await send_error_to_telegram(f"Parser failed to extract display title for link: {entry_link}", entry_url=entry_link); continue
                if not title_text_for_youtube:
                     logger.warning(f"Parser failed to extract title block for YT search. Using display title '{page_display_title}' as fallback.")
                     title_text_for_youtube = page_display_title

                logger.info(f"Display Title: '{page_display_title}'")
                logger.info(f"Title for Search/Lookup: '{title_text_for_youtube}'")

                is_updated = "[Обновлено]" in entry_title_feed_or_placeholder or "[Updated]" in entry_title_feed_or_placeholder
                update_prefix = "<b>[Обновлено]</b> " if is_updated else ""
                title_link_html = f'<a href="{entry_link}">{html.escape(page_display_title)}</a>'
                final_title_for_telegram = f"{update_prefix}{title_link_html}"

                # Search for Trailer & Prepare Thumbnail
                trailer_thumbnail_url = None # Initialize
                video_id_for_thumbnail = None # Initialize video ID
                try:
                    trailer_url, found_yt_title = await search_trailer_on_youtube(title_text_for_youtube, YOUTUBE_API_KEY)
                    if trailer_url and found_yt_title:
                        is_title_relevant = await validate_yt_title_with_gpt(title_text_for_youtube, found_yt_title)
                        if is_title_relevant:
                            video_id_for_thumbnail = get_youtube_video_id(trailer_url)
                            if video_id_for_thumbnail:
                                logger.info(f"Trailer validated. Video ID for thumbnail: {video_id_for_thumbnail}")
                            else:
                                logger.warning(f"Could not extract video ID from validated trailer URL: {trailer_url}")
                            if 'Trailer</a>' not in final_title_for_telegram:
                                final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                        else:
                            logger.warning(f"GPT validation deemed YT title not relevant.")
                            await notify_mismatched_trailer(title_text_for_youtube, found_yt_title, trailer_url)
                    elif trailer_url:
                         logger.warning(f"Found trailer URL but YT title missing. Adding link cautiously.")
                         if 'Trailer</a>' not in final_title_for_telegram:
                             final_title_for_telegram += f' | <a href="{trailer_url}">Trailer</a>'
                             logger.info(f"Added Trailer link (unvalidated): {trailer_url}")

                except Exception as yt_err:
                     logger.warning(f"YouTube search/validation failed: {yt_err}")

                # Get and Download Screenshots from TitleDB
                local_screenshot_paths: List[str] = []
                if db_manager:
                    game_db_data = await asyncio.to_thread(db_manager.find_game_data, title_text_for_youtube)
                    if game_db_data:
                        nsuid_from_db = game_db_data.get('nsuId')
                        screenshot_urls_from_db = game_db_data.get('screenshots', [])
                        if screenshot_urls_from_db and isinstance(screenshot_urls_from_db, list):
                             logger.debug(f"Found {len(screenshot_urls_from_db)} screenshot URLs in titledb.")
                             local_screenshot_paths = await db_manager.download_screenshots(
                                 screenshot_urls_from_db, nsuid=nsuid_from_db, game_title=title_text_for_youtube
                             )

                # Send to Telegram
                try:
                     await send_to_telegram(
                          final_title_for_telegram,
                          cover_image_url,
                          magnet_link,
                          cleaned_description,
                          entry_link,
                          video_id_for_thumbnail,
                          local_screenshot_paths,
                          cycle_log_file=cycle_log_file
                     )
                     processed_count += 1

                     # Add to daily digest after successful send
                     try:
                         # Extract update description if available
                         update_description = None
                         if is_updated and "Обновлено:" in cleaned_description:
                             import re
                             match = re.search(r'<b>Обновлено:</b>\s*(.+?)(?:\n\n|$)', cleaned_description, re.DOTALL)
                             if match:
                                 update_text = match.group(1).strip()
                                 # Remove HTML tags EXCEPT <a> tags (keep links)
                                 update_text = re.sub(r'<(?!/?a\b)[^>]+>', '', update_text)

                                 # Escape HTML entities but preserve <a> tags
                                 import html as html_module
                                 parts = re.split(r'(<a\s+[^>]*>.*?</a>)', update_text)
                                 escaped_parts = []
                                 for part in parts:
                                     if part.startswith('<a '):
                                         escaped_parts.append(part)  # Keep <a> tags as-is
                                     else:
                                         escaped_parts.append(html_module.escape(part))  # Escape text
                                 update_text = ''.join(escaped_parts)

                                 update_description = update_text[:200]  # Limit length

                         digest_manager.add_entry(
                             title=page_display_title,
                             entry_url=entry_link,
                             size=torrent_size,
                             language=torrent_language,
                             is_updated=is_updated,
                             update_description=update_description
                         )
                         logger.info(f"Added to daily digest: {page_display_title}")
                     except Exception as digest_err:
                         logger.warning(f"Failed to add entry to digest: {digest_err}")

                     if not IS_TEST_MODE:
                          await asyncio.to_thread(write_last_entry_link, last_entry_file_path, entry_link)
                except TypeError as te:
                     logger.error(f"TypeError calling send_to_telegram: {te}. Check function signature.")
                     logger.error(traceback.format_exc())
                     await send_error_to_telegram(f"TypeError calling send_to_telegram for {entry_link}.", entry_url=entry_link)
                     continue
                except Exception as tg_err:
                     logger.error(f"Error sending entry {entry_link} to Telegram: {tg_err}")
                     # Don't write last entry link if sending failed
                     continue

                # Delay
                if not IS_TEST_MODE and len(entries_to_process) > 1 and entry is not entries_to_process[-1]:
                    logger.info("Waiting 60 seconds before processing next entry...")
                    await asyncio.sleep(60)
            else:
                logger.warning(f"Failed to parse data for entry: {entry_link}. Skipping.")
                send_error = True;
                # Avoid sending error if the feed itself failed (new_entries would be None)
                if not IS_TEST_MODE and 'new_entries' in locals() and new_entries is None: send_error = False
                if send_error: await send_error_to_telegram(f"Failed to parse tracker page: {entry_link}", entry_url=entry_link)

        # Loop Finished
        if processed_count > 0: logger.info(f"Successfully processed {processed_count} entries.")
        elif IS_TEST_MODE and processed_count == 0: logger.info("Test run finished, but the test entry failed processing.")
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and not entries_to_process: pass # Normal case: no new entries
        elif not IS_TEST_MODE and 'entries_to_process' in locals() and entries_to_process and processed_count == 0:
             logger.info("Finished processing feed, but no entries were successfully parsed and sent.")
             
        # Send log file to admin if any entries were processed to check formatting
        if processed_count > 0 and os.path.exists(cycle_log_file):
             await send_document_to_admin(cycle_log_file, caption=f"Cycle Log: Processed {processed_count} entries")

        entry_link_in_progress = "N/A"

    except Exception as e:
        error_type = type(e).__name__; error_message = str(e); stack_trace = traceback.format_exc()
        error_details = (f"Unhandled error in main loop.\n"
                         f"Last Link Attempted: {entry_link_in_progress}\n\n"
                         f"<b>Error type</b>: {error_type}\n"
                         f"<b>Error message</b>: {html.escape(error_message)}\n\n"
                         f"<b>Stack Trace</b>:\n<pre>{html.escape(stack_trace)}</pre>")
        logger.error(f"FATAL ERROR in main_loop: {stack_trace}")
        await send_error_to_telegram(error_details)
    finally:
        await close_clients()

if __name__ == "__main__":
    asyncio.run(main_loop())
# --- END OF FILE main.py ---