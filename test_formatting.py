import sys
import os

# Add the project directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from html_utils import convert_markdown_to_html, sanitize_html_for_telegram

def test_conversion():
    md_test_cases = [
        ("**Bold text**", "<b>Bold text</b>"),
        ("*Italic text*", "<i>Italic text</i>"),
        ("`Code block`", "<code>Code block</code>"),
        ("Mixed **bold** and *italic* with `code`.", "Mixed <b>bold</b> and <i>italic</i> with <code>code</code>."),
        ("No formatting here.", "No formatting here."),
        ("**Multiple** **bold** **parts**", "<b>Multiple</b> <b>bold</b> <b>parts</b>"),
        ("*Multiple* *italic* *parts*", "<i>Multiple</i> <i>italic</i> <i>parts</i>"),
        ("Nested *inner* is not handled but **bold** is.", "Nested <i>inner</i> is not handled but <b>bold</b> is."),
    ]

    for input_text, expected_output in md_test_cases:
        result = convert_markdown_to_html(input_text)
        print(f"MD Input:    {input_text}")
        print(f"MD Result:   {result}")
        assert result == expected_output
        print("--- MD PASSED ---")

    html_test_cases = [
        ("<ul><li>List item</li></ul>", "List item"),
        ("<b>Bold</b> <ul><li>Item</li></ul>", "<b>Bold</b> Item"),
        ("Some text <script>alert(1)</script>", "Some text"),
    ]

    for input_text, expected_output in html_test_cases:
        result = sanitize_html_for_telegram(input_text)
        print(f"HTML Input:  {input_text}")
        print(f"HTML Result: {result}")
        assert result == expected_output
        print("--- HTML PASSED ---")

if __name__ == "__main__":
    try:
        test_conversion()
        print("\nAll formatting and sanitization tests PASSED!")
    except AssertionError as e:
        print("\nFormatting test FAILED!")
        sys.exit(1)
