# --- START OF FILE ai_validator.py ---
from core.settings_loader import openai_client # Import OpenAI client
from typing import Optional
import re # Import re for cleaning title in prompt
import logging

logger = logging.getLogger(__name__)

async def validate_yt_title_with_gpt(searched_title: str, found_yt_title: str, model: str = "gpt-5.4-nano") -> bool:
    """
    Validates if a found YouTube title is relevant to the searched game title.
    First tries a simple string check (no GPT needed), then falls back to GPT.

    Args:
        searched_title: The game title that was searched for.
        found_yt_title: The title of the YouTube video found by the search.
        model: The OpenAI model to use for validation.

    Returns:
        True if the video is relevant, False otherwise.
    """
    # Clean title for comparison (remove brackets/parentheses)
    prompt_searched_title = re.sub(r'\[.*?\]|\(.*?\)', '', searched_title).strip()
    clean_searched = prompt_searched_title.lower().strip()
    clean_found = found_yt_title.lower().strip()

    # --- Pre-check: if searched title is literally contained in found title → always True ---
    if clean_searched and clean_searched in clean_found:
        logger.info(f"YouTube validation: '{searched_title}' found in '{found_yt_title}' — accepted without GPT.")
        return True

    if not openai_client:
        logger.warning("OpenAI client unavailable for YouTube title validation. Skipping validation, assuming False.")
        return False

    prompt = (
        f"You are a game title validation assistant. Your task is to determine if the 'Found YouTube Video Title' "
        f"is relevant (likely an official trailer, gameplay video, review, or closely related content) "
        f"for the 'Searched Game Title'. Consider different languages, subtitles, and common variations "
        f"(e.g., 'Gameplay Trailer' vs 'Trailer').\n\n"
        f"Searched Game Title: \"{prompt_searched_title}\"\n"
        f"Found YouTube Video Title: \"{found_yt_title}\"\n\n"
        f"Is the YouTube video title relevant and specifically about the searched game? Respond ONLY with True or False."
    )

    fallback_model = "gpt-4o-mini"

    for attempt_model in (model, fallback_model):
        try:
            use_new_param = attempt_model.startswith(('gpt-5', 'o1', 'o3', 'o4'))
            extra = {'max_completion_tokens': 10} if use_new_param else {'max_tokens': 10}
            response = await openai_client.chat.completions.create(
                model=attempt_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                **extra,
            )
            result_text = response.choices[0].message.content.strip().lower()
            logger.debug(f"GPT Validation ({attempt_model}) response: '{result_text}'")

            is_relevant = result_text.startswith("true")
            if is_relevant:
                logger.info(f"GPT Validation ({attempt_model}): RELEVANT.")
            else:
                logger.info(f"GPT Validation ({attempt_model}): NOT relevant (response: '{result_text}').")
            return is_relevant

        except Exception as e:
            logger.error(f"Error during GPT validation with {attempt_model}: {e}")
            if attempt_model == fallback_model:
                return False  # Both models failed

    return False  # unreachable

async def summarize_description_with_ai(description: str, target_length: int = 6000, model: str = "gpt-5.4-nano") -> str:
    """
    Summarizes a long description using an AI model to fit within a target length.

    Args:
        description: The long text to summarize.
        target_length: The desired character length for the summary.
        model: The OpenAI model to use.

    Returns:
        The summarized description, or the original if an error occurs.
    """
    if not openai_client:
        logger.warning("OpenAI client unavailable for summarization. Returning original description.")
        return description

    logger.info(f"Description length ({len(description)}) is too long. Summarizing with {model}...")

    prompt = (
        f"You are a professional editor for a Telegram channel. Your task is to summarize the following game description (which could be for a single game or a large collection) to be under {target_length} characters.\n\n"
        f"**CRITICAL GOAL:** Preserve the 'essence' and minimize loss of specific meaning. The user must not miss important titles or unique features of this release.\n\n"
        f"**Strategy for Success:**\n"
        f"1. **Content Preservation:** If the description contains a list of games, mention the total count clearly. Keep only a few most important titles and suggest checking the full list on the original tracker page.\n"
        f"2. **Structure:** Use bullet points for lists. Do NOT use any Markdown formatting like '**' for bold or '*' for lists. Use ONLY HTML tags for formatting if needed.\n"
        f"3. **Technical Details:** Always keep 'Особенности' (Features) and 'Системные требования' (System Requirements), but summarize the text within those blocks to be more concise.\n"
        f"4. **Formatting:** You MUST use ONLY essential HTML tags like `<b>`, `<i>`, and `<a>`. NEVER use Markdown (e.g., no `**bold**`, use `<b>bold</b>`). Ensure all tags are correctly closed.\n"
        f"5. **Language:** Use the same language as the original text (Russian).\n"
        f"6. **Constraint:** Strictly stay under {target_length} characters while following the rules above.\n\n"
        f"**Original Text:**\n{description}\n\n"
        f"**Summarized Text (ESSENCE PRESERVED, under {target_length} chars, ONLY HTML FORMATTING):**"
    )

    try:
        use_new_param = model.startswith(('gpt-5', 'o1', 'o3', 'o4'))
        extra = {'max_completion_tokens': 2048} if use_new_param else {'max_tokens': 2048}
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            **extra,
        )
        from utils.html_utils import sanitize_html_for_telegram
        summary = response.choices[0].message.content.strip()
        # Final sanitization to remove any unsupported tags GPT might have included
        summary = sanitize_html_for_telegram(summary)
        logger.info(f"Successfully summarized description. New length: {len(summary)}")
        return summary
    except Exception as e:
        logger.error(f"Error during AI summarization: {e}")
        return description # Fallback to original text on error
