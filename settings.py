import sys
import os
import json
import telebot
import openai

def load_config(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f'Error loading config file {file}:', e)
        sys.exit(1)

current_directory = os.path.dirname(os.path.abspath(__file__))

settings = load_config(os.path.join(current_directory, 'settings.json'))
settings = load_config(os.path.join(current_directory, 'test_settings.json'))
settings = load_config(os.path.join(current_directory, 'local_settings.json'))

TOKEN = os.environ['TELEGRAM_BOT_TOKEN'] if settings['TELEGRAM_BOT_TOKEN'] == "os.environ['TELEGRAM_BOT_TOKEN']" else settings['TELEGRAM_BOT_TOKEN']
FEED_URL = settings['FEED_URL']
LAST_ENTRY_FILE = os.path.join(current_directory, "last_entry.txt")
openai.api_key = os.environ['OPENAI_API'] if settings['OPENAI_API'] == "os.environ['OPENAI_API']" else settings['OPENAI_API']
openai.Model.list()
bot = telebot.TeleBot(TOKEN)
YOUTUBE_API_KEY = os.environ['YOUTUBE_API_KEY'] if settings['YOUTUBE_API_KEY'] == "os.environ['YOUTUBE_API_KEY']" else settings['YOUTUBE_API_KEY']
DEEPL_API_KEY = os.environ['DEEPL_API_KEY'] if settings['DEEPL_API_KEY'] == "os.environ['DEEPL_API_KEY']" else settings['DEEPL_API_KEY']
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
LOG = settings['LOG']