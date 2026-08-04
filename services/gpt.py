"""Single entry point for OpenAI chat calls: primary model, one fallback, no duplication."""
import logging
from typing import Optional

from core.settings_loader import openai_client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-nano"
FALLBACK_MODEL = "gpt-4o-mini"


async def complete(
    prompt: str,
    max_tokens: int,
    model: str = DEFAULT_MODEL,
    temperature: Optional[float] = None,
    label: str = "GPT",
) -> Optional[str]:
    """Ask `model`, retry once on FALLBACK_MODEL, return raw content or None if both fail."""
    if not openai_client:
        logger.error(f"{label}: OpenAI client not available.")
        return None

    for attempt in (model, FALLBACK_MODEL):
        try:
            # New-generation models require max_completion_tokens instead of max_tokens
            limit = 'max_completion_tokens' if attempt.startswith(('gpt-5', 'o1', 'o3', 'o4')) else 'max_tokens'
            extra = {limit: max_tokens}
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
            logger.error(f"{label}: error with {attempt}: {e}")

    return None
