import os
import requests
from bs4 import BeautifulSoup
import feedparser
import time
import telebot
from io import BytesIO
import os
import json
import sys

def load_config(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f'Error loading config file {file}:', e)
        sys.exit(1)

current_directory = os.path.dirname(os.path.abspath(__file__))

settings = load_config(os.path.join(current_directory, 'settings.json'))
# settings = load_config(os.path.join(current_directory, 'test_settings.json'))

TOKEN = os.environ['TELEGRAM_BOT_TOKEN'] if settings['TELEGRAM_BOT_TOKEN'] == "os.environ['TELEGRAM_BOT_TOKEN']" else settings['TELEGRAM_BOT_TOKEN']
CHAT_ID = settings['YOUR_CHAT_ID']
TOPIC_ID = settings['TOPIC_ID']
FEED_URL = settings['FEED_URL']
LAST_ENTRY_FILE = os.path.join(current_directory, "last_entry.txt")

bot = telebot.TeleBot(TOKEN)

def get_last_post_with_phrase(username, phrase, url):
    response = requests.get(url)
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")

    user_posts = soup.find_all("tbody", class_=["row1", "row2"])

    for post in reversed(user_posts):
        author = post.find("p", class_="nick nick-author")
        if author and author.text == username:
            post_body = post.find("div", class_="post_body")
            if phrase in post_body.text:
                post_text = post_body.text
                phrase_index = post_text.find(phrase)
                return post_text[phrase_index + len(phrase):].strip()

    return None

def parse_entry(entry):
    print("Requesting page content...")
    response = requests.get(entry.link)
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")
    post_body = soup.find("div", class_="post_body")

    print("Parsing title, image_url, magnet_link, and description...")
    title = entry.title.replace(" [Nintendo Switch] ", " ").strip()
    # Поиск слова "[Обновлено]" в заголовке
    updated = ""
    last_post = ""
    if "[Обновлено]" in title:
        title = entry.title.replace("[Обновлено] ", " ").strip()
        updated = f" <b>[Обновлено] </b>"

        username = "omg_gods"
        phrase = "Раздача обновлена,"

        last_post = get_last_post_with_phrase(username, phrase, entry.link)

    # Формирование заголовка с жирным текстом, если было найдено слово "[Обновлено]"
    title_with_link = f'{updated}<a href="{entry.link}">{title}</a>'

    # title_with_link = f'<a href="{entry.link}">{title}</a>'
    # print(title_with_link)
    image_tag = post_body.find("var", class_="img-right")
    image_url = image_tag["title"] if image_tag else None
    # print(image_url)
    full_magnet_link = soup.find("a", class_="magnet-link")["href"]
    magnet_link = full_magnet_link.split('&')[0]
    # print(magnet_link)

    description_tags = post_body.find_all("span", class_="post-b")
    description_parts = []

    for tag in description_tags:
        description = tag.get_text(strip=True)
        description_parts.append(f"\n<b>{description}</b>")

        text_after_span = tag.next_sibling
        if text_after_span and text_after_span.name != 'br':
            text_after_span = text_after_span.strip()
            description_parts.append(text_after_span)

    description = " ".join(description_parts)

    return title_with_link, image_url, magnet_link, description, last_post

def send_to_telegram(title_with_link, image_url, magnet_link, description):
    message_text = f"{title_with_link}\n\n<b>Скачать</b>: <code>{magnet_link}</code>\n{description}"
    if image_url:
        print("Downloading image...")
        response = requests.get(image_url)
        if response.status_code == 200:
            image_data = response.content
            file = BytesIO(image_data)
            
            # Check if caption length is greater or equal to 1024 characters
            caption_text = message_text
            if len(caption_text) >= 1024:
                split_index = caption_text.find("<b>Описание</b>")
                first_message_text = caption_text[:split_index].strip()
                second_message_text = caption_text[split_index:].strip()
                print("Sending photo with truncated caption...")
                bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=file, caption=first_message_text, parse_mode="HTML")
                print("Sending message with remaining text...")
                bot.send_message(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, text=second_message_text, parse_mode="HTML")
            else:
                print("Sending message with photo...")
                bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=file, caption=message_text, parse_mode="HTML")
        else:
            print(f"Failed to download image from {image_url}, sending message without photo...")
            bot.send_message(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, text=message_text, parse_mode="HTML")
    else:
        print("Image not found, sending message without photo...")
        bot.send_message(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, text=message_text, parse_mode="HTML")

def main():
    if os.path.isfile(LAST_ENTRY_FILE):
        with open(LAST_ENTRY_FILE, 'r') as f:
            last_entry_link = f.read().strip()
    else:
        last_entry_link = None

    while True:
        print("Parsing feed...")
        feed = feedparser.parse(FEED_URL)

        for entry in feed.entries:
            # print(entry.link)
            # print(last_entry_link)
            if entry.link == last_entry_link:
                break

            title_with_link, image_url, magnet_link, description, last_post = parse_entry(entry)
            if last_post:
                last_post = last_post[0].upper() + last_post[1:]
                description += f"\n\n{last_post}"
            send_to_telegram(title_with_link, image_url, magnet_link, description)

        last_entry_link = feed.entries[0].link
        with open(LAST_ENTRY_FILE, 'w') as f:
            f.write(last_entry_link)
        # print("Sleeping for 1 hour...")
        # time.sleep(60 * 60)
        break

if __name__ == "__main__":
    main()
