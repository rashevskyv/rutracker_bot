# --- START OF FILE telegram_sender.py ---
from io import BytesIO

from services.translation import translate_ru_to_ua
from services.ai_validator import summarize_description_with_ai
from core.settings_loader import GROUPS, ERROR_TG, bot, TOKEN
import re
import html
import asyncio
import time
import traceback
import os
import logging
from telebot.types import InputMediaPhoto
from typing import List, Optional, Tuple, IO # Import IO for type hinting file handles
import shutil

# --- Import functions moved to telegram_utils ---
from utils.telegram_utils import (
    split_text, download_cover_image_tg, download_trailer_thumbnail_tg,
    MAX_CAPTION_LENGTH, MAX_MESSAGE_LENGTH,
)
from utils.html_utils import convert_markdown_to_html
# ---------------------------------------------

logger = logging.getLogger(__name__)

# --- Constants ---
MAX_MEDIA_GROUP_SIZE = 10
MIN_MEDIA_FOR_GROUP_STRATEGY = 6 # Send as media group if >= 6 items total (cover+thumb+screenshots)
GOOGLE_IMG_SEARCH_URL = "https://www.google.com/search?tbm=isch&q=Nintendo+Switch"
MAX_DESCRIPTION_LENGTH = 5000 # Summarize if longer than this (approx 2 posts limit)


# --- Private Helper Function for Strategy 1 (Separate Media) ---
async def _send_strategy_separate(
    chat_id: int,
    topic_id: Optional[int],
    message_text: str,
    cover_image_file: Optional[BytesIO],
    trailer_thumbnail_file: Optional[BytesIO],
    local_screenshot_paths: List[str],
    group_name: str = "Unknown",
    log_file: str = ""
) -> List[IO]:
    """Handles sending logic when media count is below the threshold."""
    media_files_opened: List[IO] = []
    caption_for_photo = ""
    remaining_text = message_text
    primary_photo_sent = False

    # Try sending Cover first
    if cover_image_file:
        logger.debug("Strategy 1: Sending cover image...")
        cover_image_file.seek(0)
        caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
        caption_for_photo = convert_markdown_to_html(caption_parts[0]) if caption_parts else None
        remaining_text = "\n\n".join(caption_parts[1:])
        # Merge fragmented blockquotes tightly — no gaps between them
        remaining_text = re.sub(r'</blockquote>\s*<blockquote>', '</blockquote><blockquote>', remaining_text, flags=re.IGNORECASE)

        await bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=cover_image_file, caption=caption_for_photo, parse_mode="HTML")
        if log_file:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n=== [{group_name}] STRATEGY 1 PHOTO CAPTION (len {len(caption_for_photo)}) ===\n{caption_for_photo}\n")
        await asyncio.sleep(1)
        primary_photo_sent = True

    # If no cover, try sending Thumbnail
    elif trailer_thumbnail_file:
        logger.debug("Strategy 1: No cover, sending trailer thumbnail...")
        trailer_thumbnail_file.seek(0)
        caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
        caption_for_photo = convert_markdown_to_html(caption_parts[0]) if caption_parts else None
        remaining_text = "\n\n".join(caption_parts[1:])
        # Merge fragmented blockquotes tightly — no gaps between them
        remaining_text = re.sub(r'</blockquote>\s*<blockquote>', '</blockquote><blockquote>', remaining_text, flags=re.IGNORECASE)

        await bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=trailer_thumbnail_file, caption=caption_for_photo, parse_mode="HTML")
        if log_file:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n=== [{group_name}] STRATEGY 1 THUMBNAIL CAPTION (len {len(caption_for_photo)}) ===\n{caption_for_photo}\n")
        await asyncio.sleep(1)
        primary_photo_sent = True

    # Send Remaining Text (if any)
    if remaining_text.strip():
        logger.debug("Strategy 1: Sending remaining text...")
        disable_first_preview = primary_photo_sent
        message_parts = split_text(remaining_text, MAX_MESSAGE_LENGTH)
        for i, part in enumerate(message_parts):
            if part.strip():
                formatted_part = convert_markdown_to_html(part)
                # Merge fragmented blockquotes tightly
                formatted_part = re.sub(r'</blockquote>\s*<blockquote>', '</blockquote><blockquote>', formatted_part, flags=re.IGNORECASE)
                logger.debug(f"TG Strategy 1 - Sending Part {i+1} (len {len(formatted_part)}): {formatted_part[:300]}...")
                if log_file:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"\n=== [{group_name}] STRATEGY 1 PART {i+1} (len {len(formatted_part)}) ===\n{formatted_part}\n")
                try:
                    await bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=formatted_part, parse_mode="HTML", disable_web_page_preview=(disable_first_preview or i > 0))
                except Exception as send_err:
                    # Capture exact HTML if it fails to parse
                    with open("failing_part.html", "w", encoding="utf-8") as dump_file:
                        dump_file.write(formatted_part)
                    logger.error(f"Saved failing HTML part ({len(formatted_part)} bytes) to failing_part.html. Error: {send_err}")
                    raise send_err
                await asyncio.sleep(1)
            else:
                logger.debug("Strategy 1: Skipped sending empty part of remaining text.")
    else:
        logger.debug("Strategy 1: No remaining text to send.")

    # Send ONLY Screenshots
    if local_screenshot_paths:
        screenshot_media_group: List[InputMediaPhoto] = []
        screenshots_added_count = 0
        for file_path in local_screenshot_paths:
            if len(screenshot_media_group) >= MAX_MEDIA_GROUP_SIZE:
                logger.warning(f"Reached max media group size ({MAX_MEDIA_GROUP_SIZE}), stopping screenshot add.")
                break
            if not os.path.exists(file_path):
                logger.warning(f"Warning: Screenshot file not found: {file_path}")
                continue
            try:
                file_handle = open(file_path, 'rb')
                media_files_opened.append(file_handle) # Add handle to list for later closing
                screenshot_media_group.append(InputMediaPhoto(media=file_handle))
                screenshots_added_count += 1
            except Exception as open_err:
                logger.error(f"Error opening screenshot file {file_path}: {open_err}")

        if screenshot_media_group:
            logger.info(f"Sending screenshot-only media group ({screenshots_added_count} items)...")
            await bot.send_media_group(chat_id=chat_id, message_thread_id=topic_id, media=screenshot_media_group)
            await asyncio.sleep(2)

    return media_files_opened


