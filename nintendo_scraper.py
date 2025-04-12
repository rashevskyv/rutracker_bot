# --- START OF FILE nintendo_scraper.py ---

import requests
from bs4 import BeautifulSoup, Tag
import re
import json # Might be needed if we find JSON data
import time # Added for sleep
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus # For URL encoding search query
import html

# --- Configuration ---
ESHOP_URLS = {
    "EU": "https://www.nintendo.co.uk/Search/Search-809390.html?q={query}&f=147394-16-88-409", # Added more filters? Check if needed
    "US_SEARCH": "https://www.nintendo.com/us/search/#q={query}&p=1&cat=gme&sort=df",
    "JP": "https://store-jp.nintendo.com/list/software/search.html?q={query}"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 NintendoScraperBot/1.0',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8', # More headers
    'Connection': 'keep-alive',
    'DNT': '1', # Do Not Track
    'Upgrade-Insecure-Requests': '1',
}

# --- Helper Functions ---

def fetch_html(url: str, retries: int = 3, delay: int = 2) -> Optional[BeautifulSoup]:
    """Fetches and parses HTML content from a URL with retries."""
    print(f"Fetching URL: {url}")
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            if 'html' not in content_type and 'json' not in content_type:
                 print(f"Warning: Unexpected Content-Type '{content_type}' for {url}")

            # Use response.text to let requests handle encoding, pass to BS4
            soup = BeautifulSoup(response.text, "html.parser")
            print(f"Successfully fetched content from {url}")
            return soup
        except requests.exceptions.Timeout: print(f"Timeout fetching {url} (Attempt {attempt + 1}/{retries})")
        except requests.exceptions.HTTPError as e:
             print(f"HTTP Error fetching {url}: {e.response.status_code}")
             if e.response.status_code in [404, 403]: return None # Stop on 404 or 403
             if 400 <= e.response.status_code < 500: return None # Stop on other client errors
        except requests.exceptions.RequestException as e: print(f"Network error fetching {url}: {e}")
        except Exception as e: print(f"Unexpected error fetching {url}: {e}"); return None

        if attempt < retries - 1: print(f"Retrying in {delay} seconds..."); time.sleep(delay)
        else: print(f"Failed to fetch {url} after {retries} attempts."); return None

def parse_eshop_page_for_screenshots(soup: BeautifulSoup, region: str) -> List[str]:
    """Parses the specific game page soup object to find screenshot URLs."""
    screenshots = set() # Use a set to avoid duplicates initially
    print(f"Parsing game page for screenshots (Region: {region})...")

    # --- Region-Specific Selectors (NEEDS INSPECTION/ADJUSTMENT) ---
    selectors = []
    if region == "EU":
        # Prioritize high-res links if available, then images
        selectors = [
            'a.pdp-image-gallery__link[href]', # Links often have higher res
            'div.product-gallery img[src]',
            'li.pdp-image-gallery__item img[src]',
            'img.pdp-main-stage-image__image[src]' # Main image?
        ]
    elif region == "US":
        # US uses picture tags often, prioritize source srcset
        selectors = [
            'div[class^="Gallerystyles__"] picture source[srcset]', # Highest priority
            'div[class^="Gallerystyles__"] picture img[src]', # Fallback img in picture
            'div[class^="Gallerystyles__"] img[src]', # Direct img if no picture tag
            'img[class^="ProductImage"]' # Another possible class for main image
        ]
    elif region == "JP":
        selectors = [
            'a.c-gallery-modal__link[href]', # Links first
            'li.o-slider__item img[srcset]', # srcset for higher res
            'li.o-slider__item img[src]', # fallback src
            'div.p-product-visual__main img[src]' # Main visual area
        ]

    for selector in selectors:
        elements = soup.select(selector)
        for element in elements:
            url = None
            # Extract URL based on tag/attribute
            if element.name == 'a' and element.has_attr('href'):
                url = element['href']
            elif element.name == 'img' and element.has_attr('src'):
                url = element.get('data-src') or element['src'] # Prioritize data-src
            elif element.name == 'img' and element.has_attr('srcset'): # Handle srcset on img directly too
                 urls = [s.strip().split(' ')[0] for s in element['srcset'].split(',')]
                 if urls: url = urls[-1] # Take last/highest res
            elif element.name == 'source' and element.has_attr('srcset'):
                 urls = [s.strip().split(' ')[0] for s in element['srcset'].split(',')]
                 if urls: url = urls[-1]

            # Validate and clean URL
            if url:
                url = url.strip()
                if url.startswith('//'): url = 'https:' + url
                # Check if it's a valid image URL and not a placeholder/tiny icon
                if url.startswith('http') and url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    if 'data:image' not in url and 'placeholder' not in url.lower(): # Basic filter
                        screenshots.add(url)

    # Convert set to list and limit
    unique_screenshots = sorted(list(screenshots))
    print(f"Found {len(unique_screenshots)} unique screenshot URLs for {region}.")
    return unique_screenshots[:10] # Limit to first 10 screenshots

# --- Main Scraping Function ---

