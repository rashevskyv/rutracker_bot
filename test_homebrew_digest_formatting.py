"""Unit tests for homebrew digest formatting, sanitization, and changelog compression."""
from datetime import datetime, timedelta
import pytest
from digest.homebrew import (
    clean_markdown_and_whitespace,
    limit_to_sentences,
    sanitize_digest_description,
    HomebrewDigest,
)


def test_clean_markdown_and_whitespace():
    # Markdown links and images
    text = "Visit the official [GitHub Repository](https://github.com/test/repo) for ![Icon](http://img.png) info."
    cleaned = clean_markdown_and_whitespace(text)
    assert "https://github.com" not in cleaned
    assert "GitHub Repository for info." in cleaned

    # Markdown formatting (bold, italics, headers, bullets)
    raw = (
        "**IMPORTANT: Please read!**\n\n"
        "### Features\n"
        "* **Live Telemetry:** Shows CPU info.\n"
        "* **Process Manager:** Kills tasks.\n"
        "- Bullet item with `code`.\n"
    )
    cleaned = clean_markdown_and_whitespace(raw)
    assert "**" not in cleaned
    assert "###" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "\n" not in cleaned
    assert "IMPORTANT: Please read! Features Live Telemetry: Shows CPU info. Process Manager: Kills tasks. Bullet item with code." == cleaned


def test_limit_to_sentences():
    text = "Перше речення. Друге речення! Третє речення? Четверте речення."
    res = limit_to_sentences(text, max_sentences=2)
    assert res == "Перше речення. Друге речення!"

    # Single sentence
    assert limit_to_sentences("Одне речення.", max_sentences=2) == "Одне речення."

    # Empty text
    assert limit_to_sentences("", max_sentences=2) == ""


def test_sanitize_digest_description_clean_input():
    desc = "Порт класичного шутера для Nintendo Switch.\n<i>Виправлено баг зі збереженням та оновлено керування.</i>"
    sanitized = sanitize_digest_description(desc)
    assert sanitized == desc


def test_sanitize_digest_description_giant_markdown_manual():
    raw_manual = (
        "**IMPORTANT: This app requires the companion server to be running on your PC!**\n\n"
        "SysMon is a hardware monitor and macro executor that turns your Nintendo 3DS into a secondary dashboard for your PC.\n\n"
        "### Features\n"
        "* **Live Telemetry:** View your PC's CPU/GPU temperatures, RAM usage, and Fan speeds in real-time on the top screen.\n"
        "* **Process Manager:** View the heaviest processes running on your PC and tap them to instantly kill frozen applications.\n"
        "* **Productivity:** Includes a built-in Pomodoro timer to help you focus.\n\n"
        "**Setup Instructions:**\n"
        "To use this app, you must download and run the lightweight `sysmon-server` background service on your PC.\n"
        "<i>Оновлено SysMon з версії v0.3.1 до v0.3.2</i>"
    )
    sanitized = sanitize_digest_description(raw_manual)
    # Must not have markdown asterisks, hashes, or bullet points
    assert "**" not in sanitized
    assert "###" not in sanitized
    assert "*" not in sanitized
    assert "`" not in sanitized
    # Must have base description limited to 1-2 sentences and changelog in <i>...</i>
    assert sanitized.startswith("IMPORTANT: This app requires the companion server to be running on your PC!")
    assert "<i>Оновлено SysMon з версії v0.3.1 до v0.3.2</i>" in sanitized
    # Total newlines must be exactly 1 (between description and changelog)
    assert sanitized.count("\n") == 1


def test_sanitize_digest_description_changelog_only():
    desc = "<i>Оновлено бібліотеки та додано підтримку нових форматів.</i>"
    sanitized = sanitize_digest_description(desc)
    assert sanitized == desc


def test_sanitize_digest_description_empty():
    assert sanitize_digest_description("") == ""
    assert sanitize_digest_description("   ") == ""
    assert sanitize_digest_description(None) == ""


def test_format_digest_message_sanitizes_markdown(tmp_path):
    data_file = tmp_path / "test_hb_digest.json"
    digest = HomebrewDigest(data_file=str(data_file))

    raw_wall_of_text = (
        "**IMPORTANT: Server needed!**\n\n"
        "SysMon is a hardware monitor for 3DS.\n\n"
        "### Features\n"
        "* **Feature 1:** Do something.\n"
        "* **Feature 2:** Do something else.\n"
        "<i>Оновлено версію до v0.3.3</i>"
    )

    digest.add_entry(
        app_name="SysMon",
        version="v0.3.3",
        release_url="https://github.com/Just-a-Spider/SysMon/releases",
        description=raw_wall_of_text,
        platform="3DS(i)",
        timestamp=datetime.now(),
        release_date=datetime.now(),
        is_new=False
    )

    since = datetime.now() - timedelta(hours=1)
    msg = digest.format_digest_message(since)

    assert msg is not None
    assert "#homebrew_digest:" in msg
    assert "=== 3DS(i) ===" in msg
    # Ensure raw markdown is stripped
    assert "**" not in msg
    assert "###" not in msg
    assert "Feature 1" not in msg  # Should be cut off by 1-2 sentence limit
    assert "<i>Оновлено версію до v0.3.3</i>" in msg


@pytest.mark.asyncio
async def test_get_description_cached_fallback_on_translation_failure(monkeypatch, tmp_path):
    from collect_homebrew_updates import HomebrewUpdatesCollector

    list_file = tmp_path / "list.json"
    list_file.write_text("[]", encoding="utf-8")

    collector = HomebrewUpdatesCollector(list_path=str(list_file))

    # Mock translate_short_description to return empty string (simulating LLM failure)
    async def mock_translate_fail(text, model=None):
        return ""

    monkeypatch.setattr("services.translation.translate_short_description", mock_translate_fail)

    desc = await collector._get_description_cached(
        cache_key="test:app1",
        local_entry=None,
        raw_text="Some long English description that failed to translate",
        fallback_name="SuperApp"
    )

    # Fallback should be used
    assert desc == "Додаток SuperApp."
    # Cache should NOT contain the entry
    assert "test:app1" not in collector._descriptions


@pytest.mark.asyncio
async def test_get_description_cached_rejects_latin_only_translation(monkeypatch, tmp_path):
    from collect_homebrew_updates import HomebrewUpdatesCollector

    list_file = tmp_path / "list.json"
    list_file.write_text("[]", encoding="utf-8")

    collector = HomebrewUpdatesCollector(list_path=str(list_file))

    # Mock translate_short_description to return English text (no Cyrillic)
    async def mock_translate_english(text, model=None):
        return "Still in English because model failed"

    monkeypatch.setattr("services.translation.translate_short_description", mock_translate_english)

    desc = await collector._get_description_cached(
        cache_key="test:app2",
        local_entry=None,
        raw_text="Still in English because model failed",
        fallback_name="AnotherApp"
    )

    assert desc == "Додаток AnotherApp."
    assert "test:app2" not in collector._descriptions


@pytest.mark.asyncio
async def test_translate_short_description_failure_returns_empty(monkeypatch):
    from services.translation import translate_short_description
    from services import gpt

    # Mock gpt.complete to return None
    async def mock_gpt_none(*args, **kwargs):
        return None

    monkeypatch.setattr(gpt, "complete", mock_gpt_none)

    res = await translate_short_description("Any text here that fails")
    assert res == ""

