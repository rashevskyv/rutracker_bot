# --- START OF FILE translation.py ---
import requests
from google.cloud import translate_v2 as translate
from settings_loader import openai_client, DEEPL_API_KEY, LOG # Import necessary items
import re
import os
from typing import Optional # Import Optional

# Translate RU to UA function with select exact translate function
def translate_ru_to_ua(text: str) -> str:
    """
    Translates text from Russian to Ukrainian using the preferred method.
    Currently set to use GPT if available, otherwise returns original text.
    """
    if openai_client:
        if LOG: print("Translating text RU -> UA using GPT...")
        return translate_ru_to_ua_gpt(text)
    else:
        print("Warning: OpenAI client not available for translation. Returning original text.")
        return text # Fallback if GPT client failed initialization

# Function translate_ru_to_ua_google remains the same
def translate_ru_to_ua_google(text: str) -> str:
    """Translates text from Russian to Ukrainian using Google Translate API."""
    if LOG: print("Translating text RU -> UA using Google Translate...")
    try:
        google_creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not google_creds_path or not os.path.exists(google_creds_path):
             print("Warning: Google credentials not configured correctly. Skipping Google Translate.")
             return text
        translate_client = translate.Client()
        paragraphs = text.split('\n'); translated_paragraphs = []
        for paragraph in paragraphs:
            if paragraph.strip(): result = translate_client.translate(paragraph, target_language='uk', source_language='ru'); translated_paragraphs.append(result['translatedText'])
            else: translated_paragraphs.append(paragraph)
        translated_text = '\n'.join(translated_paragraphs)
        translated_text = translated_text.replace(' <a', '<a').replace('</a> ', '</a>')
        translated_text = re.sub(r'([a-zA-Zа-яА-ЯёЁіІїЇєЄ])<a', r'\1 <a', translated_text)
        translated_text = translated_text.replace(" :", ":"); translated_text = re.sub(r'\s{2,}', ' ', translated_text).strip()
        translated_text = translated_text.replace("[оновлено]", "[Оновлено]").replace("Рік виконання", "Рік виходу")
        return translated_text
    except Exception as e: print(f"Error during Google translation: {e}"); return text

def translate_ru_to_ua_gpt(text: str, model: str = "gpt-4o-mini") -> str:
    """
    Translates text from Russian to Ukrainian using GPT, requesting logical formatting
    and allowing light emphasis for readability.

    :param text: Text to translate.
    :param model: GPT model to use. Defaults to "gpt-4o-mini".
    :return: Translated text or original text on error.
    """
    if not openai_client:
        print("Error: OpenAI client not available for GPT translation.")
        return text

    if LOG: print(f"Translating text RU -> UA using GPT model: {model}...")

    # --- Updated Prompt ---
    prompt = (
        f"Please translate the following text from Russian to Ukrainian.\n"
        f"**Formatting Requirements:**\n"
        f"1.  Strictly preserve all original HTML tags allowed by Telegram: `<b>`, `<i>`, `<u>`, `<s>`, `<tg-spoiler>`, `<a>`, `<code>`, `<pre>`.\n"
        f"2.  Remove any other HTML tags (like `<span>`, `<div>`) but keep their content.\n"
        f"3.  Keep English words and words starting with # (hashtags) untranslated.\n"
        f"4.  Do not translate content inside `<code>` and `<pre>` tags.\n"
        f"5.  Structure the translated text logically. If the original text uses bold tags (`<b>...</b>:`) for headers (like 'Год выпуска:', 'Жанр:', 'Описание:'), use bold tags (`<b>`) for the corresponding translated headers.\n"
        # --- MODIFIED POINT ---
        f"6.  To improve readability, use bold (`<b>`) or italics (`<i>`) tags to emphasize key points or terms where appropriate, even if not present in the original text.\n"
        # --- END MODIFIED POINT ---
        f"7.  Do NOT add any emojis or markdown formatting like ```.\n\n" # Renumbered
        f"**Text to translate:**\n{text}\n\n**Ukrainian Translation:**"
    )
    # --- End of Updated Prompt ---

    try:
        if openai_client:
             response = openai_client.chat.completions.create(
                 model=model,
                 messages=[{"role": "user", "content": prompt}],
                 # temperature=0.5 # Optional: Adjust temperature if needed
             )
             translated_text = response.choices[0].message.content

             # Clean trailing markdown code fences and whitespace
             cleaned_text = translated_text.strip()
             cleaned_text = re.sub(r"^(```html|```)", "", cleaned_text).strip()
             cleaned_text = re.sub(r"```$", "", cleaned_text).strip()

             return cleaned_text
        else:
             print("Error: OpenAI client became unavailable unexpectedly.")
             return text

    except Exception as e:
        print(f"Error during GPT translation: {e}")
        return text # Fallback to original text

# Function translate_ru_to_ua_deepl remains the same
def translate_ru_to_ua_deepl(text: str) -> str:
    """Translates text from Russian to Ukrainian using DeepL API."""
    if not DEEPL_API_KEY: return text
    if LOG: print("Translating text RU -> UA using DeepL...")
    url = "https://api-free.deepl.com/v2/translate"
    params = {"auth_key": DEEPL_API_KEY, "text": text, "source_lang": "RU", "target_lang": "UK", "tag_handling": "html"}
    try:
        response = requests.post(url, data=params, timeout=20); response.raise_for_status()
        translated_text = response.json()['translations'][0]['text']; return translated_text
    except requests.exceptions.RequestException as e: print(f"Error during DeepL translation request: {e}")
    except (KeyError, IndexError) as e: print(f"Error parsing DeepL translation response: {e}")
    except Exception as e: print(f"An unexpected error occurred during DeepL translation: {e}")
    return text
# --- END OF FILE translation.py ---