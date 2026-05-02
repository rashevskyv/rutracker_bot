# RuTracker Bot — Architecture Notes

## Project Structure

```
main.py                  — Main bot loop (feed → parse → post → digest)
send_daily_digest.py     — Daily digest sender (cron 08:00)
send_homebrew_digest.py  — Homebrew digest sender (cron 08:00)
collect_homebrew_updates.py — Homebrew GitHub/GitLab collector (cron 07:00)

core/
  settings_loader.py     — Settings, session, bot init

parsers/
  feed_handler.py        — RSS/Atom feed parsing, last_entry tracking
  tracker_parser.py      — RuTracker page parsing, update extraction

services/
  telegram_sender.py     — Telegram message sending
  ai_validator.py        — GPT title validation
  youtube_search.py      — YouTube trailer search
  titledb_manager.py     — TitleDB screenshot lookup
  translation.py         — RU→UA translation via GPT

digest/
  base.py                — Base digest class (load/save/split/send)
  daily.py               — Daily game digest (dedup by URL+type)
  homebrew.py            — Homebrew digest (dedup by release_url)

utils/
  html_utils.py          — HTML cleaning/sanitization
  telegram_utils.py      — Message splitting for Telegram 4096 limit

config/                  — Settings files (gitignored)
data/                    — Runtime data: digest JSON, timestamps, posted_links
```

## Update Extraction Strategy Chain

When the bot detects an `[Обновлено]` entry in the feed, it runs a **strategy chain** to extract the update description from the RuTracker topic page.

**Location:** `parsers/tracker_parser.py` → `parse_tracker_entry()` → `update_strategies` list

Each strategy is an async function with signature:
```python
async def _strategy_name(soup: BeautifulSoup, base_url: str) -> Optional[str]
```

Returns a formatted HTML string (e.g. `<b>Обновлено:</b> <a href="...">Details</a>\ntext`) or `None`.

### Current strategies (tried in order):

1. **`_strategy_phrase_search`** — Searches topic pages (from last to first) for posts containing "Раздача обновлена" / "Distribution updated". Extracts text after the phrase. Works for most standard RuTracker topics.

2. **`_strategy_author_update_post`** — Fallback: searches first page for "Обновлено до" pattern in author's posts. Takes the last (most recent) match. Works for topics like EA Sports FC where updates are in a separate changelog-style post by the author.

### Adding a new strategy:

1. Create an async function in `parsers/tracker_parser.py`:
```python
async def _strategy_my_new_format(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Strategy N: description of what format this handles."""
    # Parse the page, find update text
    # Return formatted HTML or None
    return None
```

2. Add it to the `update_strategies` list in `parse_tracker_entry()`:
```python
update_strategies = [
    lambda s, u: _strategy_phrase_search(s, u),
    lambda s, u: _strategy_author_update_post(s, u),
    lambda s, u: _strategy_my_new_format(s, u),  # NEW
]
```

Strategies are tried in order. First non-None result wins.

## Digest Deduplication

### Daily digest (`digest/daily.py`)
- Key: `url` + `is_updated` flag
- Same URL + same type → **replace** (keep latest version)
- Same URL + different type (new → updated) → **keep both**

### Homebrew digest (`digest/homebrew.py`)
- Key: `release_url`
- Same release URL → **replace** with latest version info

## Timestamp Management

Timestamps are saved by **senders**, not collectors:
- `send_daily_digest.py` → `data/last_digest_run.json`
- `send_homebrew_digest.py` → `data/last_homebrew_digest_run.json`

This ensures the digest window is between two successful **sends** (posts to Telegram), not between collections.

## URL Deduplication (main bot)

`data/posted_links.json` tracks all URLs posted by the main bot. Prevents re-posting entries that reappear in the feed with `[Обновлено]` tag. Auto-cleans entries older than 30 days.

## Message Splitting

`digest/base.py` auto-splits messages exceeding 4096 chars using `utils/telegram_utils.split_text()`. Preserves HTML formatting across splits.

## Known Edge Cases

- **HTML truncation in update_description**: `main.py` limits `update_description` to 200 chars with HTML-safe truncation (strips broken `<a>` tags).
- **None update_description**: Falls back to "добавлен апдейт" in `digest/daily.py` formatter.
- **Unclosed session warning**: May appear from `telebot` internal session — safe to ignore.
