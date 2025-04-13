# --- START OF FILE test_telegram_sender.py ---
import os
import time
import html
import traceback
from typing import List, Optional, Dict, Any
from io import BytesIO # Needed for potential type hints if used directly

# --- Mock or import necessary components ---
# Try importing real components first
try:
    from settings_loader import GROUPS as LOADED_GROUPS, ERROR_TG as LOADED_ERROR_TG, TOKEN as LOADED_TOKEN, LOG as LOADED_LOG, bot as actual_bot, current_directory
    from telegram_sender import send_to_telegram, send_message_to_admin, send_error_to_telegram, notify_mismatched_trailer
    from telegram_utils import download_cover_image_tg, download_trailer_thumbnail_tg # Need these for testing setup
    import telebot # Need this if we initialize the bot here
    print("Using real components imported from project files.")
    bot = actual_bot # Use the bot initialized in settings_loader if available
    TOKEN = LOADED_TOKEN
    GROUPS = LOADED_GROUPS
    ERROR_TG = LOADED_ERROR_TG
    LOG = LOADED_LOG
except ImportError as e:
    print(f"ImportError: {e}. Setting up dummy components for testing.")
    # Define dummy components if imports fail (e.g., running standalone)
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    LOG = True
    GROUPS: List[Dict[str, Any]] = []
    ERROR_TG: List[Dict[str, Any]] = []
    bot = None # No bot instance
    current_directory = os.path.dirname(os.path.abspath(__file__))

    # Define dummy functions to avoid NameError
    def send_to_telegram(*args, **kwargs): print("Dummy send_to_telegram called.")
    def send_message_to_admin(*args, **kwargs): print("Dummy send_message_to_admin called.")
    def send_error_to_telegram(*args, **kwargs): print("Dummy send_error_to_telegram called.")
    def notify_mismatched_trailer(*args, **kwargs): print("Dummy notify_mismatched_trailer called.")
    def download_cover_image_tg(*args, **kwargs) -> Optional[BytesIO]: print("Dummy download_cover_image_tg called."); return None
    def download_trailer_thumbnail_tg(*args, **kwargs) -> Tuple[Optional[BytesIO], Optional[str]]: print("Dummy download_trailer_thumbnail_tg called."); return None, None
    print("WARNING: Running with dummy functions. No actual Telegram messages will be sent.")

