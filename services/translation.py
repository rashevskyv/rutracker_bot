# --- START OF FILE translation.py ---
import asyncio
from core.settings_loader import openai_client, get_session
from utils.html_utils import sanitize_html_for_telegram
import re
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

async def translate_ru_to_ua_gpt(text: str, model: str = "gpt-5.4-nano") -> str:
    """
    Translates text from Russian to Ukrainian using GPT, requesting logical formatting
    and allowing light emphasis for readability.

    :param text: Text to translate.
    :param model: GPT model to use. Defaults to "gpt-5.4-nano".
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

    fallback_model = "gpt-4o-mini"

    for attempt_model in (model, fallback_model):
        try:
            use_new_param = attempt_model.startswith(('gpt-5', 'o1', 'o3', 'o4'))
            extra = {'max_completion_tokens': 8192} if use_new_param else {'max_tokens': 8192}
            response = await openai_client.chat.completions.create(
                model=attempt_model,
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
            if attempt_model != model:
                logger.info(f"Translation: used fallback model {attempt_model}.")

            translated_text = response.choices[0].message.content

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
            # If the bold header has no colon, but there is a leading colon inside the blockquote
            cleaned_text = re.sub(
                r'(<b>[^<:]+</b>)\s*\n*XBQSX\s*\n*\s*:\s*',
                r'\1:\nXBQSX\n',
                cleaned_text
            )
            # If the bold header already has a colon, and there is also a colon inside the blockquote
            cleaned_text = re.sub(
                r'(<b>[^<]+:</b>|<b>[^<]+</b>:)\s*\n*XBQSX\s*\n*\s*:\s*',
                r'\1\nXBQSX\n',
                cleaned_text
            )
            # ---------------------------------------------

            # FINAL SANITIZATION: Clean any unsupported tags from GPT response
            logger.debug(f"GPT Response (cleaned bytes {len(cleaned_text)}): {cleaned_text[:300]}...")

            # Replace accidental BBCode with HTML (GPT sometimes hallucinates [b] instead of <b>)
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

            logger.debug(f"GPT Response (final bytes {len(final_text)}): {final_text[:300]}...")
            return final_text

        except Exception as e:
            logger.error(f"Error during GPT translation with {attempt_model}: {e}")
            if attempt_model == fallback_model:
                return text  # Both models failed — return original

    return text  # unreachable

async def translate_short_description(text: str, model: str = "gpt-5.4-nano") -> str:
    """
    Summarizes and translates a homebrew app description into 1 concise Ukrainian sentence.
    Focuses on what the app IS and DOES, not implementation details.
    Falls back to gpt-4o-mini if the primary model fails.

    :param text: App description text (any language).
    :param model: GPT model to use (primary).
    :return: 1-sentence Ukrainian description, or original text on error.
    """
    if not openai_client:
        logger.error("Error: OpenAI client not available for GPT translation.")
        return text

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
        f"6. Use natural, readable Ukrainian. End with a period.\n\n"
        f"**App description:**\n{text}\n\n**One-sentence Ukrainian summary:**"
    )

    fallback_model = "gpt-4o-mini"

    for attempt_model in (model, fallback_model):
        try:
            logger.info(f"Summarizing description using GPT model: {attempt_model}...")
            # New-generation models require max_completion_tokens instead of max_tokens
            use_new_param = attempt_model.startswith(('gpt-5', 'o1', 'o3', 'o4'))
            extra = {'max_completion_tokens': 100} if use_new_param else {'max_tokens': 100}
            response = await openai_client.chat.completions.create(
                model=attempt_model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.3,
                **extra,
            )
            translated_text = response.choices[0].message.content.strip()

            # Clean any markdown artifacts
            translated_text = re.sub(r"^(```html|```)", "", translated_text).strip()
            translated_text = re.sub(r"```$", "", translated_text).strip()

            if attempt_model != model:
                logger.info(f"Used fallback model {attempt_model} for description translation.")
            return translated_text

        except Exception as e:
            logger.error(f"Error during GPT description summarization with {attempt_model}: {e}")
            if attempt_model == fallback_model:
                # Both models failed — return original text (caller decides whether to cache)
                return text

    return text  # unreachable, but satisfies type checker


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
