import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from services import platform_ai as ai

API = "https://api.github.com/repos/o/game"
GOOD = json.dumps({"sources": [{"api_url": API, "platform": "Switch", "description": "Порт гри"}]})


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HOMEBREW_CLASSIFIER_MODEL", raising=False)
    monkeypatch.setitem(ai.settings, "ANTHROPIC_API_KEY", "test-secret")
    monkeypatch.setitem(ai.settings, "HOMEBREW_CLASSIFIER_MODEL", "claude-haiku-5-5")
    response = SimpleNamespace(status=200, json=AsyncMock(return_value={
        "model": "claude-haiku-5-5", "stop_reason": "end_turn",
        "content": [{"type": "text", "text": GOOD}], "usage": {"input_tokens": 50, "output_tokens": 30}}))
    context = AsyncMock()
    context.__aenter__.return_value = response
    post = Mock(return_value=context)
    monkeypatch.setattr(ai, "get_session", lambda: SimpleNamespace(post=post))
    backup = AsyncMock(return_value=GOOD)
    monkeypatch.setattr(ai.gpt, "complete", backup)
    return response, post, backup


@pytest.mark.asyncio
async def test_haiku_success_does_not_spend_on_backup(provider):
    _, post, backup = provider
    assert await ai.complete("Classify", {API}) == GOOD
    backup.assert_not_awaited()
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "claude-haiku-5-5" and "temperature" not in payload
    assert payload["output_config"]["effort"] == "low"
    schema = payload["output_config"]["format"]["schema"]
    assert schema["properties"]["sources"]["items"]["properties"]["api_url"]["enum"] == [API]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout", "json", "invented", "truncated"])
async def test_anthropic_failure_uses_openrouter(provider, failure, caplog):
    response, post, backup = provider
    if failure == "http": response.status = 402
    if failure == "timeout": post.side_effect = TimeoutError()
    if failure == "json": response.json.return_value["content"][0]["text"] = "bad JSON"
    if failure == "invented": response.json.return_value["content"][0]["text"] = GOOD.replace("o/game", "fake/game")
    if failure == "truncated": response.json.return_value["stop_reason"] = "max_tokens"
    assert await ai.complete("Classify", {API}) == GOOD
    backup.assert_awaited_once()
    assert "test-secret" not in caplog.text


@pytest.mark.asyncio
async def test_missing_key_uses_existing_chain(provider, monkeypatch):
    _, post, backup = provider
    monkeypatch.setitem(ai.settings, "ANTHROPIC_API_KEY", None)
    assert await ai.complete("Classify", {API}) == GOOD
    post.assert_not_called()
    backup.assert_awaited_once()


@pytest.mark.asyncio
async def test_sonnet_can_be_selected_without_code_changes(provider, monkeypatch):
    _, post, _ = provider
    monkeypatch.setenv("HOMEBREW_CLASSIFIER_MODEL", "claude-sonnet-5-5")
    await ai.complete("Classify", {API})
    assert post.call_args.kwargs["json"]["model"] == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_invalid_openrouter_answer_tries_next_model(monkeypatch):
    from services import gpt
    response = lambda text: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    create = AsyncMock(side_effect=[response("bad JSON"), response(GOOD)])
    monkeypatch.setattr(gpt, "openai_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assert await gpt.complete("Classify", 1800, validate=lambda raw: ai.validate(raw, {API})) == GOOD
    assert [c.kwargs["model"] for c in create.call_args_list] == [gpt.DEFAULT_MODEL, gpt.FALLBACK_MODEL]
