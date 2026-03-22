# --- START OF FILE translation.py ---
import aiohttp
import asyncio
from google.cloud import translate_v2 as translate
from settings_loader import openai_client, DEEPL_API_KEY, get_session
from html_utils import sanitize_html_for_telegram
import re
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Translate RU to UA function with select exact translate function
async def translate_ru_to_ua(text: str) -> str:
    """
    Translates text from Russian to Ukrainian using the preferred method.
    Currently set to use GPT if available, otherwise returns original text.
    """
    if openai_client:
        logger.info("Translating text RU -> UA using GPT...")
        return await translate_ru_to_ua_gpt(text)
    else:
        logger.warning("OpenAI client not available for translation. Returning original text.")
        return text # Fallback if GPT client failed initialization

# Function translate_ru_to_ua_google remains the same (made async-friendly)
async def translate_ru_to_ua_google(text: str) -> str:
    """Translates text from Russian to Ukrainian using Google Translate API."""
    logger.info("Translating text RU -> UA using Google Translate...")
    try:
        google_creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not google_creds_path or not os.path.exists(google_creds_path):
             logger.warning("Google credentials not configured correctly. Skipping Google Translate.")
             return text
        translate_client = translate.Client()
        paragraphs = text.split('\n'); translated_paragraphs = []
        for paragraph in paragraphs:
            if paragraph.strip(): 
                # Run sync Google call in thread
                result = await asyncio.to_thread(translate_client.translate, paragraph, target_language='uk', source_language='ru')
                translated_paragraphs.append(result['translatedText'])
            else: translated_paragraphs.append(paragraph)
        translated_text = '\n'.join(translated_paragraphs)
        translated_text = translated_text.replace(' <a', '<a').replace('</a> ', '</a>')
        translated_text = re.sub(r'([a-zA-Zа-яА-ЯёЁіІїЇєЄ])<a', r'\1 <a', translated_text)
        translated_text = translated_text.replace(" :", ":"); translated_text = re.sub(r'\s{2,}', ' ', translated_text).strip()
        translated_text = translated_text.replace("[оновлено]", "[Оновлено]").replace("Рік виконання", "Рік виходу")
        return sanitize_html_for_telegram(translated_text)
    except Exception as e:
        logger.error(f"Error during Google translation: {e}")
        return text

async def translate_ru_to_ua_gpt(text: str, model: str = "gpt-4o-mini") -> str:
    """
    Translates text from Russian to Ukrainian using GPT, requesting logical formatting
    and allowing light emphasis for readability.

    :param text: Text to translate.
    :param model: GPT model to use. Defaults to "gpt-4o-mini".
    :return: Translated text or original text on error.
    """
    if not openai_client:
        logger.error("Error: OpenAI client not available for GPT translation.")
        return text

    logger.info(f"Translating text RU -> UA using GPT model: {model}...")

    # --- Updated Prompt ---
    prompt = (
        f"Translate the following text from Russian to Ukrainian, making it highly readable and visually appealing for a Telegram post.\n\n"
        f"**Translation Rules:**\n"
        f"1.  **Language Naming:** If the text mentions 'Russian language' (русский язык), translate it ONLY as 'мова росії', 'москальська', or 'російська'. NEVER use 'руська'.\n"
        f"2.  **Improve Text:** You are encouraged to slightly improve the flow, add logical spacing (newlines), use bullet points (e.g., •) or markers for lists, and use bold/italics to make the text better readable.\n"
        f"3.  **No HTML Lists:** NEVER use HTML tags like <ul> or <li>. Use plain text bullet characters (•) for lists.\n"
        f"4.  **Emojis:** Use relevant emojis sparingly to enhance visual appeal, but do not overdo it.\n"
        f"5.  **Preserve Content:** Do not lose ANY original information. Keep the meaning and all technical details intact.\n"
        f"6.  **Telegram HTML Tags:** Strictly use ONLY these HTML tags: <b>, <i>, <u>, <s>, <tg-spoiler>, <a>, <code>, <pre>. Ensure all tags are correctly closed.\n"
        f"7.  **Untranslated items:** Keep English words, brand names, and words starting with # (hashtags) untranslated.\n"
        f"8.  **No Markdown:** Do NOT use markdown like **bold** (use <b>bold</b> instead).\n\n"
        f"**Text to translate:**\n{text}\n\n**Beautiful Ukrainian Translation (Telegram HTML):**"
    )
    # --- End of Updated Prompt ---

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        translated_text = response.choices[0].message.content

        # Clean trailing markdown code fences and whitespace
        cleaned_text = translated_text.strip()
        cleaned_text = re.sub(r"^(```html|```)", "", cleaned_text).strip()
        cleaned_text = re.sub(r"```$", "", cleaned_text).strip()
        
        # FINAL SANITIZATION: Clean any unsupported tags from GPT response
        final_text = sanitize_html_for_telegram(cleaned_text)
        
        return final_text

    except Exception as e:
        logger.error(f"Error during GPT translation: {e}")
        return text # Fallback to original text

# Function translate_ru_to_ua_deepl remains the same (using aiohttp)
async def translate_ru_to_ua_deepl(text: str) -> str:
    """Translates text from Russian to Ukrainian using DeepL API."""
    if not DEEPL_API_KEY: return text
    logger.info("Translating text RU -> UA using DeepL...")
    url = "https://api-free.deepl.com/v2/translate"
    params = {"auth_key": DEEPL_API_KEY, "text": text, "source_lang": "RU", "target_lang": "UK", "tag_handling": "html"}
    session = get_session()
    try:
        async with session.post(url, data=params, timeout=20) as response:
            response.raise_for_status()
            data = await response.json()
            translated_text = data['translations'][0]['text']
            return sanitize_html_for_telegram(translated_text)
    except Exception as e:
        logger.error(f"Error during DeepL translation: {e}")
    return text
# --- END OF FILE translation.py ---