from io import BytesIO
import requests
from translation_functions import translate_ru_to_ua
from settings import settings, LOG, bot
import re
from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_endtag(self, tag):
        if self.tags and self.tags[-1] == tag:
            self.tags.pop()


def check_html_tags(text):
    parser = MyHTMLParser()
    parser.feed(text)
    return parser.tags

def split_text_by_length(text, length):
    lines = text.split('\n')
    split_texts = []
    current_text = ''

    for line in lines:
        if len(current_text) + len(line) + 1 > length:  # plus 1 for the newline character
            # Check for unclosed tags
            unclosed_tags = check_html_tags(current_text)
            if unclosed_tags:
                print(f'Warning: found unclosed HTML tags in text: {unclosed_tags}')
            split_texts.append(current_text)
            current_text = line
        else:
            current_text = current_text + '\n' + line if current_text else line

    if current_text:  # add the last chunk of text
        # Check for unclosed tags
        unclosed_tags = check_html_tags(current_text)
        if unclosed_tags:
            print(f'Warning: found unclosed HTML tags in text: {unclosed_tags}')
        split_texts.append(current_text)

    return split_texts

import requests
from io import BytesIO
import threading

def download_image(image_url, timeout=10):
    image = None
    try:
        print("Downloading image...")
        response = requests.get(image_url, timeout=timeout)
        if response.status_code == 200:
            image_data = response.content
            image = BytesIO(image_data)
        else:
            print(f"Failed to download image from {image_url}")
    except requests.exceptions.Timeout:
        print("Image download timed out. Changing the URL...")
        image_url = 'https://static.komputronik.pl/product-picture/11/NINTENDOSWITCHRB19-1.jpg'
        response = requests.get(image_url)
        if response.status_code == 200:
            image_data = response.content
            image = BytesIO(image_data)
        else:
            print(f"Failed to download image from {image_url}")
    except Exception as e:
        print(f"An error occurred: {e}")
    return image

def send_to_telegram(title_with_link, image_url, magnet_link, description):
    try:
        message_text = f"{title_with_link}\n\n<b>Скачать</b>: <code>{magnet_link}</code>\n\n{description}"
        if LOG: print("message_text:\n", message_text)

        image = download_image(image_url)

        for group in settings['GROUPS']:
            chat_id = group['chat_id']
            topic_id = group['topic_id']
            group_name = group['group_name']
            group_lang = group['language']

            print(f"Obtaining message to {group_name}... in {group_lang} language")

            if group_lang == "UA":
                message_text = translate_ru_to_ua(message_text)
                print("Translated to UA")
                

            if image:
                image.seek(0)
                message_parts = split_text_for_telegram(message_text, group_lang)

                if len(message_parts) > 1:
                    print(f"Sending photo with truncated caption to {group_name}...")
                    print(f"Current chat_id: {chat_id}, topic_id: {topic_id}")

                    if LOG: print("message_parts[0]:\n", message_parts[0])
                    bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=image, caption=message_parts[0], parse_mode="HTML")
                    print(f"Sending message with remaining text to {group_name}...")

                    if len(message_parts[1]) > 4000:
                        split_parts = split_text_by_length(message_parts[1], 4000)
                        for i, part in enumerate(split_parts):
                            if LOG: print(f"message_parts[{i}]:\n", part)
                            bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=part, parse_mode="HTML")
                    else:
                        bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_parts[1], parse_mode="HTML")
                else:
                    print(f"Sending message with photo to {group_name}...")
                    if LOG: print("message_text:\n", message_text)
                    bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=image, caption=message_text, parse_mode="HTML")
            else:
                if LOG: print("message_text:\n", message_text)
                print(f"Sending message without photo to {group_name}...")
                bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_text, parse_mode="HTML")
    except Exception as e:
        raise

def split_text_for_telegram(text, language):
    if len(text) > 900:
        print("Text is long enough: " + str(len(text)))
        if language == "RU":
            split_index = text.find("<b>Описание")
            print("Found <b>Описание")
            print("split_index:", split_index)
        elif language == "UA":
            split_index = text.find("<b>Опис")
            print("Found <b>Опис")
            print("split_index:", split_index)
    else: 
        print("Text is too short")
        return [text]

    first_message_text = text[:split_index].strip()
    second_message_text = text[split_index:].strip()

    if LOG: 
        print("first_message_text:\n", first_message_text)
        print("second_message_text:\n", second_message_text)
    
    return [first_message_text, second_message_text]

def send_message_to_telegram(message):
    message_text = f"{message}"
    
    error_tg_list = settings['ERROR_TG']

    for error_tg in error_tg_list:
        chat_id = error_tg['chat_id']
        
        tg_url = f"https://api.telegram.org/bot{settings['TELEGRAM_BOT_TOKEN']}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message_text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        try:
            response = requests.post(tg_url, data=data)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Failed to send error message to Telegram group: {e}")

def send_error_to_telegram(error_message):
    send_message_to_telegram(error_message)
