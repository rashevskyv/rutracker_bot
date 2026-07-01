import asyncio
import aiohttp

async def inspect():
    url = 'https://udb-api.lightsage.dev/all'
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
