import sys
import os
import re

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.telegram_utils import split_text
from utils.html_utils import sanitize_html_for_telegram

def test_lone_headers():
    print("--- Running split_text lone header backtracking tests ---")
    
    # Test case 1: Standard <b>Header:</b> at split boundary
    text1 = "Some initial text that fills up the first part to near the limit." + " " * 80 + "\n<b>Озвучка:</b>\nРосійська, Англійська"
    # Let's set max_length to 100 to trigger a split on or near the bold header
    parts1 = split_text(text1, 100)
    print("Parts for test 1 (standard):")
    for idx, part in enumerate(parts1):
        print(f"Part {idx+1}:\n{part}\n{'-'*30}")
    
    # We want <b>Озвучка:</b> to be pushed to the second part so it stays with "Російська, Англійська"
    assert "<b>Озвучка:</b>" not in parts1[0], "Test 1 failed: Header left in part 1"
    assert "<b>Озвучка:</b>" in parts1[1], "Test 1 failed: Header not moved to part 2"
    
    # Test case 2: Bold header with link <b><a href="...">Header:</a></b>
    text2 = "Some initial text that fills up the first part to near the limit." + " " * 80 + "\n<b><a href=\"https://rutracker.org\">Оновлено:</a></b>\n<blockquote>Новий апдейт 1.0.3</blockquote>"
    parts2 = split_text(text2, 110)
    print("Parts for test 2 (bold link):")
    for idx, part in enumerate(parts2):
        print(f"Part {idx+1}:\n{part}\n{'-'*30}")
        
    assert "Оновлено:" not in parts2[0], "Test 2 failed: Bold link header left in part 1"
    assert "Оновлено:" in parts2[1], "Test 2 failed: Bold link header not moved to part 2"
    
    # Test case 3: Colon outside bold <b>Header</b>:
    text3 = "Some initial text that fills up the first part to near the limit." + " " * 80 + "\n<b>Жанр</b>:\nRPG, Action"
    parts3 = split_text(text3, 100)
    print("Parts for test 3 (colon outside):")
    for idx, part in enumerate(parts3):
        print(f"Part {idx+1}:\n{part}\n{'-'*30}")
        
    assert "<b>Жанр</b>:" not in parts3[0], "Test 3 failed: Colon outside header left in part 1"
    assert "<b>Жанр</b>:" in parts3[1], "Test 3 failed: Colon outside header not moved to part 2"

    print("ALL BACKTRACKING TESTS PASSED SUCCESSFULLY!")

def test_sanitize_html():
    print("--- Running sanitize_html_for_telegram tests ---")
    
    # Test case 1: Multiple bold parameter headers on the same line should be split into new lines
    raw_html = "<b>Платформа:</b> Nintendo Switch <b>Жанр:</b> RPG <b>Мова:</b> Англійська"
    sanitized = sanitize_html_for_telegram(raw_html)
    print("Sanitized inline headers:")
    print(repr(sanitized))
    
    assert "\n<b>Жанр:</b>" in sanitized, "Failed to split <b>Жанр:</b> onto a new line"
    assert "\n<b>Мова:</b>" in sanitized, "Failed to split <b>Мова:</b> onto a new line"
    
    # Test case 2: Pattern 2 (colon outside tag)
    raw_html2 = "<b>Платформа</b>: Switch <b>Жанр</b>: Adventure"
    sanitized2 = sanitize_html_for_telegram(raw_html2)
    print("Sanitized colon outside inline headers:")
    print(repr(sanitized2))
    assert "\n<b>Жанр</b>:" in sanitized2, "Failed to split colon-outside header onto a new line"

    # Test case 3: Safety restoration of href URL colons
    raw_html3 = '<a href="https://rutracker.org/forum/viewtopic.php?t=6113658">Оновлено:</a>'
    sanitized3 = sanitize_html_for_telegram(raw_html3)
    print("Sanitized href:")
    print(repr(sanitized3))
    assert 'href="https://rutracker.org/forum/viewtopic.php?t=6113658"' in sanitized3, "Href URL colon restoration failed"
    
    print("ALL SANITIZATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_lone_headers()
    test_sanitize_html()
