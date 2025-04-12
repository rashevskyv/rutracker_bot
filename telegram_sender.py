# --- START OF FILE telegram_sender.py ---
from io import BytesIO
import requests
from translation import translate_ru_to_ua
try:
    from settings_loader import GROUPS, ERROR_TG, LOG, bot, TOKEN
except ImportError:
    print("WARNING: Could not import from settings_loader. Using dummy values for direct script execution.")
    import os; LOG = True; bot = None; TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN"); GROUPS = []; ERROR_TG = []
import re
import html
from html.parser import HTMLParser
import time
import traceback
import os
from telebot.types import InputMediaPhoto
from typing import List, Optional, Tuple
import shutil

MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096
MAX_MEDIA_GROUP_SIZE = 10
MIN_MEDIA_FOR_GROUP_STRATEGY = 6
GOOGLE_IMG_SEARCH_URL = "https://www.google.com/search?tbm=isch&q=Nintendo+Switch"

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
            current_part += prefix_tags + line_with_newline; line_parser = HTMLTagParser(); line_parser.tags = open_tags_stack[:]; line_parser.feed(line); open_tags_stack = line_parser.get_unclosed_tags()
        else:
            if current_part:
                part_parser = HTMLTagParser(); part_parser.feed(current_part); final_open_tags = part_parser.get_unclosed_tags(); current_part += close_tags(final_open_tags); parts.append(current_part); open_tags_stack = final_open_tags; current_part = "".join([f"<{tag}>" for tag in open_tags_stack]) + line_with_newline; line_parser = HTMLTagParser(); line_parser.tags = open_tags_stack[:]; line_parser.feed(line); open_tags_stack = line_parser.get_unclosed_tags()
            else: available_space = max_length - len(prefix_tags); parts.append(prefix_tags + line_with_newline[:available_space]); current_part = ""; open_tags_stack = []
    if current_part.strip(): part_parser = HTMLTagParser(); part_parser.feed(current_part); final_open_tags = part_parser.get_unclosed_tags(); current_part += close_tags(final_open_tags); parts.append(current_part)
    return [p.strip() for p in parts if p.strip()]
def _try_download_image_tg(image_url: str, timeout: int = 15) -> Optional[BytesIO]:
    if not image_url or not image_url.startswith(('http://', 'https://')): return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}; response = requests.get(image_url, headers=headers, timeout=timeout)
        response.raise_for_status(); img_data = BytesIO(response.content)
        if img_data.getbuffer().nbytes == 0: return None
        img_data.seek(0); return img_data
    except Exception as e: print(f"    TG: Download failed for {image_url}: {e}"); return None
def download_cover_image_tg(image_url: str, timeout: int = 15) -> Optional[BytesIO]:
    fallback_url = 'https://via.placeholder.com/300x200.png/EEEEEE/000000?text=No+Cover'
    if LOG: print("TG: Attempting to download cover image...")
    image = _try_download_image_tg(image_url, timeout)
    if image: return image
    print("TG: Cover download failed. Trying fallback...")
    if image_url != fallback_url:
        image = _try_download_image_tg(fallback_url, timeout)
        if image: print("TG: Fallback image downloaded."); return image
        else: print("TG: Fallback image download failed.")
    return None
def download_trailer_thumbnail_tg(video_id: str, timeout: int = 15) -> Tuple[Optional[BytesIO], Optional[str]]:
    if not video_id: return None, None
    if LOG: print(f"TG: Attempting to download trailer thumbnail for video ID: {video_id}")
    resolutions = [("maxres", "maxresdefault"), ("sd", "sddefault"), ("hq", "hqdefault"), ("mq", "mqdefault"), ("default", "default")]
    for res_key, filename_part in resolutions:
        url = f"https://img.youtube.com/vi/{video_id}/{filename_part}.jpg"
        image = _try_download_image_tg(url, timeout)
        if image:
             if LOG: print(f"  TG: Successfully downloaded thumbnail ({res_key}): {url}")
             return image, res_key
    return None, None

