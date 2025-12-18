# --- START OF FILE ai_validator.py ---
from settings_loader import openai_client, LOG # Import OpenAI client and LOG flag
from typing import Optional
import re # Import re for cleaning title in prompt

def validate_yt_title_with_gpt(searched_title: str, found_yt_title: str, model: str = "gpt-4o-mini") -> bool:
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
        response = openai_client.chat.completions.create(
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

def summarize_description_with_ai(description: str, target_length: int = 6000, model: str = "gpt-4o-mini") -> str:
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
        f"You are an expert content summarizer for a Telegram channel. Your task is to shorten the following game description to be under {target_length} characters. "
        f"The summary must be clear, concise, and retain all essential information, such as game features, plot overview, and system requirements.\n\n"
        f"**Requirements:**\n"
        f"1.  The final text must be under {target_length} characters.\n"
        f"2.  Preserve all original HTML tags (`<b>`, `<i>`, `<a>`, etc.) as they are used for Telegram formatting.\n"
        f"3.  Do not remove or alter the meaning of important sections like 'Особенности игры' (Game Features) or 'Системные требования' (System Requirements). Summarize the content within them if necessary.\n"
        f"4.  The language of the summary must be the same as the original text (Russian).\n"
        f"5.  Ensure the summary is well-structured and easy to read.\n\n"
        f"**Original Text:**\n{description}\n\n"
        f"**Summarized Text (under {target_length} chars):**"
    )

    try:
        response = openai_client.chat.completions.create(
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