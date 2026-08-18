# --- START OF FILE translation.py ---
import asyncio
import hashlib
import json
import logging
import os
import re
from typing import Optional

from core.settings_loader import openai_client
from services import gpt
from utils.html_utils import sanitize_html_for_telegram

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join("data", "translations_cache.json")
_cache_memory: Optional[dict] = None


def _get_cache() -> dict:
    """Load persistent translation cache."""
    global _cache_memory
    if _cache_memory is None:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    _cache_memory = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load translation cache: {e}")
                _cache_memory = {}
        else:
            _cache_memory = {}
    return _cache_memory


def _save_cache() -> None:
    """Persist translation cache to disk."""
    if _cache_memory is not None:
        try:
            os.makedirs("data", exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_cache_memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save translation cache: {e}")


# Translate RU to UA function with select exact translate function
async def translate_ru_to_ua(text: str) -> str:
    """
    Translates text from Russian to Ukrainian using the preferred method.
    Currently set to use GPT/OpenRouter if available, otherwise returns original text.
    """
    if openai_client:
        logger.info("Translating text RU -> UA using OpenRouter/GPT...")
        return await translate_ru_to_ua_gpt(text)
    else:
        logger.warning("OpenAI/OpenRouter client not available for translation. Returning original text.")
        return text  # Fallback if client failed initialization


async def translate_ru_to_ua_gpt(text: str, model: str = gpt.DEFAULT_MODEL) -> str:
    """
    Translates text from Russian to Ukrainian using OpenRouter/GPT, requesting logical formatting
    and allowing light emphasis for readability. Uses persistent disk cache.

    :param text: Text to translate.
    :param model: Model to use. Defaults to gpt.DEFAULT_MODEL (openai/gpt-5.6-luna).
    :return: Translated text or original text on error.
    """
    if not text or not text.strip():
        return text

    # Check persistent cache
    cache = _get_cache()
    text_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    if text_hash in cache:
        logger.info("Translation found in persistent cache. Skipping LLM request.")
        return cache[text_hash]

    logger.info(f"Translating text RU -> UA using model: {model}...")

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
        f"3.  **Compact Density:** Keep simple technical parameters (Year, Genre, Publisher, Format, Language, Multiplayer, Age rating, etc.) on consecutive lines with NO blank lines between them. However, major logical sections (such as Description/Опис, Features/Особливості, Additional Info/Дод. інформація, Changelog/Оновлено, System Requirements/Системні вимоги) MUST be separated by a blank line (double newline) from each other and from the metadata block.\n"
        f"4.  **No HTML Lists:** NEVER use HTML tags like <ul> or <li>. Use plain text bullet characters (•) for lists.\n"
        f"5.  **Emojis:** Use relevant emojis sparingly to enhance visual appeal, but do not overdo it.\n"
        f"6.  **Preserve Content:** Do not lose ANY original information. Keep the meaning and all technical details intact.\n"
        f"7.  **Telegram HTML Tags:** Strictly use ONLY these HTML tags: <b>, <i>, <u>, <s>, <tg-spoiler>, <a>, <code>, <pre>, <blockquote>. Ensure all tags are correctly closed.\n"
        f"8.  **Untranslated items:** Keep English words, brand names, and words starting with # (hashtags) untranslated.\n"
        f"9.  **No Markdown:** Do NOT use markdown like **bold** (use <b>bold</b> instead).\n"
        f"10. **Line Stability & Link Unity (STRICT):** Do NOT merge paragraphs separated by ###GAP### (if present). Preserve the line unity of the input. If a line contains a link (<a> tag), the entire line INCLUDING the text before and after the link MUST remain on a single line in the output. NEVER add newlines inside or around <a> tags.\n"
        f"11. **Quote Unity:** Do NOT break a single <blockquote> block into multiple ones. All content between the input <blockquote> tags MUST remain inside a single pair of tags in the output.\n"
        f"12. **Preserve Markers:** DO NOT remove or replace list markers (like •, -, *). Keep them exactly as they are in the input.\n"
        f"13. **Token Preservation (CRITICAL):** The tokens XBQSX and XBQEX are structural markers for blockquotes. Preserve them EXACTLY as-is in the output. Each XBQSX marker MUST always start on a new line and have a newline immediately after it (e.g. \nXBQSX\n). Each XBQEX marker MUST always have a newline before it, and end with a newline (e.g. \nXBQEX\n). NEVER add more XBQSX/XBQEX tokens, NEVER remove them, and NEVER split content between them. Also, NEVER use the <blockquote> tag yourself; ONLY use XBQSX for start and XBQEX for end.\n"
        f"14. **Join Sentences (CRITICAL):** The input HTML may contain arbitrary single line breaks (\\n) in the middle of sentences due to code wrapping. You MUST remove these arbitrary mid-sentence line breaks and join the sentence onto a single continuous line. However, strictly preserve intentional paragraph breaks (double line breaks) and line breaks before list markers (•).\n"
        f"15. **No Gaps in Quotes:** NEVER use double newlines (\\n\\n) inside a blockquote (between XBQSX and XBQEX). Use only single newlines (\\n).\n"
        f"16. **Clean Updates (CRITICAL):** If the text contains update notes or changelogs, strictly REMOVE any thanks, credits, or mentions of specific people who helped with the update or release. Keep ONLY the factual, technical details of what was changed, fixed, or added.\n"
        f"17. **Inline Tags:** Do NOT add line breaks before or after inline HTML tags like <b>, <i>, <u>, <s>, <a>. Keep them on the same line as the surrounding text. Note that XBQSX and XBQEX are block tokens, not inline tags, so they MUST be on their own lines.\n\n"
        f"**Text to translate:**\n{text}\n\n**Beautiful Ukrainian Translation (Telegram HTML):**"
    )
    # --- End of Updated Prompt ---

    translated_text = await gpt.complete(prompt, max_tokens=8192, model=model, label="Translation")
    if translated_text is None:
        return text  # Both models failed — return original

    # Clean trailing markdown code fences and whitespace
    cleaned_text = translated_text.strip()
    cleaned_text = re.sub(r"^(```html|```)", "", cleaned_text).strip()
    cleaned_text = re.sub(r"```$", "", cleaned_text).strip()

    # Clean up prompt hallucination if GPT repeated/mimicked the prompt suffix
    cleaned_text = re.sub(r'(?i)\*\*Beautiful Ukrainian Translation.*?:\*\*', '', cleaned_text).strip()
    cleaned_text = re.sub(r'(?i)\bBeautiful Ukrainian Translation.*?:\s*', '', cleaned_text).strip()

    # --- Post-translation structural cleaning ---
    # 1. Clean up newlines around blockquote markers
    cleaned_text = re.sub(r'\s*XBQSX\s*', '\nXBQSX\n', cleaned_text)
    cleaned_text = re.sub(r'\s*XBQEX\s*', '\nXBQEX\n', cleaned_text)

    # 2. Snap floating colons back to the bold tags outside the blockquote
    cleaned_text = re.sub(
        r'(<b>[^<:]+</b>)\s*\n*XBQSX\s*\n*\s*:\s*',
        r'\1:\nXBQSX\n',
        cleaned_text
    )
    cleaned_text = re.sub(
        r'(<b>[^<]+:</b>|<b>[^<]+</b>:)\s*\n*XBQSX\s*\n*\s*:\s*',
        r'\1\nXBQSX\n',
        cleaned_text
    )

    # FINAL SANITIZATION: Clean any unsupported tags from GPT response
    logger.debug(f"GPT Response (cleaned bytes {len(cleaned_text)}): {cleaned_text[:300]}...")

    # Replace accidental BBCode with HTML
    cleaned_text = re.sub(r'\[b\](.*?)\[/b\]', r'<b>\1</b>', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r'\[i\](.*?)\[/i\]', r'<i>\1</i>', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r'\[s\](.*?)\[/s\]', r'<s>\1</s>', cleaned_text, flags=re.IGNORECASE | re.DOTALL)

    final_text = sanitize_html_for_telegram(cleaned_text)

    # AGGRESSIVE MERGE OF ALL POSSIBLE BLOCKQUOTE MARKERS
    final_text = final_text.replace("<blockquote>", "XBQSX").replace("</blockquote>", "XBQEX")
    final_text = re.sub(r'XBQEX[\s\S]*?XBQSX', 'XBQEXXBQSX', final_text, flags=re.IGNORECASE)
    final_text = final_text.replace("XBQSX", "<blockquote>")
    final_text = final_text.replace("XBQEX", "</blockquote>")
    final_text = re.sub(r'</blockquote>[ \t\n\r]*<blockquote>', '</blockquote><blockquote>', final_text, flags=re.IGNORECASE)
    final_text = re.sub(r'\n{3,}', '\n\n', final_text).strip()

    # Save to persistent cache
    cache[text_hash] = final_text
    _save_cache()

    logger.debug(f"GPT Response (final bytes {len(final_text)}): {final_text[:300]}...")
    return final_text


