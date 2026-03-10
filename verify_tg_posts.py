# verify_tg_posts.py
import time
import telebot
import os
import json
import html

# Load config to get token
current_directory = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(current_directory, 'test_settings.json')
if not os.path.exists(settings_path):
    settings_path = os.path.join(current_directory, 'settings.json')

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

TOKEN = settings.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("Error: No token found.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

def get_latest_messages(limit=10):
    try:
        updates = bot.get_updates(offset=-limit, limit=limit, timeout=10)
        messages = []
        for u in updates:
            if u.message:
                messages.append(u.message)
            elif u.channel_post:
                messages.append(u.channel_post)
        return messages
    except Exception as e:
        print(f"Error fetching updates: {e}")
        return []

if __name__ == "__main__":
    print("Fetching latest messages from Telegram to verify...")
    msgs = get_latest_messages(5)
    if not msgs:
        print("No recent messages found via get_updates.")
        print("Note: If the bot is already running or has a webhook, this might not work.")
    else:
        for m in msgs:
            chat_title = m.chat.title or m.chat.username or str(m.chat.id)
            print(f"\n--- Message from Chat: {chat_title} ({m.chat.id}) ---")
            print(f"Date: {time.ctime(m.date)}")
            if m.text:
                print(f"Text Content:\n{m.text[:500]}...")
            elif m.caption:
                print(f"Photo/Media with Caption:\n{m.caption[:500]}...")
            else:
                print("Media message without text/caption.")
            print("-" * 40)
