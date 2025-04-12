# --- START OF FILE telegram_sender.py ---
from io import BytesIO
import requests
from translation import translate_ru_to_ua
from settings_loader import GROUPS, ERROR_TG, LOG, bot, TOKEN
import re
import html # Import html module
from html.parser import HTMLParser
import time
import traceback
import os # Import os for file operations
# --- Import InputMediaPhoto ---
from telebot.types import InputMediaPhoto
# -----------------------------
from typing import List, Optional

# Constants for Telegram limits
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096
MAX_MEDIA_GROUP_SIZE = 10 # Telegram allows max 10 items in a media group

# Classes HTMLTagParser, functions check_html_tags, close_tags, split_text remain the same
class HTMLTagParser(HTMLParser):
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.tags = []
    def handle_starttag(self, tag, attrs):
        if tag not in ('br', 'img', 'hr'): self.tags.append(tag)
    def handle_endtag(self, tag):
        if tag not in ('br', 'img', 'hr'):
            if self.tags and self.tags[-1] == tag: self.tags.pop()
    def get_unclosed_tags(self): return self.tags[:]

def check_html_tags(text: str) -> List[str]:
    parser = HTMLTagParser(); parser.feed(text); return parser.get_unclosed_tags()

def close_tags(tags: List[str]) -> str:
    return "".join([f"</{tag}>" for tag in reversed(tags)])

def split_text(text: str, max_length: int) -> List[str]:
    parts: List[str] = []; current_part = ""; open_tags_stack: List[str] = []
    lines = text.split('\n')
    for line_index, line in enumerate(lines):
        line_with_newline = line + ('\n' if line_index < len(lines) - 1 else '')
        prefix_tags = "".join([f"<{tag}>" for tag in open_tags_stack])
        projected_length = len(current_part) + len(prefix_tags) + len(line_with_newline)
        if projected_length <= max_length:
            current_part += prefix_tags + line_with_newline
            line_parser = HTMLTagParser(); line_parser.tags = open_tags_stack[:]; line_parser.feed(line)
            open_tags_stack = line_parser.get_unclosed_tags()
        else:
            if current_part:
                part_parser = HTMLTagParser(); part_parser.feed(current_part)
                final_open_tags = part_parser.get_unclosed_tags()
                current_part += close_tags(final_open_tags); parts.append(current_part)
                open_tags_stack = final_open_tags
                current_part = "".join([f"<{tag}>" for tag in open_tags_stack]) + line_with_newline
                line_parser = HTMLTagParser(); line_parser.tags = open_tags_stack[:]; line_parser.feed(line)
                open_tags_stack = line_parser.get_unclosed_tags()
            else:
                # print(f"Warning: Line segment might exceed max_length ({max_length}). Splitting line.") # Less verbose
                available_space = max_length - len(prefix_tags)
                parts.append(prefix_tags + line_with_newline[:available_space])
                current_part = ""; open_tags_stack = []
    if current_part.strip():
         part_parser = HTMLTagParser(); part_parser.feed(current_part)
         final_open_tags = part_parser.get_unclosed_tags()
         current_part += close_tags(final_open_tags); parts.append(current_part)
    return [p.strip() for p in parts if p.strip()]

# download_image remains the same
def download_image(image_url: str, timeout: int = 15) -> Optional[BytesIO]:
    image = None; fallback_url = 'https://via.placeholder.com/300x200.png?text=No+Image+Found'
    if not image_url or not image_url.startswith(('http://', 'https://')): return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}; response = requests.get(image_url, headers=headers, timeout=timeout)
        response.raise_for_status(); content_type = response.headers.get('Content-Type', '').lower()
        if not content_type.startswith('image/'): return None
        image = BytesIO(response.content); return image
    except Exception as e: print(f"Cover image download failed for {image_url}: {e}. Trying fallback...")
    if image_url != fallback_url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}; response = requests.get(fallback_url, headers=headers, timeout=timeout)
            response.raise_for_status(); content_type = response.headers.get('Content-Type', '').lower()
            if not content_type.startswith('image/'): return None
            image = BytesIO(response.content); return image
        except Exception as e: print(f"Fallback image download failed: {e}"); return None
    return None