# --- Test Execution Block ---
if __name__ == "__main__":
    print("--- Running telegram_sender.py Tests ---")

    # Initialize bot if needed (and not already done by settings_loader)
    if not bot and TOKEN:
        print("Initializing bot for testing...")
        try:
            if 'telebot' not in locals(): import telebot # Import if not already imported
            bot = telebot.TeleBot(TOKEN)
            bot_info = bot.get_me()
            print(f"Test Bot initialized: {bot_info.username}")
            # IMPORTANT: If using dummy functions above, the real bot won't be used.
            # You might need to re-import the real functions here if you want actual sending.
            # This setup assumes settings_loader provides the *real* bot instance.
        except Exception as e:
            print(f"Failed to initialize bot for testing: {e}")
            bot = None # Ensure bot is None if initialization fails
    elif bot:
        print(f"Bot '{bot.get_me().username}' already initialized (likely via settings_loader).")
    else:
        print("Skipping tests: Bot TOKEN not available and bot not initialized.")
        exit()

    # Determine Test Chat ID
    # Use the first group from GROUPS if available, otherwise use a hardcoded fallback
    TEST_CHAT_ID = None
    if GROUPS:
        TEST_CHAT_ID = GROUPS[0].get('chat_id')
        print(f"Using Chat ID from first group in settings: {TEST_CHAT_ID}")
    else:
        # !!! --- IMPORTANT: SET A VALID TEST CHAT ID HERE --- !!!
        YOUR_FALLBACK_TEST_CHAT_ID = -1001960832921 # Replace with your test chat/group ID
        # !!! --------------------------------------------- !!!
        TEST_CHAT_ID = YOUR_FALLBACK_TEST_CHAT_ID
        print(f"WARNING: No groups in settings. Using fallback TEST_CHAT_ID: {TEST_CHAT_ID}")
        # Ensure GROUPS has at least one entry for the loop in send_to_telegram
        if not GROUPS: # Add if it's completely empty
            GROUPS = [{"group_name": "Direct Test Group", "chat_id": TEST_CHAT_ID, "language": "RU"}]

    if not TEST_CHAT_ID:
        print("ERROR: Could not determine a valid TEST_CHAT_ID. Exiting tests.")
        exit()

    # Find existing screenshots in the standard temporary directory
    _SCRIPT_DIR = current_directory # Use directory from settings_loader or fallback
    SCREENSHOT_SOURCE_DIR = os.path.join(_SCRIPT_DIR, "tmp_screenshots") # Standard temp dir
    existing_screenshots: List[str] = []
    if os.path.isdir(SCREENSHOT_SOURCE_DIR):
        print(f"Looking for existing screenshot files in: {SCREENSHOT_SOURCE_DIR}")
        try:
            # List files and filter for common image extensions
            for fname in sorted(os.listdir(SCREENSHOT_SOURCE_DIR)):
                fpath = os.path.join(SCREENSHOT_SOURCE_DIR, fname)
                if os.path.isfile(fpath) and fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    existing_screenshots.append(fpath)
            print(f"Found {len(existing_screenshots)} existing screenshot files.")
        except Exception as e:
            print(f"Error listing screenshot directory '{SCREENSHOT_SOURCE_DIR}': {e}")
    else:
        print(f"WARNING: Screenshot source directory not found: {SCREENSHOT_SOURCE_DIR}. Some tests may lack screenshots.")

    if not existing_screenshots:
        print("WARNING: No screenshot files found for testing media groups.")

    # Test Data (same as before)
    test_cover_url = "https://i1.imageban.ru/out/2023/06/23/848f9247616ca84bfb98304f718f5799.png" # Example cover
    test_trailer_vid_id_hq = "dQw4w9WgXcQ" # Has maxresdefault
    test_trailer_vid_id_no_maxres = "o4GyQEXXzHU" # Likely no maxresdefault
    test_magnet = "magnet:?xt=urn:btih:THISISATESTHASHONLY1234567890"
    test_desc_short = "Это <b>короткое</b> тестовое описание с <i>форматированием</i> и <a href='http://example.com'>ссылкой</a>. [Test Script]"
    test_desc_long = "Это <b>первая часть</b> очень длинного описания. [Test Script] " + ("тестовый текст bla bla bla " * 150) + "\n\nА это <i>вторая часть</i> после переноса строки.\n\n<tg-spoiler>Скрытый текст</tg-spoiler>\n\n" + ("ещё тестовый текст ля ля ля " * 150) + " Конец <code>кода</code>."

    # Define Scenarios (same as before)
    scenarios = [
        {"name": "Test 1 (Strat 1): Cover + 2 SS (Short Desc)", "cover": test_cover_url, "vid_id": None, "ss_count": 2, "desc": test_desc_short},
        {"name": "Test 2 (Strat 1): No Cover + HQ Thumb (maxres) + 3 SS (Short Desc)", "cover": None, "vid_id": test_trailer_vid_id_hq, "ss_count": 3, "desc": test_desc_short},
        {"name": "Test 3 (Strat 1): Cover Only (Short Desc)", "cover": test_cover_url, "vid_id": None, "ss_count": 0, "desc": test_desc_short},
        {"name": "Test 4 (Strat 1): SD Thumb (no maxres) + 1 SS (Short Desc)", "cover": None, "vid_id": test_trailer_vid_id_no_maxres, "ss_count": 1, "desc": test_desc_short},

        {"name": "Test 5 (Strat 2): Cover + MaxRes Thumb + 4 SS (Short Desc)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_hq, "ss_count": 4, "desc": test_desc_short},
        {"name": "Test 6 (Strat 2): Cover + SD Thumb + 5 SS (Short Desc)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_no_maxres, "ss_count": 5, "desc": test_desc_short},
        {"name": "Test 7 (Strat 2): Cover + 7 SS (No Trailer) (Short Desc)", "cover": test_cover_url, "vid_id": None, "ss_count": 7, "desc": test_desc_short},
        {"name": "Test 8 (Text Only) (Short Desc)", "cover": None, "vid_id": None, "ss_count": 0, "desc": test_desc_short},

        {"name": "Test 9 (Strat 1): Cover + 2 SS (Long Desc)", "cover": test_cover_url, "vid_id": None, "ss_count": 2, "desc": test_desc_long},
        {"name": "Test 10 (Strat 2): Cover + MaxRes Thumb + 4 SS (Long Desc)", "cover": test_cover_url, "vid_id": test_trailer_vid_id_hq, "ss_count": 4, "desc": test_desc_long},
        {"name": "Test 11 (Strat 2): MaxRes Thumb + 8 SS (No Cover) (Long Desc)", "cover": None, "vid_id": test_trailer_vid_id_hq, "ss_count": 8, "desc": test_desc_long},
        {"name": "Test 12 (Strat 2): SD Thumb + 10 SS (No Cover) (Long Desc - Media Limit)", "cover": None, "vid_id": test_trailer_vid_id_no_maxres, "ss_count": 10, "desc": test_desc_long},
        {"name": "Test 13 (Error): Invalid Cover URL (Short Desc)", "cover": "http://invalid-url-that-does-not-exist-12345.xyz/image.jpg", "vid_id": None, "ss_count": 1, "desc": test_desc_short},
        {"name": "Test 14 (Error): Invalid Video ID (Short Desc)", "cover": test_cover_url, "vid_id": "InvalidIDDefinitely", "ss_count": 1, "desc": test_desc_short},
    ]

    # Run Scenarios
    print("\n--- STARTING TEST SCENARIOS ---")
    total_scenarios = len(scenarios)
    for i, scenario in enumerate(scenarios):
        print(f"\n--- Running Scenario {i+1}/{total_scenarios}: {scenario['name']} ---")
        time.sleep(5) # Give time to read logs before execution

        # Prepare data for the scenario
        title_link_html = f'<a href="http://example.com/test/{i+1}">{html.escape(scenario["name"])}</a>'
        title_with_trailer = title_link_html
        # Add trailer link only if video ID seems valid
        if scenario.get("vid_id") and "Invalid" not in scenario["vid_id"]:
             title_with_trailer += f' | <a href="https://www.youtube.com/watch?v={scenario["vid_id"]}">Trailer</a>'

        description_to_use = scenario.get("desc", test_desc_short)

        # Select screenshots for the current test
        screenshots_to_use = existing_screenshots[:min(scenario["ss_count"], len(existing_screenshots))]
        if scenario["ss_count"] > 0 and not screenshots_to_use:
            print(f"WARNING: Scenario requires {scenario['ss_count']} screenshots, but none were found/available.")
        elif scenario["ss_count"] > len(existing_screenshots):
             print(f"WARNING: Scenario requires {scenario['ss_count']} screenshots, but only {len(existing_screenshots)} were found/available.")

        # Execute the main function being tested
        try:
            # Make sure you are calling the *actual* send_to_telegram function
            # If using dummy setup, this call might go to the dummy function
            send_to_telegram(
                title_for_caption=title_with_trailer,
                cover_image_url=scenario.get("cover"),
                magnet_link=test_magnet,
                description=description_to_use,
                video_id_for_thumbnail=scenario.get("vid_id"),
                local_screenshot_paths=screenshots_to_use
            )
            print(f"--- Scenario {i+1} completed (check Telegram) ---")
        except Exception as test_err:
            print(f"!!! ERROR during test scenario {i+1}: {test_err} !!!")
            traceback.print_exc()
            # Optionally send an error message to admin channel during testing
            # send_error_to_telegram(f"Error in Test Scenario {i+1}: {test_err}")

        # Pause between tests to avoid hitting rate limits and allow observation
        if i < total_scenarios - 1:
            pause_duration = 15
            print(f"Pausing for {pause_duration} seconds...")
            time.sleep(pause_duration)

    print("\n--- ALL TEST SCENARIOS FINISHED ---")

# --- END OF FILE test_telegram_sender.py ---