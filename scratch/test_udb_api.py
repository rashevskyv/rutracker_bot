import asyncio
import aiohttp
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collect_homebrew_updates import UDB_API_URL


async def test_udb():
    url = UDB_API_URL
    print(f"Fetching {url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                print(f"Status code: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Success! Fetched {len(data)} items.")
                else:
                    print(f"API Error. Body: {await resp.text()}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_udb())
