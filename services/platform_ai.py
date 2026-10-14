"""Anthropic first, then the existing OpenRouter fallback chain for platform classification."""
import json
import logging
import os

from core.settings_loader import get_session, get_env_or_setting, settings
from services import gpt

logger = logging.getLogger(__name__)


def validate(raw, candidates):
    data = json.JSONDecoder().raw_decode(raw[raw.index("{"):])[0]
    rows = data["sources"]
    if not isinstance(rows, list):
        raise ValueError("Invalid sources")
    seen = set()
    for row in rows:
        api = row.get("api_url")
        description = row.get("description")
        if (api not in candidates or api in seen or row.get("platform") not in {"Switch", "PC"}
                or not isinstance(description, str) or not 1 <= len(description.strip()) <= 220):
            raise ValueError("Unverified classification")
        seen.add(api)
    return True


async def complete(prompt, candidates):
    key = os.environ.get("ANTHROPIC_API_KEY") or get_env_or_setting(settings, "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    model = os.environ.get("HOMEBREW_CLASSIFIER_MODEL") or settings.get("HOMEBREW_CLASSIFIER_MODEL") or "claude-haiku-5-5"
    if key:
        try:
            schema = {"type": "object", "additionalProperties": False, "required": ["sources"],
                      "properties": {"sources": {"type": "array", "items": {
                          "type": "object", "additionalProperties": False,
                          "required": ["api_url", "platform", "description"], "properties": {
                              "api_url": {"type": "string", "enum": sorted(candidates)},
                              "platform": {"type": "string", "enum": ["Switch", "PC"]},
                              "description": {"type": "string"}}}}}}
            payload = {"model": model, "max_tokens": 1800,
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                       "messages": [{"role": "user", "content": prompt}]}
            async with get_session().post("https://api.anthropic.com/v1/messages", json=payload, timeout=20,
                                          headers={"x-api-key": key, "anthropic-version": "2023-06-01"}) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                data = await response.json()
            usage = data.get("usage", {})
            logger.info("Homebrew platforms: provider=anthropic model=%s input_tokens=%s output_tokens=%s",
                        data.get("model", model), usage.get("input_tokens"), usage.get("output_tokens"))
            if data.get("stop_reason") not in {"end_turn", "stop_sequence"}:
                raise ValueError("Incomplete Anthropic response")
            raw = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
            validate(raw, candidates)
            return raw
        except Exception as error:
            logger.warning("Homebrew platforms: Anthropic failed (%s); trying OpenRouter", type(error).__name__)
    return await gpt.complete(prompt, max_tokens=1800, temperature=0, label="Homebrew platforms",
                              validate=lambda raw: validate(raw, candidates))
