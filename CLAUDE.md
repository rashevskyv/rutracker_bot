# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RuTracker Bot is an automated Telegram bot that monitors the RuTracker torrent tracker (specifically the Nintendo Switch section) for new game releases and updates. It fetches RSS feeds, parses torrent pages, enriches posts with YouTube trailers and game screenshots, translates content to Ukrainian, and publishes formatted messages to multiple Telegram channels. The bot also generates daily digest summaries.

## Core Architecture

### Main Processing Flow (main.py)

The bot operates in a single-pass loop:
1. **Feed Fetching** (`feed_handler.py`) - Retrieves new entries from RuTracker RSS feed
2. **Page Parsing** (`tracker_parser.py`) - Extracts game metadata, descriptions, magnet links, and update information from HTML
3. **Content Enrichment** - Searches YouTube for trailers, validates relevance with GPT, fetches game screenshots from TitleDB
4. **Translation** (`translation.py`) - Translates Russian content to Ukrainian using GPT-4o-mini
5. **Telegram Delivery** (`telegram_sender.py`) - Sends formatted messages with media to configured channels
6. **Digest Collection** (`daily_digest.py`) - Tracks entries for daily summary posts

### Key Modules

**tracker_parser.py** - HTML parsing logic for RuTracker pages
- `parse_tracker_entry()` - Main parser extracting title, description, images, magnet links, size, language
- `get_last_post_with_phrase()` - Searches recent forum posts for update announcements (e.g., "Раздача обновлена")
- Uses BeautifulSoup for HTML parsing with careful handling of nested structures

**telegram_sender.py** - Message formatting and delivery
- Two sending strategies based on media count:
  - **Strategy 1 (< 6 media items)**: Sends cover/thumbnail separately, then text, then screenshots
  - **Strategy 2 (≥ 6 media items)**: Bundles all media into a single media group with caption
- Handles Telegram's caption length limits (1024 chars) and message length limits (4096 chars)
- Splits long messages intelligently while preserving HTML structure
- Special handling for `###GAP###` markers to control paragraph spacing

**translation.py** - Russian to Ukrainian translation
- Primary method: GPT-4o-mini with detailed prompt for natural, readable Ukrainian
- Uses special tokens `XBQSX`/`XBQEX` to protect `<blockquote>` tags from GPT manipulation
- Enforces specific terminology (e.g., "російська" not "руська" for Russian language)
- Preserves HTML structure, links, and technical parameters

**ai_validator.py** - AI-powered content validation
- `validate_yt_title_with_gpt()` - Verifies YouTube search results match the game title
- `summarize_description_with_ai()` - Condenses descriptions exceeding 5000 chars while preserving key information

**daily_digest.py** - Daily summary system
- Collects entries throughout the day in `daily_digest_data.json`
- Formats digest with separate sections for new releases and updates
- Designed to run on a schedule (e.g., 9:00 AM daily)

**settings_loader.py** - Configuration management
- Loads `settings.json` with API keys, channel configurations, and feature flags
- Initializes shared aiohttp session and Telegram bot client
- Supports environment variable substitution (e.g., `"os.environ['TELEGRAM_BOT_TOKEN']"`)

**html_utils.py** - HTML sanitization and formatting
- `sanitize_html_for_telegram()` - Strips unsupported HTML tags, keeps only Telegram-allowed tags
- `clean_description_html()` - Removes unwanted elements (spoilers, quotes, images) from descriptions
- `convert_markdown_to_html()` - Converts `###GAP###` markers to proper line breaks

**titledb_manager.py** - Nintendo game database integration
- Searches local TitleDB JSON files (US.en.json, JP.ja.json, GB.en.json) for game metadata
- Downloads official Nintendo eShop screenshots for games
- Fuzzy matching to handle title variations

## Running the Bot

### Production Mode
```bash
python main.py
```

### Test Mode
Set `"test": true` in `settings.json` and specify a test URL in `"test_last_entry_link"`. This processes a single entry without updating the last-processed-link file.

