import os
import requests
from bs4 import BeautifulSoup
import feedparser
import time
import os
import re
from googleapiclient.discovery import build
from telegram import send_to_telegram, send_error_to_telegram, send_message_to_telegram
from settings import settings, LOG, YOUTUBE_API_KEY, LAST_ENTRY_FILE, FEED_URL, test, test_settings
import traceback

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

    # If no results found and search query contains "/", try searching with text before "/"
    if not items and '/' in search_query:
        search_query = search_query.split('/', 1)[0].strip()
        print(f"Retry searching for trailer with query: {search_query}")
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

    print(f"Found video with ID: {video_id}")

    return f"https://www.youtube.com/watch?v={video_id}"

def get_last_post_with_phrase(phrase, url):
    response = requests.get(url)
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")

    user_posts = soup.find_all("tbody", class_=["row1", "row2"])

    if phrase in str(user_posts):

        for post in reversed(user_posts):
            post_body = post.find("div", class_="post_body")
            post_url = "https://rutracker.org/forum/" + post.find("a", class_="p-link small")["href"]
            # print(f"post_url: {post_url}")
            
            # Заменяем все теги <br> на \n
            for br_tag in post_body.find_all("br"):
                br_tag.replace_with("\n")
            
            # 6317248
            for hr_tag in post_body.find_all("hr"):
                hr_tag.replace_with(" BREAK ")

            #6345283
            for span_tag in post_body.find_all("span", class_="post-br"):
                span_tag.replace_with(" BREAK ")

            #6245869
            for div_tag in post_body.find_all("div", class_="sp-wrap"):
                div_tag.replace_with(" BREAK ")

            post_body_text = post_body.text
            if phrase in post_body_text:
                phrase_index = post_body_text.find(phrase)
                break_index = post_body_text.find("BREAK")
                post_body_text=post_body_text[:break_index]

                if "внесённые изменения" in post_body_text:
                    print("post_body:\n" + str(post_body))
                    if "внесённые изменения" in post_body_text:
                        word_index = post_body_text.find("внесённые изменения")

                    # Find the nearest link below the word
                    last_post_text = None

                    if post_url:
                        # Update the text with the link
                        updated_text = post_body_text[:word_index] + f'<a href="{post_url}">' + post_body_text[word_index:(word_index + len("внесённые изменения"))] + '</a>'

                        ("updated_text: " + updated_text)

                        post_body_text = updated_text
                        last_post_text = f'<b>Обновлено: </b>{updated_text[len(phrase)+4:]}'
                else: 
                    last_post_text = f'<b>Обновлено: </b>{post_body_text[phrase_index + len(phrase)+1:].strip()}'
                return last_post_text
    else:
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
        entry = entry.replace('<span class="post-br"><br/></span>', "\n\r\n")

        def remove_spans_inside_pre(match):
            return re.sub(r'<span[^>]*>|</span>', '', match.group(0))

        entry = re.sub(r'(<pre class="post-pre">.*?</pre>)', remove_spans_inside_pre, entry, flags=re.DOTALL)

        entry = re.sub(r"<ul>(.*?)</ul>", lambda match: f"{i}. {match.group(1)}", entry, flags=re.DOTALL)
        entry = re.sub(r"<li>(.*?)", lambda match: f"• {match.group(1)}", entry, flags=re.DOTALL)

        # # Обработка ссылок
        # entry = re.sub(r'<a href="(.*?)">(.*?)</a>', lambda match: f'<a href="{match.group(1)}">{match.group(2)}</a> ', entry)
        entry = re.sub(r'([a-zA-Zа-яА-ЯёЁ])<a', r'\1 <a', entry)
        entry = re.sub(r"<span class=\"post-u\">(.*?)</span>", lambda match: f"<u>{match.group(1)}</u>", entry, flags=re.DOTALL)
        entry = re.sub(r"<span class=\"post-i\">(.*?)</span>", lambda match: f"<i>{match.group(1)}</i>", entry, flags=re.DOTALL)
        entry = re.sub(r"<span class=\"post-b\">(.*?)</span>", lambda match: f"<b>{match.group(1)}</b>", entry, flags=re.DOTALL)
        entry = re.sub(r"<span[^>]*>(.*?)</span>", lambda match: f"<b>{match.group(1)}</b>", entry, flags=re.DOTALL)

        result += entry  + "\n"

    break_index = result.find("BREAK")
    print(f"break_index: {break_index}")

    result = result[:break_index].replace("<span class=\"post-br\"><br/></span>", "\n\r\n").replace("<br/>", "\n").replace("<ol class=\"post-ul\">", "\n\r").replace("</ul>", "").replace("</ol>", "").replace("<li>", "").replace("</li>", "").replace("<span class=\"post-b\">", "").replace("</span>", "").replace("<div class=\"sp-wrap\">", "").replace("\n\n", "\n").replace("<hr class=\"post-hr\"/>", "\n\r").replace(" :", ":").replace(":", ": ").replace(",", ", ").replace("href=\"viewtopic.php", "href=\"https://rutracker.org/forum/viewtopic.php").replace("href=\"tracker.php?", "href=\"https://rutracker.org/forum/tracker.php?").replace("</a>", "</a> ").replace("</a> , ", "</a>, ").replace("/<a", "/ <a").replace("</a> ]", "</a>]").replace("https: //", "https://").replace("<span class=\"post-i\">", "").replace("\n</i>", "</i>").replace("<i>", " <i>").replace("</i>", "</i> ").replace("\n</b>", "").replace("<ol type=\"1\">", "").replace("\" <a ", "\"<a ").replace("</u></b>", "</b></u>")

    result = result.replace("  ", " ").strip()

    return result

