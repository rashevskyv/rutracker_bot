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
import re
import openai
from googleapiclient.discovery import build
from translation_functions import translate_ru_to_ua

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

def search_trailer_on_youtube(game_title):
    # Remove text within square brackets
    cleaned_game_title = re.sub(r'\[.*?\]', '', game_title).strip()

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    search_query = f"{cleaned_game_title} Nintendo Switch Trailer"
    
    print(f"Searching for trailer with query: {search_query}")

    search_response = youtube.search().list(
        q=search_query,
        part="id,snippet",
        type="video",
        maxResults=1,
        fields="items(id(videoId),snippet(publishedAt,channelId,channelTitle,title,description))"
    ).execute()

    items = search_response.get("items", [])

    if not items:
        print("No results found")
        return None

    video = items[0]
    video_id = video["id"]["videoId"]

    (f"Found video with ID: {video_id}")

    return f"https://www.youtube.com/watch?v={video_id}"

def get_last_post_with_phrase(phrase, url):
    response = requests.get(url)
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")

    user_posts = soup.find_all("tbody", class_=["row1", "row2"])

    for post in reversed(user_posts):
        post_body = post.find("div", class_="post_body")
        
        # Заменяем все теги <br> на \n
        for br_tag in post_body.find_all("br"):
            br_tag.replace_with("\n")
        
        # 6317248
        for hr_tag in post_body.find_all("hr"):
            hr_tag.replace_with(" BREAK ")

        #6345283
        for span_tag in post_body.find_all("span", class_="post-br"):
            span_tag.replace_with(" BREAK ")

        # Получаем текст post_body после замены <br> на \n
        post_body_text = post_body.text
        if phrase in post_body_text:
            phrase_index = post_body_text.find(phrase)
            break_index = post_body_text.find("BREAK")
            post_body_text=post_body_text[:break_index]

            if "внесённые изменения" in post_body_text:
                if "внесённые изменения" in post_body_text:
                    word_index = post_body_text.find("внесённые изменения")

                # Find the nearest link below the word
                nearest_link = post_body.find_next("a", href=True, text=True)
                if nearest_link:
                    # Update the text with the link
                    updated_text = post_body_text[:word_index] + f'<a href="{nearest_link["href"]}">' + post_body_text[word_index:(word_index + len("внесённые изменения"))] + '</a>'

                    ("updated_text: " + updated_text)

                    post_body_text = updated_text
                    last_post_text = f'<b>Обновлено: </b>{updated_text[len(phrase)+4:]}'
            else: 
                last_post_text = f'<b>Обновлено: </b>{post_body_text[phrase_index + len(phrase)+1:].strip()}'
            return last_post_text

    return None

def process_list_items(tag):
    if tag.name in ('ul', 'ol'):
        list_items = tag.find_all('li')
        formatted_items = [f"• {item.get_text(strip=True)}" for item in list_items]
        return "\n".join(formatted_items)
    else:
        return ""

def extract_description(post_body):
    if LOG: print("post_body: " + str(post_body))
    spans = post_body.find_all("span", class_="post-b")

    description = []
    result = ""

    for span in spans:
        content_list = []
        content = span.next_sibling

        while content is not None:
            if (content.name == "span" and content.get("class") == ["post-b"]):
                break

            if (content.name == "div" and content.get("class") == ["sp-wrap"]) or (content.name == "div" and content.get("class") == ["q-wrap"]):
                content_list.append("BREAK")

            content_list.append(str(content).strip())
            content = content.next_sibling

        content_text = "".join(content_list)
        description.append(f"<b>{span.text}</b>{content_text}")

    for i, entry in enumerate(description):
        # Обработка списков

        entry = entry.replace('<span class="post-br"><br/></span></li>', "")

        def remove_spans_inside_pre(match):
            return re.sub(r'<span[^>]*>|</span>', '', match.group(0))

        entry = re.sub(r'(<pre class="post-pre">.*?</pre>)', remove_spans_inside_pre, entry, flags=re.DOTALL)

        entry = re.sub(r"<ul>(.*?)</ul>", lambda match: f"{i}. {match.group(1)}", entry, flags=re.DOTALL)
        entry = re.sub(r"<li>(.*?)", lambda match: f"• {match.group(1)}", entry, flags=re.DOTALL)

        # # Обработка ссылок
        # entry = re.sub(r'<a href="(.*?)">(.*?)</a>', lambda match: f'<a href="{match.group(1)}">{match.group(2)}</a> ', entry)
        entry = re.sub(r'([a-zA-Zа-яА-ЯёЁ])<a', r'\1 <a', entry)

        result += entry  + "\n"

    break_index = result.find("BREAK")
    print(f"break_index: {break_index}")

    result = result[:break_index].replace("<span class=\"post-br\"><br/></span>", "\n\r\n").replace("<br/>", "\n").replace("<ol class=\"post-ul\">", "\n\r").replace("</ul>", "").replace("</ol>", "").replace("<li>", "").replace("</li>", "").replace("<span class=\"post-b\">", "").replace("</span>", "").replace("<div class=\"sp-wrap\">", "").replace("\n\n", "\n").replace("<hr class=\"post-hr\"/>", "\n\r").replace(" :", ":").replace(":", ": ").replace(",", ", ").replace("  ", " ").replace("href=\"viewtopic.php", "href=\"https://rutracker.org/forum/viewtopic.php").replace("href=\"tracker.php?", "href=\"https://rutracker.org/forum/tracker.php?").replace("</a>(", "</a> (").replace("https: //", "https://").strip()

    return result

