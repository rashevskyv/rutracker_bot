# RuTracker Bot — Architecture Notes

## Project Structure

```
main.py                  — Main bot loop (feed → parse → post → digest)
send_daily_digest.py     — Daily digest sender (cron 08:00)
send_homebrew_digest.py  — Homebrew digest sender (cron 08:00)
send_homebrew_digest.py  — Homebrew digest sender (cron 08:00)
send_swuk_digest.py      — Switch UA localizations digest sender (cron 08:00)
collect_homebrew_updates.py — Multi-source homebrew collector (cron 07:00)
collect_swuk_updates.py  — swuk.com.ua RSS collector (cron 07:00)

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
  swuk.py                — Ukrainian Switch localizations digest

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
- Same URL + same type → **update** entry.
- Same URL + different type (new → updated) → **only keep the 'new' (added) entry** in the formatted digest if both occur in the same digest period, to prevent duplicates.
- **Timestamp Preservation**: Like the homebrew digest, it preserves the original discovery `timestamp` if the title and update status haven't changed.

### Homebrew digest (`digest/homebrew.py`)
- Key: `release_url`
- Same release URL → **update** entry.
- **Discovery Timestamp Preservation**: If the `version` and `app_name` are the same as existing, the original discovery `timestamp` is preserved. This prevents the entry from reappearing in the "last 24 hours" digest if it's re-added without changes.
- **Automatic Marker Clearing**: After a successful digest send, all entries included in that digest have their `is_new` flag set to `False`.

## Homebrew Collector — Multi-Source Architecture

`collect_homebrew_updates.py` runs in phases. Each phase returns a set of GitHub `owner/repo` slugs it covered. Phase 2 skips any entry whose slug was already handled.

```
Phase 1a: UDB API          — 3DS/DS(i)    https://udb-api.lightsage.dev/all        (GET)
Phase 1b: ForTheUsers      — Switch       https://switch.cdn.fortheusers.org/repo.json (GET)
Phase 1c: ForTheUsers      — WiiU         https://wiiu.cdn.fortheusers.org/repo.json   (GET)
Phase 1d: VitaDB           — PSVita       3 POST endpoints on rinnegatamante.eu
Phase 2:  GitHub/GitLab    — Everything else not covered above
```

### Description Cache (`data/hb_descriptions.json`)

Shared across all sources. Key format: `{prefix}:{id}`. Descriptions are translated **once** via GPT and cached permanently.

**Priority per entry:**
1. `list_hb.json` description (already Ukrainian) → used directly
2. `hb_descriptions.json` cache hit → used directly
3. API `long_description`/`description` → GPT translate → saved to cache

### Changelog Summarization

All sources: `_extract_latest_changelog()` extracts the top block, then GPT (`gpt-4o-mini`) summarizes to 1–2 Ukrainian sentences. Appended as `<i>...</i>` to the digest entry.

### State Files

| File | Source | Key format |
|------|--------|------------|
| `data/udb_state.json` | UDB API | `{slug}` |
| `data/fortheusers_state.json` | Switch/WiiU FTU | `switch-hb:{name}` / `wiiu-hb:{name}` |
| `data/vitadb_state.json` | VitaDB | `vita-hb:{id}` / `vita-plugin:{id}` / `vita-tool:{id}` |
| `data/hb_state.json` | GitHub/GitLab | `{api_url}` |
| `data/hb_descriptions.json` | Shared cache | `{prefix}:{id}` |

### First Run Behavior

All Phase 1 collectors: if an entry is **not** in state → save current version/date, **do not post**. Only subsequent runs with changed `version` or `updated`/`date` trigger a digest entry.

## Swuk Digest (Ukrainian Switch Localizations)

**Source:** `https://swuk.com.ua/feed/tg-updates/` — RSS 2.0, updates hourly.

**Key detection:** `<guid>` contains `?modified=YYYYMMDDHHMMSS`. `<pubDate>` does NOT change on updates — only `guid` does.

**State file:** `data/swuk_state.json` — `{url: {modified, title}}`

**Digest:** `digest/swuk.py` — separate from homebrew digest. Sent via `send_swuk_digest.py`.

**Config key** in `settings.json`: `SWUK_CHANNEL` with `enabled`, `chat_id`, `topic_id`.

## Timestamp Management

Timestamps are saved by **senders**, not collectors:
- `send_daily_digest.py` → `data/last_digest_run.json`
- `send_homebrew_digest.py` → `data/last_homebrew_digest_run.json`
- `send_swuk_digest.py` → `data/last_swuk_digest_run.json`

This ensures the digest window is between two successful **sends** (posts to Telegram), not between collections.

## URL Deduplication (main bot)

`data/posted_links.json` tracks all URLs posted by the main bot. Prevents re-posting entries that reappear in the feed with `[Обновлено]` tag. Auto-cleans entries older than 30 days.

## Message Splitting

`digest/base.py` auto-splits messages exceeding 4096 chars using `utils/telegram_utils.split_text()`. Preserves HTML formatting across splits.

## Known Edge Cases

- **HTML truncation in update_description**: `main.py` limits `update_description` to 200 chars with HTML-safe truncation (strips broken `<a>` tags).
- **None update_description**: Falls back to "добавлен апдейт" in `digest/daily.py` formatter.
- **Unclosed session warning**: May appear from `telebot` internal session — safe to ignore.

## Manual Releases

### Processing Limit
To prevent flooding channels with too many new releases at once when a bulk set of links is added, processing of new manual releases is limited to at most **5 unprocessed releases** per execution (which runs daily). The remaining releases are kept with `"processed": false` in `data/manual_releases.json` and are processed on subsequent runs.

### Skip Updates for Unprocessed Manual Releases
If a manual release for an app is pending (has `"processed": false` in `data/manual_releases.json`), the automated homebrew collectors (`collect_homebrew_updates.py`) will **skip** adding any updates for that app to the digest. Instead, they will only update their internal state files (`hb_state.json`, `udb_state.json`, etc.) with the new version. This prevents:
1. Posting update news for apps that have not yet been announced as new in the channel.
2. Posting duplicate update news after the manual release is processed (since state is updated beforehand).
Once the manual release's `"processed"` status becomes `true`, normal update tracking resumes.