# --- Private Helper Function for Strategy 2 (Grouped Media) ---
async def _send_strategy_grouped(
    chat_id: int,
    topic_id: Optional[int],
    message_text: str,
    cover_image_file: Optional[BytesIO],
    trailer_thumbnail_file: Optional[BytesIO],
    local_screenshot_paths: List[str],
    is_max_res_thumbnail: bool,
    group_name: str = "Unknown",
    log_file: str = ""
) -> List[IO]:
    """Handles sending logic when media count meets or exceeds the threshold."""
    media_files_opened: List[IO] = []
    media_group_to_send: List[InputMediaPhoto] = []
    caption_for_group = ""
    remaining_text_group = message_text

    # --- Build the media group ---
    if is_max_res_thumbnail and trailer_thumbnail_file:
        trailer_thumbnail_file.seek(0)
        media_group_to_send.append(InputMediaPhoto(media=trailer_thumbnail_file))
        if cover_image_file and len(media_group_to_send) < MAX_MEDIA_GROUP_SIZE:
            cover_image_file.seek(0)
            media_group_to_send.append(InputMediaPhoto(media=cover_image_file))
    else:
        if cover_image_file:
            cover_image_file.seek(0)
            media_group_to_send.append(InputMediaPhoto(media=cover_image_file))
        if trailer_thumbnail_file and len(media_group_to_send) < MAX_MEDIA_GROUP_SIZE:
            trailer_thumbnail_file.seek(0)
            media_group_to_send.append(InputMediaPhoto(media=trailer_thumbnail_file))

    # Add Screenshots
    if local_screenshot_paths:
        screenshots_added_count = 0
        for file_path in local_screenshot_paths:
            if len(media_group_to_send) >= MAX_MEDIA_GROUP_SIZE:
                 logger.warning(f"Reached max media group size ({MAX_MEDIA_GROUP_SIZE}), stopping screenshot add.")
                 break
            if not os.path.exists(file_path):
                logger.warning(f"Warning: Screenshot file not found: {file_path}")
                continue
            try:
                file_handle = open(file_path, 'rb')
                media_files_opened.append(file_handle) # Add handle to list for later closing
                media_group_to_send.append(InputMediaPhoto(media=file_handle))
                screenshots_added_count += 1
            except Exception as open_err:
                logger.error(f"Error opening screenshot file {file_path}: {open_err}")

    # --- Assign Caption and Send ---
    if media_group_to_send:
        caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
        if caption_parts:
            caption_for_group = convert_markdown_to_html(caption_parts[0])
            remaining_text_group = "\n".join(caption_parts[1:])
            media_group_to_send[0].caption = caption_for_group
            media_group_to_send[0].parse_mode = "HTML"
            if log_file:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n=== [{group_name}] STRATEGY 2 MEDIA GROUP CAPTION (len {len(caption_for_group)}) ===\n{caption_for_group}\n")
        else:
            remaining_text_group = ""

        # Send Media Group or Single Photo
        if len(media_group_to_send) > 1:
            logger.info(f"Sending media group ({len(media_group_to_send)} items)...")
            await bot.send_media_group(chat_id=chat_id, message_thread_id=topic_id, media=media_group_to_send)
            await asyncio.sleep(2)
        elif len(media_group_to_send) == 1:
            logger.info("Sending single photo...")
            single_media_obj = media_group_to_send[0]
            media_content = single_media_obj.media
            if hasattr(media_content, 'seek'): media_content.seek(0)
            await bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=media_content, caption=single_media_obj.caption, parse_mode="HTML")
            if log_file:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n=== [{group_name}] STRATEGY 2 SINGLE PHOTO CAPTION (len {len(single_media_obj.caption or '')}) ===\n{single_media_obj.caption}\n")
            await asyncio.sleep(1)

    # Send Remaining Text (if any)
    if remaining_text_group.strip():
        logger.debug("Strategy 2: Sending remaining text...")
        message_parts = split_text(remaining_text_group, MAX_MESSAGE_LENGTH)
        for i, part in enumerate(message_parts):
             if part.strip():
                 formatted_part = convert_markdown_to_html(part)
                 # Merge fragmented blockquotes tightly
                 formatted_part = re.sub(r'</blockquote>\s*<blockquote>', '</blockquote><blockquote>', formatted_part, flags=re.IGNORECASE)
                 logger.debug(f"TG Strategy 2 - Sending Part {i+1} (len {len(formatted_part)}): {formatted_part[:300]}...")
                 if log_file:
                     with open(log_file, "a", encoding="utf-8") as f:
                         f.write(f"\n=== [{group_name}] STRATEGY 2 PART {i+1} (len {len(formatted_part)}) ===\n{formatted_part}\n")
                 await bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=formatted_part, parse_mode="HTML", disable_web_page_preview=True)
                 await asyncio.sleep(1)
             else:
                  logger.debug("Strategy 2: Skipped sending empty part of remaining text.")
    else:
         logger.debug("Strategy 2: No remaining text to send.")

    return media_files_opened


