# --- START OF FILE ai_validator.py ---
from settings_loader import openai_client, LOG # Import OpenAI client and LOG flag
from typing import Optional
import re # Import re for cleaning title in prompt

async def validate_yt_title_with_gpt(searched_title: str, found_yt_title: str, model: str = "gpt-4o-mini") -> bool:
    """
    Uses ChatGPT to validate if a found YouTube title is relevant to the searched game title.
    Treats only an exact 'true' (case-insensitive) response as relevant.

    Args:
        searched_title: The game title that was searched for.
        found_yt_title: The title of the YouTube video found by the search.
        model: The OpenAI model to use for validation.

    Returns:
        True if GPT response is exactly 'true', False otherwise (including errors or other responses).
    """
    if not openai_client:
        print("Warning: OpenAI client unavailable for YouTube title validation. Skipping validation, assuming False.")
        return False # Cannot validate without client

    # Clean title for the prompt
    prompt_searched_title = re.sub(r'\[.*?\]', '', searched_title).strip()

    prompt = (
        f"You are a game title validation assistant. Your task is to determine if the 'Found YouTube Video Title' "
        f"is relevant (likely an official trailer, gameplay video, review, or closely related content) "
        f"for the 'Searched Game Title'. Consider different languages, subtitles, and common variations "
        f"(e.g., 'Gameplay Trailer' vs 'Trailer').\n\n"
        f"Searched Game Title: \"{prompt_searched_title}\"\n"
        f"Found YouTube Video Title: \"{found_yt_title}\"\n\n"
        f"Is the YouTube video title relevant and specifically about the searched game? Respond ONLY with True or False."
    )

    if LOG: print(f"Requesting GPT validation for: '{prompt_searched_title}' vs '{found_yt_title}'")

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10, # Expecting short response
            temperature=0.1 # Low temperature
        )
        result_text = response.choices[0].message.content.strip().lower() # Get response, strip whitespace, convert to lowercase
        if LOG: print(f"GPT Validation Raw Response: '{response.choices[0].message.content}', Processed: '{result_text}'")

        # --- Simplified Check ---
        is_relevant = (result_text == "true")
        # ----------------------

        if is_relevant:
            print("GPT Validation: Title judged as RELEVANT.")
        else:
            print(f"GPT Validation: Title judged as NOT relevant (Response was: '{result_text}').")

        return is_relevant

    except Exception as e:
        print(f"Error during GPT validation API call: {e}")
        return False # Default to False on API error

async def summarize_description_with_ai(description: str, target_length: int = 6000, model: str = "gpt-4o-mini") -> str:
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
        print("Warning: OpenAI client unavailable for summarization. Returning original description.")
        return description

    if LOG: print(f"Description length ({len(description)}) is too long. Summarizing with {model}...")

    prompt = (
        f"You are a professional editor for a Telegram channel. Your task is to summarize the following game description (which could be for a single game or a large collection) to be under {target_length} characters.\n\n"
        f"**CRITICAL GOAL:** Preserve the 'essence' and minimize loss of specific meaning. The user must not miss important titles or unique features of this release.\n\n"
        f"**Strategy for Success:**\n"
        f"1. **Content Preservation:** If the description contains a list of games, mention the total count clearly. Keep only a few most important titles and suggest checking the full list on the original tracker page.\n"
        f"2. **Structure:** Use bullet points for lists. Do NOT use bold text for individual items in lists. You can use bold text ONLY for section headers.\n"
        f"3. **Technical Details:** Always keep 'Особенности' (Features) and 'Системные требования' (System Requirements), but summarize the text within those blocks to be more concise.\n"
        f"4. **Formatting:** You MUST preserve essential HTML tags like `<b>`, `<i>`, and `<a>`, but avoid overusing bolding inside lists.\n"
        f"5. **Language:** Use the same language as the original text (Russian).\n"
        f"6. **Constraint:** Strictly stay under {target_length} characters while following the rules above.\n\n"
        f"**Original Text:**\n{description}\n\n"
        f"**Summarized Text (ESSENCE PRESERVED, under {target_length} chars):**"
    )

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,  # Allow for a substantial summary
            temperature=0.5
        )
        summary = response.choices[0].message.content.strip()
        if LOG: print(f"Successfully summarized description. New length: {len(summary)}")
        return summary
    except Exception as e:
        print(f"Error during AI summarization: {e}")
        return description # Fallback to original text on error