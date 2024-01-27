import openai
import requests
from google.cloud import translate_v2 as translate
import re

# translate_ru_to_ua function with select exact translate function
def translate_ru_to_ua(text):
    return translate_ru_to_ua_google(text)

def translate_ru_to_ua_google(text):
    translate_client = translate.Client()

    # Разбить текст на абзацы по символам перевода строки
    paragraphs = text.split('\n')

    # Перевести каждый абзац отдельно
    translated_paragraphs = []
    for paragraph in paragraphs:
        result = translate_client.translate(paragraph, target_language='uk', source_language='ru')
        translated_paragraphs.append(result['translatedText'])

    translated_text = '\n'.join(translated_paragraphs).replace(' <a', '<a').replace('</a> ', '</a>')
    translated_text = re.sub(r'([a-zA-Zа-яА-ЯёЁ])<a', r'\1 <a', translated_text)
    translated_text = translated_text.replace(" :", ":").replace(":<a", ": <a").replace("</a>(", "</a> (").replace("</b><a", '</b> <a').replace("<a", " <a").replace("</a>", "</a> ").replace(' , ', ", ").replace("# ", "#").replace("( <a", "(<a").replace("</a> )", "</a>)").replace("[ <a", "[<a").replace("</a> ]", "</a>]").replace("| </a>", "</a> |").replace("|</a>", "</a>|").replace("|", " | ").replace("[оновлено]", "[Оновлено]").strip().replace("<html>", "").replace("Рік виконання", "Рік виходу").replace("Рік зробити", "Рік виходу")

    translated_text = translated_text.replace("  ", " ").replace("  ", " ")

    return translated_text

def translate_ru_to_ua_gpt3_5(text):
    prompt = f"Пожалуйста, переведи следующий текст с русского на украинский, оставляя английские слова и теги, начинающиеся с # без изменений (на английском). Ты перевел название жанра, начинающееся на #. Не переводи слова, начинающиеся с #:\n\n{text}\n\nПеревод:"

    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
    
    return response.choices[0].message.content

def translate_ru_to_ua_gpt4(text):
    prompt = f"Пожалуйста, переведи следующий текст с русского на украинский, оставляя английские слова и теги, начинающиеся с # без изменений (на английском). Ты перевел название жанра, начинающееся на #. Не переводи слова, начинающиеся с #:\n\n{text}\n\nПеревод:"

    openai.organization = "org-wKWxhPRgiQddo9HjjUr1M0Tz"
    response = openai.ChatCompletion.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
    
    return response.choices[0].message.content

def translate_ru_to_ua_phind(text):
    prompt = f"Просто переведи текст с русского на украинский, оставляя без перевода слова на языках отличных от русского:\n\n{text}\n\nПеревод:"

    result = phind.Completion.create(
        model  = 'gpt-4',
        prompt = prompt,
        results     = phind.Search.create(prompt, actualSearch = False), # create search (set actualSearch to False to disable internet)
        creative    = False,
        detailed    = False,
        codeContext = ''
    ) # up to 3000 chars of code
    print(result.completion.choices[0].text)
    
    return result.completion.choices[0].text

def translate_ru_to_ua_deepl(text):
    url = f"https://api.deepl.com/v2/translate?auth_key={DEEPL_API_KEY}&text={text}&source_lang=RU&target_lang=UK"

    response = requests.get(url)
    translated_text = response.json()['translations'][0]['text']

    return translated_text