def parse_entry(entry):
    print(f"Requesting {entry.link} content...")
    response = requests.get(entry.link)
    
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")
    post_body = soup.find("div", class_="post_body")

    print("Parsing title, image_url, magnet_link, and description...")
    title = entry.title.replace("[Nintendo Switch] ", " ").strip()
    updated = ""
    last_post = ""
    
    if "[Обновлено]" in title:
        title = title.replace("[Обновлено] ", " ").strip()
        updated = f"<b>[Обновлено] </b>"

        if updated:
            link = entry.link
            for i in range(0, 6001, 30):
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

        phrase = "Раздача обновлена"
        last_post = get_last_post_with_phrase(phrase, link)
        if LOG: print(f"last_post: {last_post}")

    # Формирование заголовка с жирным текстом, если было найдено слово "[Обновлено]"
    title_with_link = f'{updated}<a href="{entry.link}">{title}</a>'

    try:
        trailer_url = search_trailer_on_youtube(title)
        if trailer_url:
            title_with_link += f' | <a href="{trailer_url}">Трейлер</a>'
        print(f"Trailer url: {trailer_url}")
    except Exception as e:
        print(f"An error occurred while searching for the trailer: {e}")

    image_tag = post_body.find("var", class_="img-right")
    image_url = image_tag["title"] if image_tag else None
    full_magnet_link = soup.find("a", class_="magnet-link")["href"]
    magnet_link = full_magnet_link.split('&')[0]

    description = extract_description(post_body)
    if LOG: print(f"Description:\n{description}")

    additional_info_string = "Доп. информацияписал(а):"
    additional_info_index = description.find(additional_info_string)
    if additional_info_index != -1:
        description = description[:additional_info_index] + "\n\n" + "<b>Дополнительная информация:</b> " + description[additional_info_index + len(additional_info_string):]

    # Переводит жанры в теги
    description = make_tag(description, "Жанр")
    # description = make_tag(description, "Год выпуска")

    return title_with_link, image_url, magnet_link, description, last_post

def make_tag(description, keyword):
    print("Making tag...")
    tag_string = f"<b>{keyword}</b>: "
    if tag_string in description:
        tag_start = description.find(tag_string) + len(tag_string)
        tag_end = description.find("\n", tag_start)
        tags = description[tag_start:tag_end].strip().split(", ")
        formatted_tags = []

        for tag in tags:
            if re.search('<a.*?>(.*?)</a>', tag):
                link_text = re.search('<a.*?>(.*?)</a>', tag).group(1)
                new_link_text = f"еще игры этого жанра"
                clean_tag = link_text.replace(' ', '').replace('&', 'and').replace('-', '')
                formatted_tag = re.sub(r'(<a.*?>)(.*?)(</a>)', f" #{clean_tag} (\\1{new_link_text}\\3)", tag)
            else:
                clean_tag = tag.replace(' ', '').replace('&', 'and').replace('-', '')
                formatted_tag = f" #{clean_tag}"
            formatted_tags.append(formatted_tag)

        formatted_tags_str = ",".join(formatted_tags)
        description = description[:tag_start] + formatted_tags_str + description[tag_end:]
    return description

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

def send_to_telegram(title_with_link, image_url, magnet_link, description):
    message_text = f"{title_with_link}\n\n<b>Скачать</b>: <code>{magnet_link}</code>\n\n{description}"
    if LOG: print("message_text:\n", message_text)

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
                if LOG: print("message_parts[0]:\n", message_parts[0])
                bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=file, caption=message_parts[0], parse_mode="HTML")
                print(f"Sending message with remaining text to {group_name}...")
                bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_parts[1], parse_mode="HTML")
                if LOG: print("message_parts[1]:\n", message_parts[1])
            else:
                print(f"Sending message with photo to {group_name}...")
                bot.send_photo(chat_id=chat_id, message_thread_id=topic_id, photo=file, caption=message_text, parse_mode="HTML")
                if LOG: print("message_text:\n", message_text)
        else:
            print(f"Sending message without photo to {group_name}...")
            bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=message_text, parse_mode="HTML")
            if LOG: print("message_text:\n", message_text)

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
                entry.link = last_entry_link
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

                print("Sleeping for 1 minute...")
                time.sleep(60)

            last_entry_link = feed.entries[0].link
            with open(LAST_ENTRY_FILE, 'w') as f:
                f.write(last_entry_link)
            # print("Sleeping for 1 hour...")
            # time.sleep(60 * 60)
            break

if __name__ == "__main__":
    main()
