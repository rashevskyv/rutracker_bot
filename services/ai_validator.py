# --- START OF FILE ai_validator.py ---
from services import gpt
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)

_STOP_WORDS = {
    'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for',
    'is', 'it', 'its', 'be', 'as', 'by', 'with', 'that', 'this', 'from',
}


def _word_overlap_ratio(searched: str, found: str) -> float:
    """Return ratio of significant searched words that appear in found title."""
    words = {w for w in re.findall(r'\w+', searched.lower()) if len(w) > 2 and w not in _STOP_WORDS}
    if not words:
        return 0.0
    found_lower = found.lower()
    matched = sum(1 for w in words if w in found_lower)
    return matched / len(words)


async def validate_yt_title_with_gpt(searched_title: str, found_yt_title: str, model: str = "gpt-5.4-nano") -> bool:
    """
    3-layer validation for YouTube trailer relevance:
      Layer 1 — Exact contains: searched title is a substring of found title.
      Layer 2 — Word overlap: ≥60% of significant words from searched title appear in found title.
      Layer 3 — GPT with structured RELEVANT/NOT_RELEVANT + REASON response.

    Args:
        searched_title: The game title that was searched for.
        found_yt_title: The title of the YouTube video found by the search.
        model: Primary GPT model to use.

    Returns:
        True if the video is considered relevant, False otherwise.
    """
    prompt_searched_title = re.sub(r'\[.*?\]|\(.*?\)', '', searched_title).strip()
    clean_searched = prompt_searched_title.lower().strip()
    clean_found = found_yt_title.lower().strip()

    # --- Layer 1: Exact contains ---
    if clean_searched and clean_searched in clean_found:
        logger.info(f"YT Layer 1 (contains): '{searched_title}' ⊆ '{found_yt_title}' — ACCEPTED")
        return True

    # --- Layer 2: Word overlap ≥ 60% ---
    overlap = _word_overlap_ratio(clean_searched, clean_found)
    if overlap >= 0.6:
        logger.info(f"YT Layer 2 (word overlap {overlap:.0%}): '{searched_title}' ~ '{found_yt_title}' — ACCEPTED")
        return True
    else:
        logger.debug(f"YT Layer 2 (word overlap {overlap:.0%}): below threshold, proceeding to GPT")

    # --- Layer 3: GPT with structured response ---
    prompt = (
        f"You are a strict game trailer validation assistant.\n\n"
        f"Searched Game Title: \"{prompt_searched_title}\"\n"
        f"Found YouTube Video Title: \"{found_yt_title}\"\n\n"
        f"Task: Determine if the YouTube video is specifically about the searched game "
        f"(official trailer, gameplay, announcement, review). "
        f"Consider alternate spellings, subtitles, and localized names.\n\n"
        f"Respond in EXACTLY this format (two lines):\n"
        f"RELEVANT: Yes\n"
        f"REASON: one sentence\n\n"
        f"or:\n"
        f"RELEVANT: No\n"
        f"REASON: one sentence"
    )

    raw = await gpt.complete(prompt, max_tokens=60, model=model, temperature=0.1, label="YT Layer 3")
    if raw is None:
        return False

    raw = raw.strip()
    logger.debug(f"YT Layer 3 GPT raw: {raw!r}")

    # Parse structured response
    relevant_line = next((l for l in raw.splitlines() if l.upper().startswith('RELEVANT:')), '')
    reason_line   = next((l for l in raw.splitlines() if l.upper().startswith('REASON:')), '')
    reason = reason_line.split(':', 1)[1].strip() if ':' in reason_line else ''
    is_relevant = 'yes' in relevant_line.lower()

    logger.info(f"YT Layer 3: {'RELEVANT' if is_relevant else 'NOT RELEVANT'} — {reason}")
    return is_relevant

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

    summary = await gpt.complete(prompt, max_tokens=2048, model=model, temperature=0.5, label="AI summarization")
    if summary is None:
        return description  # Fallback to original text on error

    from utils.html_utils import sanitize_html_for_telegram
    # Final sanitization to remove any unsupported tags GPT might have included
    summary = sanitize_html_for_telegram(summary.strip())
    logger.info(f"Successfully summarized description. New length: {len(summary)}")
    return summary