def send_to_telegram(title_for_caption: str,
                     cover_image_url: Optional[str],
                     magnet_link: str,
                     description: str,
                     video_id_for_thumbnail: Optional[str] = None,
                     local_screenshot_paths: Optional[List[str]] = None):
    global bot
    if not bot: print("ERROR in send_to_telegram: Bot is not initialized."); return
    if not GROUPS: print("No target groups configured."); return
    if local_screenshot_paths is None: local_screenshot_paths = []
    cover_image_file = download_cover_image_tg(cover_image_url) if cover_image_url else None
    trailer_thumbnail_file, thumbnail_resolution = download_trailer_thumbnail_tg(video_id_for_thumbnail) if video_id_for_thumbnail else (None, None)
    potential_total_media = 0
    if cover_image_file: potential_total_media += 1
    if trailer_thumbnail_file: potential_total_media += 1
    potential_total_media += len(local_screenshot_paths)
    is_max_res_thumbnail = (thumbnail_resolution == "maxres")
    for group in GROUPS:
        chat_id = group.get('chat_id'); topic_id = None; group_name = group.get('group_name', 'Unknown Group')
        try:
            if isinstance(chat_id, str) and chat_id.startswith('-'): chat_id = int(chat_id)
            elif not isinstance(chat_id, int): raise ValueError("Invalid chat_id type")
        except (ValueError, TypeError): print(f"Skipping group '{group_name}': invalid chat_id {group.get('chat_id')}"); continue
        topic_id_str = group.get('topic_id');
        if topic_id_str and topic_id_str.isdigit(): topic_id = int(topic_id_str)
        group_lang = group.get('language', 'RU').upper()
        print(f"\nProcessing message for group: {group_name} (Lang: {group_lang}, ChatID: {chat_id}, TopicID: {topic_id})")
        description_part = description.strip()
        base_message_text = f"{title_for_caption}\n\n<b>Download</b>: <code>{magnet_link}</code>\n\n{description_part}"
        message_text = base_message_text
        if group_lang == "UA":
            try: message_text = translate_ru_to_ua(base_message_text)
            except Exception as e: print(f"Error translating message for {group_name}: {e}.")
        media_files_opened: List[BytesIO] = []
        try:
            if potential_total_media < MIN_MEDIA_FOR_GROUP_STRATEGY:
                print(f"Strategy 1: Sending cover/thumb separately (potential media: {potential_total_media} < {MIN_MEDIA_FOR_GROUP_STRATEGY}).")
                caption_for_photo = ""; remaining_text = message_text; primary_photo_sent = False
                # Try sending Cover first
                if cover_image_file:
                    print("Strategy 1: Sending cover image...")
                    cover_image_file.seek(0); caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
                    caption_for_photo = caption_parts[0] if caption_parts else ""; remaining_text = "\n".join(caption_parts[1:])
                    bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=cover_image_file, caption=caption_for_photo, parse_mode="HTML"); time.sleep(1)
                    primary_photo_sent = True
                # If no cover, try sending Thumbnail
                elif trailer_thumbnail_file:
                    print("Strategy 1: No cover, sending trailer thumbnail...")
                    trailer_thumbnail_file.seek(0); caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
                    caption_for_photo = caption_parts[0] if caption_parts else ""; remaining_text = "\n".join(caption_parts[1:])
                    bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=trailer_thumbnail_file, caption=caption_for_photo, parse_mode="HTML"); time.sleep(1)
                    primary_photo_sent = True
                # Send Remaining Text
                if remaining_text.strip():
                    disable_first_preview = primary_photo_sent
                    message_parts = split_text(remaining_text, MAX_MESSAGE_LENGTH)
                    for i, part in enumerate(message_parts): bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=part, parse_mode="HTML", disable_web_page_preview=(disable_first_preview or i > 0)); time.sleep(1)
                # Send ONLY Screenshots (no thumb here, as it was sent as primary if available)
                if local_screenshot_paths:
                    screenshot_media_group: List[InputMediaPhoto] = []; screenshots_added_count = 0
                    for file_path in local_screenshot_paths:
                        if len(screenshot_media_group) >= MAX_MEDIA_GROUP_SIZE: break
                        if not os.path.exists(file_path): continue
                        try: file_handle = open(file_path, 'rb'); media_files_opened.append(file_handle); screenshot_media_group.append(InputMediaPhoto(media=file_handle)); screenshots_added_count += 1
                        except Exception as open_err: print(f"Error opening screenshot file {file_path}: {open_err}")
                    if screenshot_media_group:
                        print(f"Sending screenshot-only media group ({screenshots_added_count} items)...")
                        bot.send_media_group(chat_id=chat_id, message_thread_id=topic_id, media=screenshot_media_group); time.sleep(2)
            else:
                # Strategy 2: Combined Media Group
                print(f"Strategy 2: Sending combined media group/photo (potential media: {potential_total_media}).")
                media_group_to_send: List[InputMediaPhoto] = []
                caption_for_group = ""; remaining_text_group = message_text
                # Build the group (order depends on thumbnail resolution)
                if is_max_res_thumbnail and trailer_thumbnail_file:
                    trailer_thumbnail_file.seek(0); media_group_to_send.append(InputMediaPhoto(media=trailer_thumbnail_file))
                    if cover_image_file and len(media_group_to_send) < MAX_MEDIA_GROUP_SIZE: cover_image_file.seek(0); media_group_to_send.append(InputMediaPhoto(media=cover_image_file))
                else:
                     if cover_image_file: cover_image_file.seek(0); media_group_to_send.append(InputMediaPhoto(media=cover_image_file))
                     if trailer_thumbnail_file and len(media_group_to_send) < MAX_MEDIA_GROUP_SIZE: trailer_thumbnail_file.seek(0); media_group_to_send.append(InputMediaPhoto(media=trailer_thumbnail_file))
                # Add Screenshots
                if local_screenshot_paths:
                    screenshots_added_count = 0
                    for file_path in local_screenshot_paths:
                        if len(media_group_to_send) >= MAX_MEDIA_GROUP_SIZE: break
                        if not os.path.exists(file_path): continue
                        try: file_handle = open(file_path, 'rb'); media_files_opened.append(file_handle); media_group_to_send.append(InputMediaPhoto(media=file_handle)); screenshots_added_count += 1
                        except Exception as open_err: print(f"Error opening screenshot file {file_path}: {open_err}")
                # Assign Caption
                if media_group_to_send:
                    caption_parts = split_text(message_text, MAX_CAPTION_LENGTH)
                    if caption_parts:
                        caption_for_group = caption_parts[0]; remaining_text_group = "\n".join(caption_parts[1:])
                        media_group_to_send[0].caption = caption_for_group; media_group_to_send[0].parse_mode = "HTML"
                    else: remaining_text_group = ""
                    # Send Media Group or Single Photo
                    if len(media_group_to_send) > 1:
                        print(f"Sending media group ({len(media_group_to_send)} items)...")
                        bot.send_media_group(chat_id=chat_id, message_thread_id=topic_id, media=media_group_to_send); time.sleep(2)
                    elif len(media_group_to_send) == 1:
                        print("Sending single photo...")
                        single_media_obj = media_group_to_send[0]; media_content = single_media_obj.media
                        media_content.seek(0)
                        bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=media_content, caption=single_media_obj.caption, parse_mode="HTML"); time.sleep(1)
                # Send Remaining Text
                if remaining_text_group.strip():
                    message_parts = split_text(remaining_text_group, MAX_MESSAGE_LENGTH)
                    for i, part in enumerate(message_parts):
                         bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=part, parse_mode="HTML", disable_web_page_preview=True); time.sleep(1)
        except Exception as e:
            print(f"!!! Failed to send message to group {group_name}: {type(e).__name__}: {e}")
            if LOG: traceback.print_exc()
            error_info = f"Failed sending to {group_name}: {type(e).__name__}: {e}";
            if hasattr(e, 'result_json'): error_info += f"\nAPI Response: {str(e.result_json)[:200]}..."
            send_error_to_telegram(error_info)
        finally:
             for f in media_files_opened:
                  try: f.close()
                  except Exception as close_err: print(f"Error closing screenshot file handle: {close_err}")
        time.sleep(2)

