import sys
import os
import json
import telebot
from openai import OpenAI
from typing import Dict, Optional, Any, List # Import typing

# Function load_config remains the same
def load_config(file_path: str) -> Optional[Dict[str, Any]]:
    """Loads configuration from a JSON file."""
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except json.JSONDecodeError as e: print(f'Error loading config file {file_path}: {e}'); sys.exit(f"Invalid JSON in {file_path}")
    except Exception as e: print(f'An unexpected error occurred loading {file_path}: {e}'); sys.exit(f"Could not load {file_path}")

# Function get_env_or_setting remains the same
def get_env_or_setting(settings_dict: Dict[str, Any], key: str, env_var: str) -> Optional[Any]: # Return Any to handle bools
    """Gets value from settings dict or environment variable."""
    value = settings_dict.get(key)
    placeholder = f"os.environ['{env_var}']"
    if isinstance(value, str) and value == placeholder:
        env_value = os.environ.get(env_var)
        if not env_value:
            if key in ['DEEPL_API_KEY', 'YOUTUBE_API_KEY']: # Make optional keys explicit
                 # print(f"Info: Setting '{key}' uses env var '{env_var}' which is not set. Feature disabled.")
                 return None
            sys.exit(f"Error: Environment variable {env_var} is not set, and setting '{key}' requires it.")
        return env_value
    elif value is None:
        # Only try env var for specific critical keys if value is None
        if key in ['TELEGRAM_BOT_TOKEN', 'OPENAI_API']:
            env_value = os.environ.get(env_var)
            if not env_value:
                 if key == 'OPENAI_API' and settings_dict.get('OPENAI_API_KEY'): return settings_dict.get('OPENAI_API_KEY')
                 sys.exit(f"Error: Setting '{key}' is missing in config and environment variable {env_var} is not set.")
            print(f"Warning: Setting '{key}' not found in config, using environment variable {env_var}.")
            return env_value
        # Provide defaults or None for non-critical keys
        elif key == 'FEED_URL': return 'https://feed.rutracker.cc/atom/f/1605.atom' # Default even if None
        elif key == 'LOG': return False
        elif key == 'test': return False
        else: return None # Includes DEEPL_API_KEY, YOUTUBE_API_KEY if explicitly null
    # Handle boolean conversion for LOG/test if they are strings
    if key in ['LOG', 'test'] and isinstance(value, str): return value.lower() == 'true'
    # Return value as is (could be bool, list, dict, string, etc.)
    return value

# --- Configuration Loading ---
current_directory = os.path.dirname(os.path.abspath(__file__))
default_settings_path = os.path.join(current_directory, 'settings.json')
test_settings_path = os.path.join(current_directory, 'test_settings.json')
local_settings_path = os.path.join(current_directory, 'local_settings.json')
credentials_path = os.path.join(current_directory, 'credentials.json')
last_entry_file_path = os.path.join(current_directory, "last_entry.txt")

# --- NEW Settings Loading Logic ---
settings: Optional[Dict[str, Any]] = None
IS_TEST_MODE = False

# Try loading test_settings.json first
test_cfg = load_config(test_settings_path)
if test_cfg is not None:
    print("--- Loading TEST settings from test_settings.json ---")
    settings = test_cfg
    IS_TEST_MODE = True # Force test mode if test_settings.json exists
else:
    # If test_settings.json not found, load default and then local
    print("--- Loading PRODUCTION/LOCAL settings (test_settings.json not found) ---")
    settings = {}
    default_cfg = load_config(default_settings_path)
    if default_cfg:
        settings.update(default_cfg)
    else:
         print("Warning: settings.json (default config) not found.")
         # sys.exit("Error: Default settings file (settings.json) not found.") # Optionally exit if default is required

    local_cfg = load_config(local_settings_path)
    if local_cfg:
        print("Info: local_settings.json found, overriding defaults.")
        settings.update(local_cfg) # Local overrides default

    # Determine test mode based on the 'test' flag in the final loaded settings
    IS_TEST_MODE = settings.get('test', False)
    # Convert string 'true'/'false' to boolean for test flag if necessary
    if isinstance(IS_TEST_MODE, str): IS_TEST_MODE = IS_TEST_MODE.lower() == 'true'


if not settings:
    sys.exit("Error: No configuration settings could be loaded.")

# --- Extract Settings using the final 'settings' dictionary ---
print(f"Final Mode - IS_TEST_MODE: {IS_TEST_MODE}")

TOKEN = get_env_or_setting(settings, 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = get_env_or_setting(settings, 'OPENAI_API', 'OPENAI_API_KEY')
FEED_URL = settings.get('FEED_URL', 'https://feed.rutracker.cc/atom/f/1605.atom') # Still need feed url for production
YOUTUBE_API_KEY = get_env_or_setting(settings, 'YOUTUBE_API_KEY', 'YOUTUBE_API_KEY')
DEEPL_API_KEY = get_env_or_setting(settings, 'DEEPL_API_KEY', 'DEEPL_API_KEY')
LOG = settings.get('LOG', False)
if isinstance(LOG, str): LOG = LOG.lower() == 'true' # Ensure boolean

GROUPS = settings.get('GROUPS', [])
ERROR_TG = settings.get('ERROR_TG', [])
# Get the test link ONLY if in test mode
TEST_LAST_ENTRY_LINK = settings.get('test_last_entry_link') if IS_TEST_MODE else None

# --- Validate Critical Settings ---
if not TOKEN: sys.exit("Error: TELEGRAM_BOT_TOKEN is not configured.")
if not OPENAI_API_KEY: print("Warning: OPENAI_API_KEY not configured. GPT translation disabled.")
# YouTube API key validation moved to where it's used, as it's optional

# Set Google credentials path
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
if not os.path.exists(credentials_path):
     print(f"Warning: Google credentials file ({credentials_path}) not found. Google services might fail.")

# --- Initialize API Clients ---
try:
    bot = telebot.TeleBot(TOKEN)
    bot_info = bot.get_me(); print(f"Telegram Bot initialized: {bot_info.username}")
except Exception as e: sys.exit(f"Error initializing Telegram Bot: {e}")

openai_client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    try: openai_client = OpenAI(api_key=OPENAI_API_KEY); print("OpenAI client initialized.")
    except Exception as e: print(f"Warning: Error initializing OpenAI client: {e}. GPT functions disabled.")
else: print("OpenAI client not initialized (no API key).")

# Warnings about GROUPS/ERROR_TG
if not GROUPS: print("Warning: No 'GROUPS' defined in settings. Posting to groups will not work.")
if not ERROR_TG: print("Warning: No 'ERROR_TG' defined in settings. Error notifications disabled.")
