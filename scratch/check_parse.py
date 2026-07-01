import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import get_session, close_clients
from parsers.tracker_parser import parse_tracker_entry

async def main():
    url = "https://rutracker.org/forum/viewtopic.php?t=6038065"
    print(f"Parsing {url}...")
    try:
        res = await parse_tracker_entry(url, "TEST [Обновлено]")
        print("Parse successful!")
        print("Title:", res[0])
        print("Has update text:", res[8] is not None)
        if res[8]:
            print("Update text (first 200 chars):", res[8][:200])
    except Exception as e:
        print("Error during parsing:", e)
    finally:
        await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
