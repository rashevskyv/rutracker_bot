import asyncio
import sys
import os
from curl_cffi.requests import AsyncSession as CurlSession
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import RUTRACKER_COOKIES, close_clients

async def main():
    url = "https://rutracker.org/forum/viewtopic.php?t=6038065"
    cookies = RUTRACKER_COOKIES or {}
    print("Using cookies:", cookies)
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://rutracker.org/forum/index.php'
    }
    
    async with CurlSession(impersonate="chrome110") as session:
        response = await session.get(url, headers=headers, cookies=cookies, timeout=90)
        print("Status code:", response.status_code)
        print("Headers:", response.headers)
        print("Response text:", response.text)

if __name__ == "__main__":
    asyncio.run(main())
