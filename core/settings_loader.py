import sys
import os
import json
import logging
from typing import Dict, Optional, Any, List
from telebot.async_telebot import AsyncTeleBot
from openai import AsyncOpenAI
import aiohttp
from core.logger_setup import setup_logging

# Function load_config remains the same
def load_config(file_path: str) -> Optional[Dict[str, Any]]:
    """Loads configuration from a JSON file."""
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except json.JSONDecodeError as e: logging.error(f'Error loading config file {file_path}: {e}'); sys.exit(f"Invalid JSON in {file_path}")
    except Exception as e: logging.error(f'An unexpected error occurred loading {file_path}: {e}'); sys.exit(f"Could not load {file_path}")

# Function get_env_or_setting remains the same
def get_env_or_setting(settings_dict: Dict[str, Any], key: str, env_var: str) -> Optional[Any]: # Return Any to handle bools
    """Gets value from settings dict or environment variable."""
    value = settings_dict.get(key)
    placeholder = f"os.environ['{env_var}']"
    if isinstance(value, str) and value == placeholder:
        env_value = os.environ.get(env_var)
        if not env_value:
            if key in ['DEEPL_API_KEY', 'YOUTUBE_API_KEY']: # Make optional keys explicit
                 # logging.info(f"Setting '{key}' uses env var '{env_var}' which is not set. Feature disabled.")
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
            logging.warning(f"Setting '{key}' not found in config, using environment variable {env_var}.")
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
# Project root is one level up from core/
current_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
# LOG flag is needed for logging initialization
LOG = settings.get('LOG', False)
if isinstance(LOG, str): LOG = LOG.lower() == 'true' # Ensure boolean

# Initialize logging immediately after determining LOG flag
log_level = logging.DEBUG if LOG else logging.INFO
setup_logging(log_level=log_level)

logging.info(f"Final Mode - IS_TEST_MODE: {IS_TEST_MODE}")

TOKEN = get_env_or_setting(settings, 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_TOKEN')
OPENAI_BASE_URL = settings.get('OPENAI_BASE_URL')  # Optional: for localhost/custom OpenAI-compatible APIs
OPENAI_API_KEY = get_env_or_setting(settings, 'OPENAI_API', 'OPENAI_API_KEY') if not OPENAI_BASE_URL else None
FEED_URL = settings.get('FEED_URL', 'https://feed.rutracker.cc/atom/f/1605.atom')
YOUTUBE_API_KEY = get_env_or_setting(settings, 'YOUTUBE_API_KEY', 'YOUTUBE_API_KEY')
DEEPL_API_KEY = get_env_or_setting(settings, 'DEEPL_API_KEY', 'DEEPL_API_KEY')

GROUPS = settings.get('GROUPS', [])
ERROR_TG = settings.get('ERROR_TG', [])
# Get the test link ONLY if in test mode
TEST_LAST_ENTRY_LINK = settings.get('test_last_entry_link') if IS_TEST_MODE else None

# --- Validate Critical Settings ---
if not TOKEN: logging.critical("TELEGRAM_BOT_TOKEN is not configured."); sys.exit("Error: TELEGRAM_BOT_TOKEN is not configured.")
if not OPENAI_API_KEY and not OPENAI_BASE_URL: logging.warning("OPENAI_API_KEY and OPENAI_BASE_URL not configured. GPT translation disabled.")

# Set Google credentials path
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
if not os.path.exists(credentials_path):
     logging.warning(f"Google credentials file ({credentials_path}) not found. Google services might fail.")

# --- Initialize API Clients ---
try:
    bot = AsyncTeleBot(TOKEN)
    logging.info(f"Telegram AsyncBot initialized with token ending in ...{TOKEN[-5:]}")
except Exception as e: logging.error(f"Error initializing Telegram Bot: {e}"); sys.exit(f"Error initializing Telegram Bot: {e}")

openai_client: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY or OPENAI_BASE_URL:
    try:
        # Initialize with base_url if provided (for localhost/custom OpenAI-compatible APIs)
        if OPENAI_BASE_URL:
            # For localhost, use empty string as API key (SDK will skip Authorization header)
            openai_client = AsyncOpenAI(api_key="", base_url=OPENAI_BASE_URL, default_headers={})
            logging.info(f"OpenAI Async client initialized with custom base_url: {OPENAI_BASE_URL}")
        else:
            openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            logging.info("OpenAI Async client initialized.")
    except Exception as e: logging.warning(f"Error initializing OpenAI client: {e}. GPT functions disabled.")
else: logging.info("OpenAI client not initialized (no API key or base_url).")

# --- Shared aiohttp Session ---
app_session: Optional[aiohttp.ClientSession] = None

def get_session() -> aiohttp.ClientSession:
    """Returns the shared aiohttp.ClientSession, initializing it if necessary."""
    global app_session
    if app_session is None or app_session.closed:
        headers = {'User-Agent': 'Mozilla/5.0 RutrackerBot/1.0'}
        app_session = aiohttp.ClientSession(headers=headers)
        logging.info("Shared aiohttp ClientSession initialized.")
    return app_session

# --- Cleanup ---
async def close_clients():
    """Closes all initialized API clients."""
    if 'bot' in globals() and bot:
        try:
            await bot.close_session()
            logging.info("Telegram AsyncBot session closed.")
        except Exception as e:
            logging.error(f"Error closing Telegram Bot session: {e}")

    global openai_client
    if openai_client:
        try:
            await openai_client.close()
            logging.info("OpenAI Async client closed.")
        except Exception as e:
            logging.error(f"Error closing OpenAI client: {e}")

    global app_session
    if app_session and not app_session.closed:
        try:
            await app_session.close()
            logging.info("Shared aiohttp ClientSession closed.")
        except Exception as e:
            logging.error(f"Error closing shared aiohttp session: {e}")

# Warnings about GROUPS/ERROR_TG
if not GROUPS: logging.warning("No 'GROUPS' defined in settings. Posting to groups will not work.")
if not ERROR_TG: logging.warning("No 'ERROR_TG' defined in settings. Error notifications disabled.")
