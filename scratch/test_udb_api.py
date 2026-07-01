import asyncio
import aiohttp
import sys

async def test_udb():
    url = 'https://udb-api.lightsage.dev/all'
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