# --- UPDATED send_to_telegram SIGNATURE and LOGIC ---
def send_to_telegram(title_with_link: str,
                     cover_image_url: Optional[str],
                     magnet_link: str,
                     description: str,
                     local_screenshot_paths: Optional[List[str]] = None): # Accept list of local paths
    """
    Formats and sends game info to Telegram, including optional local screenshots as media group.
    """
    if not GROUPS: print("No target groups configured."); return
    if local_screenshot_paths is None: local_screenshot_paths = [] # Ensure it's a list

    cover_image_file = download_image(cover_image_url) if cover_image_url else None

    for group in GROUPS:
        chat_id = group.get('chat_id'); topic_id = None; group_name = group.get('group_name', 'Unknown Group')
        try:
            if isinstance(chat_id, str) and chat_id.startswith('-'): chat_id = int(chat_id)
            elif not isinstance(chat_id, int): raise ValueError("Invalid chat_id type")
        except (ValueError, TypeError): print(f"Skipping group '{group_name}' due to invalid chat_id: {group.get('chat_id')}"); continue
        topic_id_str = group.get('topic_id');
        if topic_id_str and topic_id_str.isdigit(): topic_id = int(topic_id_str)
        group_lang = group.get('language', 'RU').upper()
        print(f"\nProcessing message for group: {group_name} (Lang: {group_lang}, ChatID: {chat_id}, TopicID: {topic_id})")

        description_part = description.strip()
        base_message_text = f"{title_with_link}\n\n<b>Download</b>: <code>{magnet_link}</code>\n\n{description_part}"
        if LOG: print(f"Base message text ({group_lang}) length:", len(base_message_text))

        message_text = base_message_text
        if group_lang == "UA":
            try: message_text = translate_ru_to_ua(base_message_text)
            except Exception as e: print(f"Error translating message for {group_name}: {e}.")
            if LOG: print(f"Translated message text (UA) length:", len(message_text))

        try:
            first_caption = ""; remaining_text = message_text
            media_group_to_send = [] # Initialize media group list

            if cover_image_file:
                # print("Sending cover image with caption...") # Less verbose
                cover_image_file.seek(0)
                caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
                if not caption_parts: print(f"Warning: Empty caption after splitting for {group_name}."); continue
                first_caption = caption_parts[0]; remaining_text = "\n".join(caption_parts[1:])
                bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=cover_image_file, caption=first_caption, parse_mode="HTML")
                time.sleep(1)
            # else: print("No cover image. Sending text message(s)...") # Less verbose

            if remaining_text.strip():
                 # print("Sending remaining description text...") # Less verbose
                 message_parts = split_text(remaining_text, MAX_MESSAGE_LENGTH)
                 for i, part in enumerate(message_parts):
                      # if LOG: print(f"Sending text part {i+1}/{len(message_parts)}...") # Less verbose
                      bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=part, parse_mode="HTML", disable_web_page_preview=True)
                      time.sleep(1)

            # --- Send Screenshots using LOCAL PATHS ---
            if local_screenshot_paths:
                print(f"Preparing media group with {len(local_screenshot_paths)} local screenshots...")
                media_files_opened = [] # To keep track of opened files for closing
                try:
                    for i, file_path in enumerate(local_screenshot_paths): # Already limited by manager
                         if not os.path.exists(file_path):
                              print(f"Warning: Screenshot file not found: {file_path}")
                              continue
                         # --- Open file in binary read mode ---
                         file_handle = open(file_path, 'rb')
                         media_files_opened.append(file_handle) # Add to list for later closing
                         # --------------------------------------
                         # Create InputMediaPhoto using the file handle
                         media_group_to_send.append(InputMediaPhoto(media=file_handle))
                         # Limit group size just in case manager limit changes
                         if len(media_group_to_send) >= MAX_MEDIA_GROUP_SIZE: break

                    if media_group_to_send:
                         print(f"Sending media group ({len(media_group_to_send)} items)...")
                         bot.send_media_group(chat_id=chat_id, message_thread_id=topic_id, media=media_group_to_send)
                         time.sleep(2)
                except Exception as mg_err:
                     print(f"!!! Error preparing/sending media group: {mg_err}")
                     send_error_to_telegram(f"Failed sending media group for {group_name}: {mg_err}")
                finally:
                     # --- IMPORTANT: Close all opened file handles ---
                     for f in media_files_opened:
                          try: f.close()
                          except Exception as close_err: print(f"Error closing screenshot file handle: {close_err}")
                     # ---------------------------------------------

            # print(f"Successfully sent message components to {group_name}.") # Less verbose

        except Exception as e:
            print(f"!!! Failed to send message to group {group_name} (ChatID: {chat_id}, TopicID: {topic_id}): {type(e).__name__}: {e}")
            if LOG: traceback.print_exc()
            error_info = f"Failed to send to group {group_name}: {type(e).__name__}: {e}";
            if hasattr(e, 'result_json'): error_info += f"\nAPI Response: {str(e.result_json)[:200]}..."
            send_error_to_telegram(error_info)

        time.sleep(2)

# Other functions (send_message_to_admin, send_error_to_telegram, notify_mismatched_trailer) remain the same
def send_message_to_admin(message: str):
    if not ERROR_TG: return
    for error_group in ERROR_TG:
        chat_id = error_group.get('chat_id'); topic_id = None
        try:
             if isinstance(chat_id, str) and chat_id.startswith('-'): chat_id = int(chat_id)
             elif not isinstance(chat_id, int): raise ValueError("Invalid chat_id type")
             topic_id_str = error_group.get('topic_id');
             if topic_id_str and topic_id_str.isdigit(): topic_id = int(topic_id_str)
             bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message, parse_mode='HTML', disable_web_page_preview=True); time.sleep(0.5)
        except Exception as e: print(f"!!! CRITICAL: Failed to send admin message to {error_group.get('chat_id')} (Topic: {topic_id}): {type(e).__name__} - {e}")

def send_error_to_telegram(error_message: str):
    # print(f"Sending error notification...") # Less verbose
    temp_message = error_message.strip()
    if temp_message.startswith("<pre>") and temp_message.endswith("</pre>"): formatted_message = temp_message
    elif "Traceback" in error_message or "Error type" in error_message or "Stack Trace" in error_message:
        escaped_message = html.escape(error_message); formatted_message = f"<pre>{escaped_message}</pre>"
    else: formatted_message = html.escape(error_message)
    max_error_len = 4000
    if len(formatted_message) > max_error_len: formatted_message = formatted_message[:max_error_len] + "\n... (message truncated)"
    send_message_to_admin(f"❗ Bot Error:\n\n{formatted_message}")

def notify_mismatched_trailer(searched_title: str, found_title: str, trailer_url: str):
    # print(f"Sending mismatched trailer notification...") # Less verbose
    message = (f"⚠️ YouTube Search Warning:\n\n"
               f"Searched for: <code>{html.escape(searched_title)}</code>\n"
               f"Found trailer: <code>{html.escape(found_title)}</code>\n"
               f"URL: {trailer_url}\n\n"
               f"Title may not match searched game.")
    send_message_to_admin(message)

# --- END OF FILE telegram_sender.py ---