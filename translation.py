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

    # Check if text contains GAP markers
    has_gap_markers = "###GAP###" in text
    gap_instruction = ""
    if has_gap_markers:
        gap_instruction = "2.  **Structural Spacing & Readability:** You will see '###GAP###' markers in the text. You MUST preserve these markers exactly as they are on their own lines. To make the description text look beautiful and highly readable, you are ENCOURAGED to space it out by adding empty lines between logical paragraphs or sections.\n"

    # --- Updated Prompt ---
    prompt = (
        f"Translate the following text from Russian to Ukrainian, making it highly readable and visually appealing for a Telegram post.\n\n"
        f"**Translation Rules:**\n"
        f"1.  **Language Naming:** If the text mentions 'Russian language' (русский язык), translate it ONLY as 'мова росії', 'москальська', or 'російська'. NEVER use 'руська'.\n"
        f"{gap_instruction}"
        f"{gap_instruction}"
        f"3.  **Compact Density:** Keep technical parameters (Year, Genre, etc.) on consecutive lines with NO blank lines between them. However, for the 'Description' text and especially inside <blockquote> blocks, you MUST preserve the original structural line breaks and tags for readability.\n"
        f"4.  **No HTML Lists:** NEVER use HTML tags like <ul> or <li>. Use plain text bullet characters (•) for lists.\n"
        f"5.  **Emojis:** Use relevant emojis sparingly to enhance visual appeal, but do not overdo it.\n"
        f"6.  **Preserve Content:** Do not lose ANY original information. Keep the meaning and all technical details intact.\n"
        f"7.  **Telegram HTML Tags:** Strictly use ONLY these HTML tags: <b>, <i>, <u>, <s>, <tg-spoiler>, <a>, <code>, <pre>, <blockquote>. Ensure all tags are correctly closed.\n"
        f"8.  **Untranslated items:** Keep English words, brand names, and words starting with # (hashtags) untranslated.\n"
        f"9.  **No Markdown:** Do NOT use markdown like **bold** (use <b>bold</b> instead).\n"
        f"10. **Line Stability & Link Unity (STRICT):** Do NOT merge paragraphs separated by ###GAP### (if present). Preserve the line unity of the input. If a line contains a link (<a> tag), the entire line INCLUDING the text before and after the link MUST remain on a single line in the output. NEVER add newlines inside or around <a> tags.\n"
        f"11. **Quote Unity:** Do NOT break a single <blockquote> block into multiple ones. All content between the input <blockquote> tags MUST remain inside a single pair of tags in the output.\n"
        f"12. **Preserve Markers:** DO NOT remove or replace list markers (like •, -, *). Keep them exactly as they are in the input.\n"
        f"13. **Token Preservation (CRITICAL):** The tokens XBQSX and XBQEX are structural markers for blockquotes. Preserve them EXACTLY as-is in the output. NEVER add more XBQSX/XBQEX tokens, NEVER remove them, and NEVER split content between them. Also, NEVER use the <blockquote> tag yourself; ONLY use XBQSX for start and XBQEX for end.\n"
        f"14. **Join Sentences (CRITICAL):** The input HTML may contain arbitrary single line breaks (\\n) in the middle of sentences due to code wrapping. You MUST remove these arbitrary mid-sentence line breaks and join the sentence onto a single continuous line. However, strictly preserve intentional paragraph breaks (double line breaks) and line breaks before list markers (•).\n"
        f"15. **No Gaps in Quotes:** NEVER use double newlines (\\n\\n) inside a blockquote (between XBQSX and XBQEX). Use only single newlines (\\n).\n\n"
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
        logger.debug(f"GPT Response (cleaned bytes {len(cleaned_text)}): {cleaned_text[:300]}...")
        
        # DEBUG: Write step-by-step to file
        with open("debug_bq_pipeline.txt", "w", encoding="utf-8") as dbg:
            dbg.write("=== STEP 1: RAW GPT OUTPUT (cleaned) ===\n")
            dbg.write(cleaned_text)
            dbg.write("\n\n")
            
            # Count tokens/tags
            bqsx_count = cleaned_text.upper().count("XBQSX")
            bqex_count = cleaned_text.upper().count("XBQEX")
            bq_open = cleaned_text.lower().count("<blockquote>")
            bq_close = cleaned_text.lower().count("</blockquote>")
            dbg.write(f"Tokens: XBQSX={bqsx_count}, XBQEX={bqex_count}\n")
            dbg.write(f"Literal tags: <blockquote>={bq_open}, </blockquote>={bq_close}\n\n")
        
        final_text = sanitize_html_for_telegram(cleaned_text)
        
        with open("debug_bq_pipeline.txt", "a", encoding="utf-8") as dbg:
            dbg.write("=== STEP 2: AFTER sanitize_html_for_telegram ===\n")
            dbg.write(final_text)
            dbg.write("\n\n")
            bqsx_count = final_text.upper().count("XBQSX")
            bqex_count = final_text.upper().count("XBQEX")
            bq_open = final_text.lower().count("<blockquote>")
            bq_close = final_text.lower().count("</blockquote>")
            dbg.write(f"Tokens: XBQSX={bqsx_count}, XBQEX={bqex_count}\n")
            dbg.write(f"Literal tags: <blockquote>={bq_open}, </blockquote>={bq_close}\n\n")
        
        # AGGRESSIVE MERGE OF ALL POSSIBLE BLOCKQUOTE MARKERS
        # First, normalize any literal tags GPT might have used back to tokens
        final_text = final_text.replace("<blockquote>", "XBQSX").replace("</blockquote>", "XBQEX")
        
        with open("debug_bq_pipeline.txt", "a", encoding="utf-8") as dbg:
            dbg.write("=== STEP 3: AFTER normalize tags->tokens ===\n")
            bqsx_count = final_text.upper().count("XBQSX")
            bqex_count = final_text.upper().count("XBQEX")
            dbg.write(f"Tokens: XBQSX={bqsx_count}, XBQEX={bqex_count}\n")
            # Find all XBQEX...XBQSX gaps
            import re as re2
            gaps = list(re2.finditer(r'XBQEX(.*?)XBQSX', final_text, flags=re.DOTALL|re.IGNORECASE))
            dbg.write(f"Gaps between XBQEX and XBQSX: {len(gaps)}\n")
            for gi, gap in enumerate(gaps):
                dbg.write(f"  Gap {gi}: [{repr(gap.group(1))}]\n")
            dbg.write("\n")
        
        # Merge any XBQEX ... XBQSX pairs
        # Allow ANY content between them (not just whitespace) since GPT might insert empty tags like <b></b>
        final_text = re.sub(r'XBQEX[\s\S]*?XBQSX', 'XBQEXXBQSX', final_text, flags=re.IGNORECASE)
        
        with open("debug_bq_pipeline.txt", "a", encoding="utf-8") as dbg:
            dbg.write("=== STEP 4: AFTER merge XBQEX...XBQSX ===\n")
            bqsx_count = final_text.upper().count("XBQSX")
            bqex_count = final_text.upper().count("XBQEX")
            dbg.write(f"Tokens: XBQSX={bqsx_count}, XBQEX={bqex_count}\n\n")
        
        # RESTORE blockquote tokens
        final_text = final_text.replace("XBQSX", "<blockquote>")
        final_text = final_text.replace("XBQEX", "</blockquote>")
        
        # Merge any remaining fragmented blockquotes tightly
        final_text = re.sub(r'</blockquote>[ \t\n\r]*<blockquote>', '</blockquote><blockquote>', final_text, flags=re.IGNORECASE)
        
        # Remove triple+ newlines and leading/trailing whitespace
        final_text = re.sub(r'\n{3,}', '\n\n', final_text).strip()
        
        with open("debug_bq_pipeline.txt", "a", encoding="utf-8") as dbg:
            dbg.write("=== STEP 5: FINAL OUTPUT ===\n")
            dbg.write(final_text)
            dbg.write("\n")
        
        logger.debug(f"GPT Response (final bytes {len(final_text)}): {final_text[:300]}...")
        
        return final_text

    except Exception as e:
        logger.error(f"Error during GPT translation: {e}")
        return text # Fallback to original text

async def translate_short_description(text: str, model: str = "gpt-4o-mini") -> str:
    """
    Translates short descriptions (1-2 sentences) from Russian to Ukrainian.
    Designed for homebrew app descriptions - keeps them concise without adding extra content.

    :param text: Short text to translate (typically 1-2 sentences).
    :param model: GPT model to use. Defaults to "gpt-4o-mini".
    :return: Translated text or original text on error.
    """
    if not openai_client:
        logger.error("Error: OpenAI client not available for GPT translation.")
        return text

    logger.info(f"Translating short description RU -> UA using GPT model: {model}...")

    prompt = (
        f"Translate the following short text from Russian to Ukrainian.\n\n"
        f"**Rules:**\n"
        f"1. Keep it SHORT - translate exactly what's given, don't add extra information\n"
        f"2. Preserve HTML tags like <b>, <i> exactly as they are\n"
        f"3. Keep the same structure and length as the original\n"
        f"4. Use natural, readable Ukrainian\n"
        f"5. Translate 'русский язык' as 'російська' or 'москальська', NEVER 'руська'\n"
        f"6. Keep English words, brand names, and technical terms untranslated\n\n"
        f"**Text to translate:**\n{text}\n\n**Ukrainian translation:**"
    )

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        translated_text = response.choices[0].message.content.strip()

        # Clean any markdown artifacts
        translated_text = re.sub(r"^(```html|```)", "", translated_text).strip()
        translated_text = re.sub(r"```$", "", translated_text).strip()

        return translated_text

    except Exception as e:
        logger.error(f"Error during GPT translation: {e}")
        return text

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