# --- Other sender functions ---
def send_message_to_admin(message: str):
    global bot
    # --- FIX: Separated checks ---
    if not bot:
        print("ERROR in send_message_to_admin: Bot not initialized.")
        return
    if not ERROR_TG:
        # print("No ERROR_TG configured. Admin message not sent.") # Keep silent if no error group
        return
    # ---------------------------
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
    temp_message = error_message.strip(); max_error_len = 4000
    if temp_message.startswith("<pre>") and temp_message.endswith("</pre>"): formatted_message = temp_message
    elif "Traceback" in error_message or "Error type" in error_message or "Stack Trace" in error_message:
        escaped_message = html.escape(error_message); formatted_message = f"<pre>{escaped_message}</pre>"
    else: formatted_message = html.escape(error_message)
    if len(formatted_message) > max_error_len: formatted_message = formatted_message[:max_error_len] + "\n... (message truncated)"
    send_message_to_admin(f"❗ Bot Error:\n\n{formatted_message}")
def notify_mismatched_trailer(searched_title: str, found_title: str, trailer_url: str):
    message = (f"⚠️ YouTube Search Warning:\n\n" f"Searched: <code>{html.escape(searched_title)}</code>\n" f"Found: <code>{html.escape(found_title)}</code>\n" f"URL: {trailer_url}\n\n" f"Title mismatch.")
    send_message_to_admin(message)