# --- Main Sending Function (remains the same structure, calls helpers) ---
async def send_to_telegram(title_for_caption: str,
                     cover_image_url: Optional[str],
                     magnet_link: str,
                     description: str,
                     entry_url: str,
                     video_id_for_thumbnail: Optional[str] = None,
                     local_screenshot_paths: Optional[List[str]] = None,
                     cycle_log_file: Optional[str] = None):
    """
    Sends the parsed tracker data to configured Telegram groups.
    Handles translation, media grouping, and message splitting.
    Uses helper functions for different sending strategies.
    """
    if not bot:
        logger.error("ERROR in send_to_telegram: Bot is not initialized.")
        return
    if not GROUPS:
        logger.warning("No target groups configured.")
        return

    if local_screenshot_paths is None:
        local_screenshot_paths = []

    # --- AI Summarization for long descriptions ---
    if len(description) > MAX_DESCRIPTION_LENGTH:
        logger.info(f"Description length ({len(description)}) exceeds {MAX_DESCRIPTION_LENGTH}. Summarizing with AI...")
        original_description = description  # Keep a copy of the original
        summarized_description = await summarize_description_with_ai(description, target_length=MAX_DESCRIPTION_LENGTH - 1000)

        # Check if summarization was successful and different from original
        if summarized_description != original_description:
            description = summarized_description  # Replace original description
            
            # Send a notification to the admin/log channel
            log_message = (
                f"📝 Description Summarized for Post\n\n"
                f"Original Length: {len(original_description)}\n"
                f"Summarized Length: {len(summarized_description)}\n\n"
                f"--- ORIGINAL ---\n{html.escape(original_description[:1500])}...\n\n"
                f"--- SUMMARY ---\n{html.escape(summarized_description[:1500])}..."
            )
            await send_message_to_admin(log_message)
        else:
            logger.info("Summarization did not produce a different result. Using original description.")
    # ---

    # Download media needed for all groups first
    cover_image_file = await download_cover_image_tg(cover_image_url)
    trailer_thumbnail_file, thumbnail_resolution = await download_trailer_thumbnail_tg(video_id_for_thumbnail)

    # Calculate total potential media items to decide strategy
    potential_total_media = 0
    if cover_image_file: potential_total_media += 1
    if trailer_thumbnail_file: potential_total_media += 1
    potential_total_media += len(local_screenshot_paths)

    is_max_res_thumbnail = (thumbnail_resolution == "maxres")

    # --- Assemble message text ONCE before the group loop ---
    description_part = description.strip()
    
    # Add a gap before the main description header (if found)
    description_headers = ["Описание", "Описание игры", "Description", "Опис", "Опис гри"]
    for header in description_headers:
        header_pattern = rf"<b>{header}</b>"
        if header_pattern in description_part:
            description_part = description_part.replace(header_pattern, f"###GAP###{header_pattern}")
            break  # Only add one gap

    # Condense technical parameters block globally
    split_point_desc = -1
    for header in description_headers:
        idx = description_part.find(f"###GAP###<b>{header}</b>")
        if idx == -1:
            idx = description_part.find(f"<b>{header}</b>")
        if idx != -1 and (split_point_desc == -1 or idx < split_point_desc):
            split_point_desc = idx
    
    quote_idx_desc = description_part.find("<blockquote>")
    if quote_idx_desc != -1 and (split_point_desc == -1 or quote_idx_desc < split_point_desc):
        split_point_desc = quote_idx_desc
        
    if split_point_desc != -1:
        desc_params = description_part[:split_point_desc]
        desc_rest = description_part[split_point_desc:]
        desc_params = re.sub(r"\n\n\s*<b>", "\n<b>", desc_params)
        description_part = desc_params + desc_rest
    else:
        description_part = re.sub(r"\n\n\s*<b>", "\n<b>", description_part)

    base_message_text = (
        f"{title_for_caption}"
        f"###GAP###"
        f"<b>Скачать:</b> <code>{magnet_link}</code>"
        f"###GAP###"
        f"{description_part}"
    )

    # Translation cache — translate once, reuse for all UA groups
    translated_message_text = None

    # Track sent groups to avoid double posting
    sent_group_keys = set()
    
    # Iterate through each configured group
    for group in GROUPS:
        chat_id = group.get('chat_id')
        topic_id = None
        group_name = group.get('group_name', 'Unknown Group')

        # Validate chat_id
        try:
            if isinstance(chat_id, str) and chat_id.startswith('-'):
                chat_id = int(chat_id)
            elif not isinstance(chat_id, int):
                raise ValueError("Invalid chat_id type")
        except (ValueError, TypeError):
            logger.error(f"Skipping group '{group_name}': invalid chat_id {group.get('chat_id')}")
            continue

        # Validate and set topic_id (message_thread_id)
        topic_id_str = group.get('topic_id')
        if topic_id_str and str(topic_id_str).isdigit():
            topic_id = int(topic_id_str)

        # Create a unique key for this group/topic AFTER parsing both IDs
        group_key = (str(chat_id), str(topic_id) if topic_id else "")
        if group_key in sent_group_keys:
            logger.info(f"Skipping duplicate group entry: {group_name} ({chat_id}, Topic: {topic_id})")
            continue
        sent_group_keys.add(group_key)

        group_lang = group.get('language', 'RU').upper()

        logger.info(f"Processing message for group: {group_name} (Lang: {group_lang}, ChatID: {chat_id}, TopicID: {topic_id})")

        # Use cached translated or original message
        if group_lang == "UA":
            if translated_message_text is None:
                # Translate once and cache
                logger.info("Translating message to UA (first UA group)...")
                try: 
                    description_headers = ["Описание", "Описание игры", "Description", "Опис", "Опис гри"]
                    # Identify where parameters end to isolate consolidation
                    split_point = -1
                    for header in description_headers:
                        idx = base_message_text.find(f"<b>{header}</b>")
                        if idx != -1 and (split_point == -1 or idx < split_point):
                            split_point = idx
                    
                    quote_idx = base_message_text.find("<blockquote>")
                    if quote_idx != -1 and (split_point == -1 or quote_idx < split_point):
                        split_point = quote_idx
                    
                    if split_point != -1:
                        prepared_text = base_message_text[:split_point] + "###PARAMS_END###\n" + base_message_text[split_point:]
                    else:
                        prepared_text = base_message_text

                    # Replace <blockquote> tags with opaque tokens before GPT translation.
                    prepared_text = prepared_text.replace("<blockquote>", "XBQSX")
                    prepared_text = prepared_text.replace("</blockquote>", "XBQEX")

                    translated_message_text = await translate_ru_to_ua(prepared_text)
                    
                    # Final safety: merge any consecutive blockquotes tightly
                    translated_message_text = re.sub(r'</blockquote>\s*<blockquote>', '</blockquote><blockquote>', translated_message_text, flags=re.IGNORECASE)

                    # Force consolidation of technical parameters ONLY
                    if "###PARAMS_END###" in translated_message_text:
                        params_part, rest_part = translated_message_text.split("###PARAMS_END###", 1)
                        params_part = re.sub(r"\n\n\s*<b>", "\n<b>", params_part)
                        translated_message_text = params_part + rest_part
                    else:
                        translated_message_text = re.sub(r"\n\n\s*<b>", "\n<b>", translated_message_text)
                    
                    translated_message_text = translated_message_text.replace("###PARAMS_END###", "")
                    
                    logger.debug(f"Cached translated message (len {len(translated_message_text)})")
                except Exception as e: 
                    logger.error(f"Error translating message: {e}. UA groups will receive original language.")
                    translated_message_text = base_message_text  # Fallback
            
            message_text = translated_message_text
        else:
            message_text = base_message_text

        # --- Execute Sending Strategy ---
        opened_files_for_group: List[IO] = [] # Track files opened for this specific group send
        try:
            if potential_total_media < MIN_MEDIA_FOR_GROUP_STRATEGY:
                opened_files_for_group = await _send_strategy_separate(
                    chat_id, topic_id, message_text, cover_image_file, trailer_thumbnail_file, local_screenshot_paths,
                    group_name=group_name, log_file=cycle_log_file
                )
            else:
                opened_files_for_group = await _send_strategy_grouped(
                    chat_id, topic_id, message_text, cover_image_file, trailer_thumbnail_file, local_screenshot_paths, is_max_res_thumbnail,
                    group_name=group_name, log_file=cycle_log_file
                )

        except Exception as e:
            logger.error(f"!!! Failed to send message to group {group_name}: {type(e).__name__}: {e}")
            error_info = f"Failed sending to {group_name} ({chat_id}): {type(e).__name__}: {str(e)[:200]}"
            if hasattr(e, 'result_json'): error_info += f"\nAPI Response: {str(e.result_json)[:200]}..."
            await send_error_to_telegram(error_info, entry_url=entry_url)
        finally:
            # --- Close files opened specifically for this group's send ---
            for f in opened_files_for_group:
                if hasattr(f, 'close') and not f.closed:
                    try:
                        f.close()
                    except Exception as close_err:
                        logger.error(f"Error closing screenshot file handle {getattr(f, 'name', '')}: {close_err}")

        # Pause between groups
        await asyncio.sleep(2)

    # --- Final Cleanup: Close the main BytesIO objects after processing all groups ---
    if cover_image_file and hasattr(cover_image_file, 'close') and not cover_image_file.closed:
        cover_image_file.close()
    if trailer_thumbnail_file and hasattr(trailer_thumbnail_file, 'close') and not trailer_thumbnail_file.closed:
        trailer_thumbnail_file.close()


