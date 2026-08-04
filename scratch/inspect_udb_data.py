import asyncio
import aiohttp
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collect_homebrew_updates import UDB_API_URL


async def inspect():
    url = UDB_API_URL
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if isinstance(data, list) and data:
                item = data[0]
                print(f"All keys: {list(item.keys())}")
                print(f"slug: {item.get('slug')}")
                print(f"uniq: {item.get('uniq')}")
                print(f"title: {item.get('title')}")
                print(f"systems: {item.get('systems')}")
                print(f"updated: {item.get('updated')}")
                print(f"version: {item.get('version')}")

if __name__ == "__main__":
    asyncio.run(inspect())
