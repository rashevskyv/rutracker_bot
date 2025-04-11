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

def translate_ru_to_ua_google(text: str) -> str:
    """Translates text from Russian to Ukrainian using Google Translate API."""
    if LOG: print("Translating text RU -> UA using Google Translate...")
    try:
        # Check if GOOGLE_APPLICATION_CREDENTIALS is set and file exists
        google_creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not google_creds_path or not os.path.exists(google_creds_path):
             print("Warning: Google credentials not configured correctly. Skipping Google Translate.")
             return text

        translate_client = translate.Client()

        # Split text into paragraphs by newline characters
        paragraphs = text.split('\n')

        # Translate each paragraph separately
        translated_paragraphs = []
        for paragraph in paragraphs:
            # Avoid translating empty strings which can cause errors or unnecessary API calls
            if paragraph.strip():
                result = translate_client.translate(paragraph, target_language='uk', source_language='ru')
                translated_paragraphs.append(result['translatedText'])
            else:
                translated_paragraphs.append(paragraph) # Keep empty lines

        translated_text = '\n'.join(translated_paragraphs)

        # Post-processing (simplified for clarity, adjust as needed)
        translated_text = translated_text.replace(' <a', '<a').replace('</a> ', '</a>')
        translated_text = re.sub(r'([a-zA-Zа-яА-ЯёЁіІїЇєЄ])<a', r'\1 <a', translated_text)
        translated_text = translated_text.replace(" :", ":")
        translated_text = re.sub(r'\s{2,}', ' ', translated_text).strip()
        # Add specific replacements if necessary
        translated_text = translated_text.replace("[оновлено]", "[Оновлено]").replace("Рік виконання", "Рік виходу")

        return translated_text
    except Exception as e:
        print(f"Error during Google translation: {e}")
        # Fallback or re-raise? For now, return original text.
        return text

def translate_ru_to_ua_gpt(text: str, model: str = "gpt-4o-mini") -> str:
    """
    Translates text from Russian to Ukrainian using GPT.

    :param text: Text to translate.
    :param model: GPT model to use. Defaults to "gpt-4o-mini".
    :return: Translated text or original text on error.
    """
    if not openai_client:
        print("Error: OpenAI client not available for GPT translation.")
        return text

    if LOG: print(f"Translating text RU -> UA using GPT model: {model}...")
    prompt = (
        f"Please translate the following text from Russian to Ukrainian. "
        f"Preserve all HTML tags (like <a>, <b>, <code>) and their content exactly as they are. "
        f"Keep English words and words starting with # (hashtags) untranslated (in English or as they are). "
        f"Do not translate the content inside <code> tags. Ensure the HTML structure remains valid.\n\n"
        f"Text to translate:\n{text}\n\nTranslation:"
    )

    try:
        # Ensure openai_client is not None before calling methods on it
        if openai_client:
             response = openai_client.chat.completions.create(
                 model=model,
                 messages=[{"role": "user", "content": prompt}]
             )
             translated_text = response.choices[0].message.content
             return translated_text.strip()
        else:
             # This case should ideally be caught by the initial check, but added for safety
             print("Error: OpenAI client became unavailable unexpectedly.")
             return text

    except Exception as e:
        print(f"Error during GPT translation: {e}")
        return text # Fallback to original text

def translate_ru_to_ua_deepl(text: str) -> str:
    """Translates text from Russian to Ukrainian using DeepL API."""
    if not DEEPL_API_KEY:
        # print("Info: DEEPL_API_KEY is not configured. Skipping DeepL translation.")
        return text # Return original text if key is missing

    if LOG: print("Translating text RU -> UA using DeepL...")
    url = "https://api-free.deepl.com/v2/translate" # Use free API endpoint unless paid
    params = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "source_lang": "RU",
        "target_lang": "UK",
        "tag_handling": "html" # Tell DeepL to handle HTML tags
    }

    try:
        response = requests.post(url, data=params, timeout=20) # Use POST and add timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        translated_text = response.json()['translations'][0]['text']
        return translated_text
    except requests.exceptions.RequestException as e:
        print(f"Error during DeepL translation request: {e}")
    except (KeyError, IndexError) as e:
        print(f"Error parsing DeepL translation response: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during DeepL translation: {e}")

    # Fallback if error occurred
    return text