def get_nintendo_screenshots(game_title_from_parser: str) -> Optional[List[str]]:
    """
    Tries to find screenshots for a given game title across EU, US, JP eShop regions.
    Uses the pre-cleaned title provided by the main parser.

    Args:
        game_title_from_parser: The cleaned game title (e.g., used for YT search).

    Returns:
        A list of screenshot URLs, or None if not found.
    """
    if not game_title_from_parser:
        print("Error: No game title provided to scraper.")
        return None

    # The title is already cleaned by the main parser logic
    cleaned_title = game_title_from_parser
    print(f"Searching eShops for: '{cleaned_title}'")

    # Iterate through regions
    for region in ["EU", "US", "JP"]:
        print(f"\n--- Checking Region: {region} ---")
        search_query_encoded = quote_plus(cleaned_title) # URL-encode the title
        game_page_soup = None
        search_url = None

        # --- Construct Search URL and Find Game Page ---
        if region == "EU":
            search_url = ESHOP_URLS["EU"].format(query=search_query_encoded)
            search_soup = fetch_html(search_url)
            if search_soup:
                # EU Search Results: Find first game link (adjust selector if needed)
                link = search_soup.select_one('div.search-result-item a.search-result-item__link[href*="/Games/"]')
                if link and link.has_attr('href'):
                     page_url = link['href']
                     if not page_url.startswith('http'): page_url = 'https://www.nintendo.co.uk' + page_url
                     print(f"Found potential game page link (EU): {page_url}")
                     game_page_soup = fetch_html(page_url)
                else: print("No suitable game link found on EU search results.")

        elif region == "US":
            # US Search Results can be tricky due to JS rendering, but try selectors
            search_url = ESHOP_URLS["US_SEARCH"].format(query=search_query_encoded)
            # Note: US Search page heavily relies on JS. Requests might not see results.
            # A more robust US approach might involve specific API endpoints if discoverable,
            # or using Selenium/Playwright (which adds complexity).
            # Let's try fetching and seeing if *any* static links exist.
            search_soup = fetch_html(search_url) # This might fetch the #q= URL
            if search_soup:
                 # This selector might only work if search results render without JS, which is unlikely
                 link = search_soup.select_one('a[class^="ProductCard_link"]')
                 if link and link.has_attr('href'):
                      page_url = link['href']
                      if not page_url.startswith('http'): page_url = 'https://www.nintendo.com' + page_url
                      print(f"Found potential game page link (US): {page_url}")
                      game_page_soup = fetch_html(page_url)
                 else:
                      print("No static game link found on US search page (JS likely required). Trying direct guess (less reliable)...")
                      # Fallback: Guess direct slug (very unreliable)
                      slug = cleaned_title.lower().replace(':', '').replace(' ', '-')
                      guessed_url = f"https://www.nintendo.com/us/store/products/{slug}-switch/"
                      print(f"Trying guessed URL (US): {guessed_url}")
                      game_page_soup = fetch_html(guessed_url)


        elif region == "JP":
            search_url = ESHOP_URLS["JP"].format(query=search_query_encoded)
            search_soup = fetch_html(search_url)
            if search_soup:
                 # JP Search Results: Find first game link (adjust selector if needed)
                 link = search_soup.select_one('a.product-list__item__link')
                 if link and link.has_attr('href'):
                      page_url = link['href']
                      if not page_url.startswith('http'): page_url = 'https://store-jp.nintendo.com' + page_url
                      print(f"Found potential game page link (JP): {page_url}")
                      game_page_soup = fetch_html(page_url)
                 else: print("No suitable game link found on JP search results.")


        # --- Parse Screenshots if Game Page Found ---
        if game_page_soup:
            screenshots = parse_eshop_page_for_screenshots(game_page_soup, region)
            if screenshots:
                print(f"Success: Found {len(screenshots)} screenshots in region {region}.")
                return screenshots # Return screenshots from the first successful region
        else:
             print(f"Could not find or fetch game page for region {region}.")


    # If loop finishes without finding screenshots
    print(f"Could not find any screenshots for '{cleaned_title}' after checking all regions.")
    return None

# --- Testing Block ---
if __name__ == "__main__":
    # --- Test Cases ---
    test_titles = [
        "The Legend of Zelda: Tears of the Kingdom",
        "Circuit Superstars",
         "eBaseball Professional Baseball Spirits 2021: Grand Slam", # JP Title
         "Mario Kart 8 Deluxe",
         "Hades",
         "NonExistentGame 12345", # Test case for not found
         "PAC-MAN 99" # Example from earlier discussion
    ]

    for title in test_titles:
        print(f"\n{'='*10} Testing Title: {title} {'='*10}")
        screenshots = get_nintendo_screenshots(title)
        if screenshots:
            print(f"\nScreenshots Found for '{title}':")
            for i, url in enumerate(screenshots):
                print(f"  {i+1}: {url}")
        else:
            print(f"\nNo screenshots found for '{title}'.")
        print(f"{'='*30}\n")
        time.sleep(2) # Add a small delay between tests

# --- END OF FILE nintendo_scraper.py ---