# --- Other sender functions (send_message_to_admin, send_error_to_telegram, notify_mismatched_trailer) ---

async def send_message_to_admin(message: str):
    """Sends a plain text or HTML message to all configured admin/error groups."""
    if not bot:
        logger.error("ERROR in send_message_to_admin: Bot not initialized.")
        return
    if not ERROR_TG:
        return

    for error_group in ERROR_TG:
        chat_id = error_group.get('chat_id')
        topic_id = None
        try:
            if isinstance(chat_id, str) and chat_id.startswith('-'): chat_id = int(chat_id)
            elif not isinstance(chat_id, int): raise ValueError("Invalid chat_id type for error group")
            topic_id_str = error_group.get('topic_id');
            if topic_id_str and str(topic_id_str).isdigit(): topic_id = int(topic_id_str)

            formatted_message = convert_markdown_to_html(message)
            if not formatted_message.strip():
                logger.warning("Attempted to send empty admin message, skipped.")
                continue
            await bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=formatted_message, parse_mode='HTML', disable_web_page_preview=True)
            await asyncio.sleep(0.5)
        except Exception as e: logger.error(f"!!! CRITICAL: Failed to send admin message to {error_group.get('chat_id')} (Topic: {topic_id}): {type(e).__name__} - {e}")

async def send_document_to_admin(file_path: str, caption: str = ""):
    """Sends a document to all configured admin/error groups."""
    if not bot:
        logger.error("ERROR in send_document_to_admin: Bot not initialized.")
        return
    if not ERROR_TG:
        return

    import os
    if not os.path.exists(file_path):
        logger.warning(f"File {file_path} not found. Skipped sending to admin.")
        return

    for error_group in ERROR_TG:
        chat_id = error_group.get('chat_id')
        topic_id = None
        try:
            if isinstance(chat_id, str) and chat_id.startswith('-'): chat_id = int(chat_id)
            elif not isinstance(chat_id, int): raise ValueError("Invalid chat_id type for error group")
            topic_id_str = error_group.get('topic_id')
            if topic_id_str and str(topic_id_str).isdigit(): topic_id = int(topic_id_str)

            with open(file_path, 'rb') as f:
                from telebot.types import InputFile
                input_file = InputFile(f)
                await bot.send_document(chat_id=chat_id, message_thread_id=topic_id, document=input_file, caption=caption)
            await asyncio.sleep(0.5)
        except Exception as e: logger.error(f"!!! CRITICAL: Failed to send document to {error_group.get('chat_id')} (Topic: {topic_id}): {type(e).__name__} - {e}")

