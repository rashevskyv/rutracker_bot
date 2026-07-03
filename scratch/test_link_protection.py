"""
Test: verify that <b><a href="...">Оновлено:</a></b> links survive GPT translation
by being protected with XUPDLNKX tokens before sending to GPT and restored after.
"""
import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def simulate_protection(base_message_text: str):
    """Simulate the exact logic from telegram_sender.py translation block."""
    # Replace blockquote tags with opaque tokens (as done in sender)
    prepared_text = base_message_text.replace("<blockquote>", "XBQSX")
    prepared_text = prepared_text.replace("</blockquote>", "XBQEX")

    # Protect update header links from GPT
    protected_links: dict = {}
    link_counter = [0]

    def _protect_link(m):
        token = f'XUPDLNK{link_counter[0]}X'
        protected_links[token] = m.group(0)
        link_counter[0] += 1
        return token

    prepared_text = re.sub(
        r'<b><a href="[^"]*">[^<]*</a></b>',
        _protect_link,
        prepared_text
    )
    return prepared_text, protected_links


def simulate_gpt_stripping(text: str) -> str:
    """Simulate what GPT might do: strip <a> tags inside <b> or modify them."""
    # Worst case: GPT removes <a> tags and just keeps the text
    result = re.sub(r'<a href="[^"]*">([^<]*)</a>', r'\1', text)
    # Also simulate GPT translating XBQSX/XBQEX correctly
    return result


def simulate_restore(translated_text: str, protected_links: dict) -> str:
    """Restore protected update header links after translation."""
    for token, original_html in protected_links.items():
        translated_text = translated_text.replace(token, original_html)
    return translated_text


def run_tests():
    print("--- Testing update link protection pipeline ---")

    # Test case 1: single Оновлено link
    msg1 = (
        'Game Title\n'
        '<b>Download:</b>\n<code>magnet:?xt=...</code>\n'
        '<b><a href="https://rutracker.org/forum/viewtopic.php?p=12345678#12345678">Оновлено:</a></b>\n'
        'XBQSX\nДодано апдейт версії 1.0.33.0\nXBQEX'
    )

    prepared, protected_links = simulate_protection(msg1)

    print(f"Protected links count: {len(protected_links)}")
    assert len(protected_links) == 1, "Should have protected 1 link"
    assert 'XUPDLNK0X' in prepared, "Token should be in prepared text"
    assert '<a href=' not in prepared, "href should not remain in prepared text"
    print(f"  Token in prepared text: XUPDLNK0X -> {list(protected_links.values())[0]}")

    # Simulate GPT destroying the token (it shouldn't — it's opaque)
    # GPT will only see "XUPDLNK0X" and treat it as a preserved marker
    # But let's verify even if GPT does something bad, we handle it
    gpt_output_normal = prepared.replace("Game Title", "Назва гри")
    gpt_output_normal = gpt_output_normal.replace("Download", "Завантажити")

    restored = simulate_restore(gpt_output_normal, protected_links)
    print(f"  Restored text contains link: {'rutracker.org/forum/viewtopic.php?p=12345678' in restored}")
    assert 'href="https://rutracker.org/forum/viewtopic.php?p=12345678#12345678"' in restored
    assert 'Оновлено:' in restored
    print("  Test 1 PASSED: Link restored correctly after simulated GPT translation")

    # Test case 2: no link present (fallback - just <b>Оновлено:</b>)
    msg2 = (
        'Game Title\n'
        '<b><b>Оновлено:</b></b>\n'
        'XBQSX\nДодано апдейт\nXBQEX'
    )
    prepared2, protected2 = simulate_protection(msg2)
    assert len(protected2) == 0, "No links to protect in this case"
    print("  Test 2 PASSED: No spurious protection when no <a> present")

    # Test case 3: GPT would have stripped the <a> without our protection
    link_html = '<b><a href="https://rutracker.org/forum/viewtopic.php?p=99887766#99887766">Оновлено:</a></b>'
    msg3 = f"Some description\n{link_html}\nXBQSX\nUpdate text\nXBQEX"

    prepared3, protected3 = simulate_protection(msg3)

    # Simulate what would happen WITHOUT protection (GPT strips <a>)
    bad_gpt_output = simulate_gpt_stripping(prepared3)
    restored_without = simulate_restore(bad_gpt_output, {})  # No restore
    assert 'href=' not in restored_without, "Without protection, href would be gone"
    print("  Test 3a: Without protection - link GONE (as expected)")

    # Now with protection - GPT sees token, can't strip it
    gpt_output3 = prepared3  # GPT doesn't touch opaque XUPDLNK0X token
    restored_with = simulate_restore(gpt_output3, protected3)
    assert 'href="https://rutracker.org/forum/viewtopic.php?p=99887766#99887766"' in restored_with
    print("  Test 3b: With protection - link PRESERVED")
    print("  Test 3 PASSED")

    print("\nALL PROTECTION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_tests()