async def translate_short_description(text: str, model: str = gpt.DEFAULT_MODEL) -> str:
    """
    Summarizes and translates a homebrew app description into 1 concise Ukrainian sentence.
    Uses persistent disk cache.

    :param text: App description text (any language).
    :param model: Model to use (primary).
    :return: 1-sentence Ukrainian description, or original text on error.
    """
    if not text or not text.strip():
        return text

    cache = _get_cache()
    short_hash = f"short_{hashlib.sha256(text.strip().encode('utf-8')).hexdigest()}"
    if short_hash in cache:
        logger.info("Short description found in cache. Skipping LLM request.")
        return cache[short_hash]

    prompt = (
        f"Summarize the following app description into exactly ONE short sentence in Ukrainian.\n\n"
        f"**Rules:**\n"
        f"1. ONE sentence only — no more.\n"
        f"2. Describe only WHAT the app/game IS and WHAT it does for the user.\n"
        f"3. Do NOT include technical implementation details (e.g. how a port was made, "
        f"what libraries it uses, how it loads executables, patching methods, etc.)\n"
        f"4. Example: instead of 'port that loads an ARMv7 binary into memory...', "
        f"write 'Порт гри Beat Hazard 2 для PS Vita.'\n"
        f"5. Keep English brand names, game titles, and technical terms untranslated.\n"
        f"6. Use natural, readable Ukrainian. End with a period.\n"
        f"7. STRICT: Do NOT add obvious, redundant, or wordy explanations like 'який дозволяє грати...', "
        f"'який дає змогу...', 'для консолі...', 'це порт...', 'щоб ви могли грати...'. "
        f"Keep it as concise and direct as possible. Example: 'Порт гри Adventures of Mana для Nintendo Switch.' "
        f"instead of 'Порт гри Adventures of Mana для Switch, який дозволяє вам грати в цю гру на консолі.'\n\n"
        f"**App description:**\n{text}\n\n**One-sentence Ukrainian summary:**"
    )

    logger.info(f"Summarizing description using model: {model}...")
    translated_text = await gpt.complete(prompt, max_tokens=100, model=model, temperature=0.3,
                                         label="Description summarization")
    if translated_text is None:
        return text  # Both models failed — caller decides whether to cache

    # Clean any markdown artifacts
    translated_text = re.sub(r"^(```html|```)", "", translated_text.strip()).strip()
    result = re.sub(r"```$", "", translated_text).strip()

    cache[short_hash] = result
    _save_cache()
    return result
# --- END OF FILE translation.py ---
