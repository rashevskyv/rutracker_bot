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
import openai

def load_config(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f'Error loading config file {file}:', e)
        sys.exit(1)

current_directory = os.path.dirname(os.path.abspath(__file__))

# settings = load_config(os.path.join(current_directory, 'settings.json'))
# settings = load_config(os.path.join(current_directory, 'test_settings.json'))
settings = load_config(os.path.join(current_directory, 'local_settings.json'))

TOKEN = os.environ['TELEGRAM_BOT_TOKEN'] if settings['TELEGRAM_BOT_TOKEN'] == "os.environ['TELEGRAM_BOT_TOKEN']" else settings['TELEGRAM_BOT_TOKEN']
FEED_URL = settings['FEED_URL']
LAST_ENTRY_FILE = os.path.join(current_directory, "last_entry.txt")
openai.api_key = os.environ['OPENAI_API'] if settings['OPENAI_API'] == "os.environ['OPENAI_API']" else settings['OPENAI_API']
openai.Model.list()
bot = telebot.TeleBot(TOKEN)

def translate_ru_to_ua(text):
    prompt = f"Переведите следующий текст с русского на украинский:\n\n{text}\n\nПеревод:"

    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
    
    return response.choices[0].message.content

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
    print(f"Requesting {entry.link} content...")
    response = requests.get(entry.link)
    
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")
    post_body = soup.find("div", class_="post_body")

    print("Parsing title, image_url, magnet_link, and description...")
    title = entry.title.replace(" [Nintendo Switch] ", " ").strip()
    updated = ""
    last_post = ""
    
    if "[Обновлено]" in title:
        title = title.replace("[Обновлено] ", " ").strip()
        updated = f"<b>[Обновлено] </b>"

        username = "omg_gods"
        phrase = "Раздача обновлена,"

        if updated:
            link = entry.link
            for i in range(0, 121, 30):
                new_link = f"{entry.link}&start={i}"
                print(f"Requesting {new_link} content...")
                response = requests.get(new_link)

                if response.status_code == 200:
                    print(f"Got response from {new_link}")
                    new_response = requests.get(new_link)
                    new_page_content = new_response.content
                    new_soup = BeautifulSoup(new_page_content, "html.parser")
                    new_post_body = new_soup.find("div", class_="post_body")
                    
                    if new_post_body == None:
                        break
                    else:
                        link = new_link
                        print(f"Response from {link}")
                else:
                    print(f"No response from {new_link}")
                    break

        last_post = get_last_post_with_phrase(username, phrase, link)

    # Формирование заголовка с жирным текстом, если было найдено слово "[Обновлено]"
    title_with_link = f'{updated}<a href="{entry.link}">{title}</a>'
    print("title_ith_link:", title_with_link)

    image_tag = post_body.find("var", class_="img-right")
    image_url = image_tag["title"] if image_tag else None
    full_magnet_link = soup.find("a", class_="magnet-link")["href"]
    magnet_link = full_magnet_link.split('&')[0]

    description_all_tags = post_body.find_all("span", class_="post-b")
    description_parts = []
    description_tags = []

    for tag in description_all_tags:
        description_tags.append(tag)
        if tag.get_text(strip=True) == "Описание":
            break

    for tag in description_tags:
        description = tag.get_text(strip=True)
        description_parts.append(f"\n<b>{description}</b>")
        text_after_span = ""

        # Получаем следующий элемент после текущего тега
        sibling = tag.next_sibling
        # print("sibling:", sibling)
        while sibling is not None:
            # Если элемент текстовый, добавляем его к переменной text_after_span
            if isinstance(sibling, str):
                text_after_span += sibling.strip()
            # Если элемент является тегом, добавляем его текст к переменной text_after_span
            elif sibling.name is not None:
                # Если следующий тег не такой же, как текущий тег 'tag', останавливаем обработку
                if sibling != tag:
                    break
                text_after_span += sibling.get_text(strip=True)

            # Если текущий тег br, прерываем цикл
            if sibling.name == 'br' or (sibling.name == 'span' and 'post-br' in sibling.get('class', [])):
                break

            sibling = sibling.next_sibling

        if text_after_span:
            description_parts.append(text_after_span)

    description = " ".join(description_parts)

    return title_with_link, image_url, magnet_link, description, last_post

def split_text_for_telegram(text, language):
    if len(text) >= 1024:
        if language == "RU":
            print("Found <b>Описание</b>")
            split_index = text.find("<b>Описание</b>")
            print("split_index:", split_index)
        elif language == "UA":
            print("Found <b>Опис</b>")
            split_index = text.find("<b>Опис</b>")
            print("split_index:", split_index)
    else: 
        return [text]

    first_message_text = text[:split_index].strip()
    second_message_text = text[split_index:].strip()
    
    return [first_message_text, second_message_text]

def send_to_telegram(title_with_link, image_url, magnet_link, description):
    message_text = f"{title_with_link}\n\n<b>Скачать</b>: <code>{magnet_link}</code>\n{description}"

    if image_url:
        print("Downloading image...")
        response = requests.get(image_url)
        if response.status_code == 200:
            image_data = response.content
            file = BytesIO(image_data)
        else:
            print(f"Failed to download image from {image_url}")
            file = None
    else:
        print("Image not found")
        file = None

    for group in settings['GROUPS']:
        chat_id = group['chat_id']
        topic_id = group['topic_id']
        group_name = group['group_name']
        group_lang = group['language']

        print(f"Obtaining message to {group_name}... in {group_lang} language")

        if group_lang == "UA":
            message_text = translate_ru_to_ua(message_text)
            print("Translated to UA")

        if file:
            file.seek(0)
            message_parts = split_text_for_telegram(message_text, group_lang)

            if len(message_parts) > 1:
                print(f"Sending photo with truncated caption to {group_name}...")
                print(f"Current chat_id: {chat_id}, topic_id: {topic_id}")
                bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=file, caption=message_parts[0], parse_mode="HTML")
                print(f"Sending message with remaining text to {group_name}...")
                bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_parts[1], parse_mode="HTML")
            else:
                print(f"Sending message with photo to {group_name}...")
                bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=file, caption=message_text, parse_mode="HTML")
        else:
            print(f"Sending message without photo to {group_name}...")
            bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_text, parse_mode="HTML")

def main():
    if settings["test"]:
        last_entry_link = settings["test_last_entry_link"]
        print("Test mode is enabled. Last entry link:", last_entry_link)
    elif os.path.isfile(LAST_ENTRY_FILE):
        with open(LAST_ENTRY_FILE, 'r') as f:
            last_entry_link = f.read().strip()
    else:
        last_entry_link = None

    while True:
        print("Parsing feed...")
        feed = feedparser.parse(FEED_URL)

        if settings["test"]:
            specific_entry = None
            for entry in feed.entries:
                if entry.link == last_entry_link:
                    specific_entry = entry
                    break

            if specific_entry is None:
                print("Specific entry not found.")
                break
            else:
                title_with_link, image_url, magnet_link, description, last_post = parse_entry(specific_entry)
                if last_post:
                    last_post = last_post[0].upper() + last_post[1:]
                    description += f"\n\n{last_post}"
                send_to_telegram(title_with_link, image_url, magnet_link, description)
                break
        else:
            for entry in feed.entries:
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