async def send_error_to_telegram(error_message: str, entry_url: Optional[str] = None):
    """Formats an error message and sends it to admin groups, often using <pre> tags."""
    temp_message = error_message.strip(); max_error_len = 3500
    if temp_message.startswith("<pre>") and temp_message.endswith("</pre>"): formatted_message = temp_message
    elif "Traceback" in error_message or "Error type" in error_message or "Stack Trace" in error_message:
        escaped_message = html.escape(error_message); formatted_message = f"<pre>{escaped_message}</pre>"
    else: formatted_message = html.escape(error_message)
    if len(formatted_message) > max_error_len: formatted_message = formatted_message[:max_error_len] + "\n... (message truncated)"
    
    url_prefix = f"🔗 Link: {entry_url}\n" if entry_url else ""
    final_message = f"❗ Bot Error:\n{url_prefix}\n{formatted_message}"
    await send_message_to_admin(final_message)

async def notify_mismatched_trailer(searched_title: str, found_title: str, trailer_url: str):
    """Sends a specific warning about potentially mismatched YouTube trailers."""
    message = (f"⚠️ YouTube Search Warning:\n\n" f"Searched: <code>{html.escape(searched_title)}</code>\n" f"Found: <code>{html.escape(found_title)}</code>\n" f"URL: {trailer_url}\n\n" f"Title mismatch or potential irrelevance detected (by GPT or logic).")
    await send_message_to_admin(message)

# --- END OF FILE telegram_sender.py ---