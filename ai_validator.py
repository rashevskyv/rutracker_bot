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
# --- END OF FILE ai_validator.py ---