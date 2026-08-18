"""Single entry point for OpenAI chat calls: primary model, one fallback, no duplication."""
import logging
from typing import Optional

from core.settings_loader import openai_client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-5.6-luna"
FALLBACK_MODEL = "deepseek/deepseek-v4-flash-0731"
SECONDARY_FALLBACK = "google/gemini-3.5-flash-lite"


async def complete(
    prompt: str,
    max_tokens: int,
    model: str = DEFAULT_MODEL,
    temperature: Optional[float] = None,
    label: str = "GPT",
) -> Optional[str]:
    """Ask `model`, retry once on FALLBACK_MODEL, return raw content or None if both fail."""
    if not openai_client:
        logger.error(f"{label}: OpenAI / OpenRouter client not available.")
        return None

    attempts = [model]
    if FALLBACK_MODEL not in attempts:
        attempts.append(FALLBACK_MODEL)
    if SECONDARY_FALLBACK not in attempts:
        attempts.append(SECONDARY_FALLBACK)

    for attempt in attempts:
        try:
            extra = {"max_tokens": max_tokens}
            if temperature is not None:
                extra['temperature'] = temperature

            response = await openai_client.chat.completions.create(
                model=attempt,
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
            if attempt != model:
                logger.info(f"{label}: used fallback model {attempt}.")
            return response.choices[0].message.content

        except Exception as e:
            logger.warning(f"{label}: error with model {attempt}: {e}")

    return None
