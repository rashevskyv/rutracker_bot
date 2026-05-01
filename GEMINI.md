# Project Overview

A Python-based Telegram bot that monitors RuTracker for new Nintendo Switch game torrents. It fetches updates from an RSS feed, parses tracker data, downloads metadata (cover images, YouTube trailers), translates descriptions to Ukrainian via GPT, and sends formatted notifications to multiple Telegram groups. Also collects homebrew application updates from GitHub/GitLab.

## Core Technologies

*   **Language:** Python 3.x (async/await)
*   **Key Libraries:**
    *   `aiohttp`: Shared async HTTP session for all network operations
    *   `beautifulsoup4`: HTML parsing of RuTracker pages
    *   `feedparser`: RSS/Atom feed parsing
    *   `pyTelegramBotAPI`: Telegram Bot API (async)
    *   `openai`: GPT translation (RU→UA), content validation, description summarization
    *   `google-api-python-client`: YouTube Data API v3 for trailer search

## Project Structure

```
rutracker_bot/
├── main.py                        # Entry point — RSS polling loop
├── send_daily_digest.py           # Cron script — send daily digest
├── send_homebrew_digest.py        # Cron script — send homebrew digest
├── collect_homebrew_updates.py    # Cron script — collect GitHub/GitLab updates
├── settings.json                  # Configuration (API keys via env vars)
├── requirements.txt               # Pinned dependencies
│
├── core/                          # Core: config, logging
│   ├── settings_loader.py         # Config loading, API client init, shared session
│   └── logger_setup.py            # Logging configuration
│
├── utils/                         # Utilities
│   ├── html_utils.py              # HTML sanitization for Telegram, tag normalization
│   └── telegram_utils.py          # Text splitting, media downloading
│
├── parsers/                       # Data parsing
│   ├── feed_handler.py            # RSS feed fetching and entry extraction
│   └── tracker_parser.py          # RuTracker page HTML parsing
│
├── services/                      # External service integrations
│   ├── telegram_sender.py         # Message composition and multi-group dispatch
│   ├── translation.py             # GPT-based RU→UA translation
│   ├── ai_validator.py            # GPT validation (YouTube titles, summarization)
│   ├── youtube_search.py          # YouTube trailer search (cached client)
│   └── titledb_manager.py         # Nintendo TitleDB metadata lookup
│
└── digest/                        # Digest system
    ├── base.py                    # BaseDigest — shared storage, sending, cleanup
    ├── daily.py                   # DailyDigest — RuTracker game entries
    └── homebrew.py                # HomebrewDigest — homebrew app updates
```

## Building and Running

**Prerequisites:**
*   Python 3.x
*   `pip` for installing dependencies

**Installation:**
```bash
pip install -r requirements.txt
```

**Configuration:**
1.  Create `settings.json` with API keys (use `os.environ['KEY']` placeholder for env vars)
2.  Set environment variables: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `YOUTUBE_API_KEY`

**Running:**
```bash
python main.py                        # Main bot loop
python send_daily_digest.py           # Send daily digest (cron)
python send_homebrew_digest.py        # Send homebrew digest (cron)
python collect_homebrew_updates.py    # Collect homebrew updates (cron)
```

## Key Design Patterns

*   **Shared aiohttp session** — single `ClientSession` via `get_session()` prevents TCP connection leaks
*   **Config-driven translation** — `language: "UA"` in settings.json triggers GPT translation
*   **Translation caching** — translated once per entry, reused for all UA groups
*   **BaseDigest inheritance** — DailyDigest and HomebrewDigest share storage/sending logic
*   **Deduplication** — `(chat_id, topic_id)` group key prevents double-posting
*   **Blockquote protection** — `XBQSX`/`XBQEX` tokens prevent GPT from mangling HTML tags