def parse_entry(entry):
    link = entry.link
    title = entry.title

    print(f"\n\n{title}\nRequesting {link} content...")
    response = requests.get(link)
       
    page_content = response.content
    soup = BeautifulSoup(page_content, "html.parser")
    post_body = soup.find("div", class_="post_body")

    print("Parsing title, image_url, magnet_link, and description...")
    title = title.replace("[Nintendo Switch] ", " ").strip()
    updated = ""
    last_post = ""
    
    if "[Обновлено]" in title:
        title = title.replace("[Обновлено] ", " ").strip()
        updated = f"<b>[Обновлено] </b>"
        phrase = "Раздача обновлена"

        if updated:
            link = link
            for i in range(0, 6001, 30):
                new_link = f"{link}&start={i}"
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
                        last_post_temp = get_last_post_with_phrase(phrase, link)
                        if last_post_temp:
                            last_post = last_post_temp
                            if LOG: print(f"last_post: {last_post}")
                else:
                    print(f"No response from {new_link}")
                    break


    # Формирование заголовка с жирным текстом, если было найдено слово "[Обновлено]"
    title_with_link = f'{updated}<a href="{link}">{title}</a>'

    try:
        trailer_url = search_trailer_on_youtube(title)
        if trailer_url:
            title_with_link += f' | <a href="{trailer_url}">Трейлер</a>'
        print(f"Trailer url: {trailer_url}")
    except Exception as e:
        print(f"An error occurred while searching for the trailer: {e}")

    try:
        image_tag = post_body.find("var", class_="img-right")
        image_url = image_tag["title"] if image_tag else None
    except Exception as e:
        print(f"Ошибка при извлечении тега изображения или атрибута 'title': {e}")
        image_url = None

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
                clean_tag = link_text.replace(' ', '').replace('&', 'And').replace('-', '').replace('amp;', '').replace("BAndW", "BlackAndWhite")
                formatted_tag = re.sub(r'(<a.*?>)(.*?)(</a>)', f" #{clean_tag} (\\1{new_link_text}\\3)", tag)
            else:
                clean_tag = tag.replace(' ', '').replace('&', 'And').replace('-', '').replace('\'', '')
                formatted_tag = f" #{clean_tag}"
            formatted_tags.append(formatted_tag)

        formatted_tags_str = ",".join(formatted_tags)
        description = description[:tag_start] + formatted_tags_str + description[tag_end:]
    return description

def main():
    print("Starting...")
    print("LOG: " + str(LOG))
    feeds=[]
    try:
        if test:
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

            if test:
                specific_entry = None

                for entry in feed.entries:
                    if entry['link'] == last_entry_link:
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
                    if entry.link != last_entry_link:
                        feeds.append(entry)
                        print(f"Added {entry.link}")
                    else: 
                        message = "No new feeds found"
                        print(message)
                        send_message_to_telegram(message)
                        break

                for entry in reversed(feeds):

                    title_with_link, image_url, magnet_link, description, last_post = parse_entry(entry)
                    if last_post:
                        last_post = last_post[0].upper() + last_post[1:]
                        description += f"\n\n{last_post}"
                    send_to_telegram(title_with_link, image_url, magnet_link, description)

                    with open(LAST_ENTRY_FILE, 'w') as f:
                        f.write(entry.link)

                    if not test_settings: 
                        print("Sleeping for 1 minute...")
                        time.sleep(60)

                    # print("Sleeping for 1 hour...")
                    # time.sleep(60 * 60)
                break
                
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        stack_trace = traceback.format_exc()

        error_details = f"Error type: {error_type}\nError message: {error_message}\nStack Trace: {stack_trace}"
        print(error_details)
        send_error_to_telegram(error_details)

if __name__ == "__main__":
    main()