# --- Testing Block ---
if __name__ == "__main__":
    print("--- Running telegram_sender.py Tests ---")
    try:
        from settings_loader import GROUPS as LOADED_GROUPS, TOKEN as LOADED_TOKEN, LOG as LOADED_LOG, current_directory
        TOKEN = LOADED_TOKEN; GROUPS = LOADED_GROUPS; LOG = LOADED_LOG; print("Using settings loaded via settings_loader.")
    except ImportError:
        print("settings_loader not found, using dummy values for test.")
        TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN"); GROUPS = [] ; LOG = True; current_directory = os.path.dirname(os.path.abspath(__file__))
    if not bot and TOKEN:
        print("Initializing bot for testing...")
        import telebot
        try: bot = telebot.TeleBot(TOKEN); bot_info = bot.get_me(); print(f"Test Bot initialized: {bot_info.username}")
        except Exception as e: print(f"Failed to initialize bot for testing: {e}"); bot = None
    elif bot: print("Bot already initialized.")
    else: print("Skipping tests: Bot TOKEN not available and bot not initialized."); exit()
    TEST_CHAT_ID = None
    if GROUPS: TEST_CHAT_ID = GROUPS[0].get('chat_id'); print(f"Using Chat ID from first group in settings: {TEST_CHAT_ID}")
    else:
        YOUR_FALLBACK_TEST_CHAT_ID = -1001960832921 # !!! REPLACE IF NEEDED !!!
        TEST_CHAT_ID = YOUR_FALLBACK_TEST_CHAT_ID; print(f"WARNING: No groups in settings. Using fallback TEST_CHAT_ID: {TEST_CHAT_ID}")
        GROUPS = [{"group_name": "Direct Test Group", "chat_id": TEST_CHAT_ID, "language": "RU"}]
    if not TEST_CHAT_ID: print("ERROR: Could not determine a valid TEST_CHAT_ID. Exiting tests."); exit()
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SCREENSHOT_SOURCE_DIR = os.path.join(_SCRIPT_DIR, "tmp_screenshots")
    existing_screenshots = []
    if os.path.isdir(SCREENSHOT_SOURCE_DIR):
        print(f"Looking for existing screenshot files in: {SCREENSHOT_SOURCE_DIR}")
        for fname in sorted(os.listdir(SCREENSHOT_SOURCE_DIR)):
            fpath = os.path.join(SCREENSHOT_SOURCE_DIR, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')): existing_screenshots.append(fpath)
        print(f"Found {len(existing_screenshots)} existing screenshot files.")
    else: print(f"WARNING: Screenshot source directory not found: {SCREENSHOT_SOURCE_DIR}.")
    if not existing_screenshots: print("WARNING: No screenshot files found for testing media groups.")
    test_cover_url = "https://i1.imageban.ru/out/2023/06/23/848f9247616ca84bfb98304f718f5799.png"
    test_trailer_vid_id_hq = "dQw4w9WgXcQ"; test_trailer_vid_id_no_maxres = "o4GyQEXXzHU"
    test_magnet = "magnet:?xt=urn:btih:TESTHASH"
    test_desc_short = "Это <b>короткое</b> тестовое описание."; test_desc_long = "Это <b>первая часть</b> очень длинного описания. " + ("тестовый текст " * 150) + "\n\nА это <i>вторая часть</i> после переноса строки.\n\n" + ("ещё тестовый текст " * 150) + " Конец."
    scenarios = [
        {"name": "Test 1 (Strat 1): Cover + 2 SS (Short)", "cover": test_cover_url, "vid_id": None, "ss_count": 2, "desc": test_desc_short},
        {"name": "Test 2 (Strat 1): No Cover + HQ Thumb + 3 SS (Short)", "cover": None, "vid_id": test_trailer_vid_id_hq, "ss_count": 3, "desc": test_desc_short},
        {"name": "Test 3 (Strat 1): Cover Only (Short)", "cover": test_cover_url, "vid_id": None, "ss_count": 0, "desc": test_desc_short},
        {"name": "Test 4 (Strat 1): HQ Thumb + 1 SS (Short)", "cover": None, "vid_id": test_trailer_vid_id_hq, "ss_count": 1, "desc": test_desc_short},
        {"name": "Test 5 (Strat 2): Cover + MaxRes Thumb + 4 SS (Short)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_hq, "ss_count": 4, "desc": test_desc_short},
        {"name": "Test 6 (Strat 2): Cover + SD Thumb + 5 SS (Short)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_no_maxres, "ss_count": 5, "desc": test_desc_short},
        {"name": "Test 7 (Strat 2): Cover + 7 SS (No Trailer) (Short)", "cover": test_cover_url, "vid_id": None, "ss_count": 7, "desc": test_desc_short},
        {"name": "Test 8 (Text Only) (Short Desc)", "cover": None, "vid_id": None, "ss_count": 0, "desc": test_desc_short},
        {"name": "Test 9 (Strat 1): Cover + 2 SS (Long Desc)", "cover": test_cover_url, "vid_id": None, "ss_count": 2, "desc": test_desc_long},
        {"name": "Test 10 (Strat 2): Cover + MaxRes + 4 SS (Long Desc)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_hq, "ss_count": 4, "desc": test_desc_long},
    ]
    for i, scenario in enumerate(scenarios):
        print(f"\n--- Running Scenario {i+1}: {scenario['name']} ---")
        time.sleep(5)
        title_link_html = f'<a href="http://example.com/test/{i+1}">{html.escape(scenario["name"])}</a>'
        title_with_trailer = title_link_html + (f' | <a href="https://www.youtube.com/watch?v={scenario["vid_id"]}">Trailer</a>' if scenario.get("vid_id") else "")
        description_to_use = scenario.get("desc", test_desc_short)
        screenshots_to_use = existing_screenshots[:min(scenario["ss_count"], len(existing_screenshots))]
        if scenario["ss_count"] > 0 and not screenshots_to_use: print(f"WARNING: Scenario requires {scenario['ss_count']} screenshots, but none were found/available.")
        send_to_telegram(
            title_for_caption=title_with_trailer, cover_image_url=scenario["cover"], magnet_link=test_magnet,
            description=description_to_use, video_id_for_thumbnail=scenario["vid_id"], local_screenshot_paths=screenshots_to_use
        )
        print(f"--- Finished Scenario {i+1} ---")
        if i < len(scenarios) - 1: print("Pausing for 15 seconds..."); time.sleep(15)

# --- END OF FILE telegram_sender.py ---