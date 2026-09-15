"""Unit tests for HTML cleaning and Telegram sanitization, covering nested DOM elements."""
import pytest
from utils.html_utils import clean_description_html, sanitize_html_for_telegram


def test_clean_description_nested_quotes():
    """Nested quote blocks should unwrap cleanly without raising ValueError."""
    html_input = """
    <div class="q-wrap">
        <div class="q-head">User 1 wrote:</div>
        <div class="q">
            Outer quote text
            <div class="q-wrap">
                <div class="q-head">User 2 wrote:</div>
                <div class="q">Inner quote text</div>
            </div>
        </div>
    </div>
    """
    result = clean_description_html(html_input)
    assert "User 1:" in result
    assert "Outer quote text" in result
    assert "Inner quote text" in result


def test_clean_description_decomposed_outer_spoiler_with_inner():
    """Inner spoilers inside decomposed outer spoilers (e.g. 'Скриншоты') should not crash."""
    html_input = """
    <div class="sp-wrap">
        <div class="sp-head">Скриншоты игры</div>
        <div class="sp-body">
            Outer text
            <div class="sp-wrap">
                <div class="sp-head">Inner Spoiler</div>
                <div class="sp-body">Inner text</div>
            </div>
        </div>
    </div>
    """
    result = clean_description_html(html_input)
    assert "Скриншоты" not in result
    assert "Inner text" not in result


def test_clean_description_decomposed_outer_spoiler_with_quotes_and_code():
    """Inner quotes and code blocks inside decomposed outer spoilers should not crash."""
    html_input = """
    <div class="sp-wrap">
        <div class="sp-head">Скриншоты</div>
        <div class="sp-body">
            <div class="q-wrap">
                <div class="q-head">Author:</div>
                <div class="q">Some quote</div>
            </div>
            <div class="c-wrap">
                <div class="c-head">Код</div>
                <div class="c-body">print("hello")</div>
            </div>
        </div>
    </div>
    """
    result = clean_description_html(html_input)
    assert "print(\"hello\")" not in result


def test_clean_description_nested_spoilers_retained():
    """Valid nested spoilers should both be formatted as blockquotes."""
    html_input = """
    <div class="sp-wrap">
        <div class="sp-head">Outer Spoiler</div>
        <div class="sp-body">
            Outer body content
            <div class="sp-wrap">
                <div class="sp-head">Inner Spoiler</div>
                <div class="sp-body">Inner body content</div>
            </div>
        </div>
    </div>
    """
    result = clean_description_html(html_input)
    assert "<b>Outer Spoiler:</b>" in result
    assert "Outer body content" in result
    assert "<b>Inner Spoiler:</b>" in result
    assert "Inner body content" in result


def test_clean_description_quotes_with_code_and_lists():
    """Quotes containing code blocks, linebreaks, and lists should parse safely."""
    html_input = """
    <div class="q-wrap">
        <div class="q-head">Moderator wrote:</div>
        <div class="q">
            Note the following:
            <div class="c-wrap">
                <div class="c-head">Код</div>
                <div class="c-body">CFW 18.0.0</div>
            </div>
            <hr>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
    </div>
    """
    result = clean_description_html(html_input)
    assert "<b>Moderator:</b>" in result
    assert "CFW 18.0.0" in result
    assert "• Item 1" in result
    assert "• Item 2" in result


def test_sanitize_html_for_telegram_detached_elements():
    """Sanitizer should handle deeply nested tags and unwrapping without tree errors."""
    raw_html = "<span><span><span><b>Text in nested spans</b></span></span></span><div><p>Paragraph</p></div>"
    sanitized = sanitize_html_for_telegram(raw_html)
    assert "<b>Text in nested spans</b>" in sanitized
    assert "Paragraph" in sanitized