### Daily Digest
```bash
python send_daily_digest.py
```
Sends accumulated entries from the past 24 hours to the configured digest channel.

## Configuration

**settings.json** structure:
- `TELEGRAM_BOT_TOKEN` - Bot API token
- `OPENAI_API` - OpenAI API key for GPT-4o-mini (translation, validation, summarization)
- `YOUTUBE_API_KEY` - YouTube Data API v3 key
- `DEEPL_API_KEY` - DeepL API key (fallback, currently unused)
- `FEED_URL` - RuTracker RSS feed URL
- `GROUPS` - Array of target Telegram channels with chat_id, topic_id, language (RU/UA)
- `DIGEST_CHANNEL` - Configuration for daily digest posts
- `test` - Boolean flag for test mode
- `LOG` - Enable/disable verbose logging

API keys can reference environment variables using the pattern: `"os.environ['VAR_NAME']"`

## Important Patterns

### HTML Tag Protection During Translation
When translating to Ukrainian, `<blockquote>` tags are replaced with opaque tokens (`XBQSX`/`XBQEX`) before sending to GPT. This prevents the model from splitting or duplicating quote blocks. After translation, tokens are restored to proper HTML tags.

### Message Splitting with ###GAP###
The `###GAP###` marker is used throughout the codebase to indicate intentional paragraph breaks that should be preserved during text splitting and translation. The `split_text()` function in `telegram_utils.py` converts these to actual newlines while respecting Telegram's length limits.

### Update Detection
The bot detects updates by checking for `[Обновлено]` or `[Updated]` in feed entry titles. When found, it searches the last 5 pages of the forum thread for posts containing "Раздача обновлена" or "Distribution updated" and extracts the update description.

### Media Strategy Selection
The bot automatically chooses between two sending strategies based on total media count (cover + thumbnail + screenshots). With ≥6 items, it uses media groups for better visual presentation. With <6 items, it sends media separately to avoid cluttered groups.

### Async/Await Patterns
The codebase is fully async. External API calls (HTTP requests, OpenAI, Telegram) use `await`. Synchronous operations (file I/O, JSON parsing) are wrapped with `asyncio.to_thread()` when called from async contexts.

## Testing Files

The repository contains numerous test files (test_*.py) for debugging specific components:
- `test_citation.py`, `test_quote.py` - HTML parsing edge cases
- `test_hades*.py` - Specific game parsing scenarios
- `test_telegram_sender.py` - Message formatting validation
- `test_formatting.py` - Translation and formatting tests

These are development artifacts and not part of the production flow.

## Dependencies

Key Python packages:
- `aiohttp` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `feedparser` - RSS/Atom feed parsing
- `pyTelegramBotAPI` (telebot) - Telegram Bot API wrapper
- `openai` - OpenAI API client (async)
- `google-cloud-translate` - Google Translate API (fallback, currently unused)

## Logging

The bot uses Python's `logging` module. Logger setup is in `logger_setup.py`. Logs include:
- Feed parsing status
- Page fetch attempts and retries
- Translation operations
- Telegram send operations
- Errors with stack traces

A per-cycle log file (`log_tg_send.txt`) captures all formatted messages sent during each run for debugging.

## Error Handling

Errors are sent to admin channels configured in `ERROR_TG` (part of settings). The `send_error_to_telegram()` function formats errors with HTML escaping and includes entry URLs for context.

## State Management

- `last_entry_link.txt` - Tracks the most recently processed feed entry to avoid duplicates
- `daily_digest_data.json` - Accumulates entries for daily digest
- `last_digest_run.json` - Tracks last digest send time
- `tmp_screenshots/` - Temporary storage for downloaded game screenshots (cleaned after send)

## Git Workflow

The project uses conventional commit messages with version tags:
- `Feature(v0.5.x):` - New features
- `Fix(v0.5.x):` - Bug fixes

When committing, follow this pattern and increment the version number appropriately.
