import feedparser
import os
import time
import aiohttp
import asyncio
from settings_loader import LOG 
from typing import Optional, List # Import Optional, List

def read_last_entry_link(file_path: str) -> Optional[str]:
    """Reads the last processed entry link from the specified file."""
    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                link = f.read().strip()
                if LOG: print(f"Read last entry link: {link}")
                # Basic validation: check if it looks like a URL
                if link and link.startswith(('http://', 'https://')):
                     return link
                elif link:
                     print(f"Warning: Content of last entry file ('{link}') doesn't look like a valid URL.")
                     return None # Treat invalid content as no link found
                else:
                     return None # Empty file
        except Exception as e:
            print(f"Error reading last entry file {file_path}: {e}")
            return None
    else:
        if LOG: print(f"Last entry file not found: {file_path}")
        return None

def write_last_entry_link(file_path: str, link: str):
    """Writes the latest processed entry link to the specified file."""
    try:
        # Basic validation before writing
        if not link or not link.startswith(('http://', 'https://')):
             print(f"Error: Attempted to write invalid link to last entry file: {link}")
             return

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(link)
            if LOG: print(f"Written last entry link: {link}")
    except Exception as e:
        print(f"Error writing last entry file {file_path}: {e}")

async def get_new_feed_entries(feed_url: str, last_entry_link: Optional[str], retries: int = 3, delay: int = 5) -> Optional[List[feedparser.FeedParserDict]]:
    print(f"Parsing feed from: {feed_url}")
    feed = None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 RutrackerBot/1.0'
    }
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(feed_url, timeout=25) as response:
                    response.raise_for_status()
                    xml_content = await response.text()
                    feed = feedparser.parse(xml_content)

            if feed.bozo:
                 bozo_exception = feed.get('bozo_exception', 'Unknown parsing error')
                 if isinstance(bozo_exception, (feedparser.CharacterEncodingOverride, feedparser.NonXMLContentType)):
                      print(f"Feed Info: Parser issue ({type(bozo_exception).__name__}), but attempting to proceed.")
                 else:
                      print(f"Warning: Feed may be ill-formed. Error: {bozo_exception}")

            if feed.entries:
                print(f"Feed parsed successfully. Found {len(feed.entries)} entries.")
                break 
            else:
                 print(f"Feed parsed but contains no entries (Attempt {attempt + 1}/{retries}).")
                 if attempt == retries -1:
                      return []

        except aiohttp.ClientResponseError as e:
            print(f"HTTP Error fetching feed {feed_url}: {e.status}")
            if e.status >= 500 and attempt < retries - 1:
                await asyncio.sleep(delay)
                continue
            return None
        except Exception as e:
            print(f"Error parsing feed URL {feed_url} (Attempt {attempt + 1}/{retries}): {e}")

        if attempt < retries - 1:
            print(f"Retrying feed parsing in {delay} seconds...")
            await asyncio.sleep(delay)
        else:
            print(f"Failed to parse feed after {retries} attempts.")
            return None 

    if not feed or not feed.entries:
        return []

    valid_entries = [entry for entry in feed.entries if hasattr(entry, 'link') and entry.link]
    if len(valid_entries) != len(feed.entries):
        print(f"Warning: Filtered out {len(feed.entries) - len(valid_entries)} entries missing a link.")

    last_index = -1
    if last_entry_link:
        for i, entry in enumerate(valid_entries):
            if entry.link == last_entry_link:
                last_index = i
                break

    new_entries: List[feedparser.FeedParserDict] = []
    if last_entry_link is None:
        print("No last entry link found. Processing only the latest entry from the feed.")
        if valid_entries:
             new_entries = [valid_entries[0]] 
    elif last_index == -1:
        print(f"Warning: Last known entry link '{last_entry_link}' not found in the current feed. Processing all entries as new.")
        new_entries = valid_entries[:] 
    elif last_index == 0:
        print("No new entries found since the last check (last known link is the newest in feed).")
        new_entries = []
    else:
        new_entries = valid_entries[:last_index]
        print(f"Found {len(new_entries)} new entries.")

    return new_entries[::-1]
