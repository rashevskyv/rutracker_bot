# RuTracker Bot

A Telegram bot designed to fetch, parse, translate, and post updates from RuTracker, collect multi-source homebrew software updates, track Ukrainian Switch localizations, and send daily digests to configured Telegram channels.

## Core Architecture

The bot runs on a hybrid scheduling model using GitHub Actions and self-managing python scripts with state synchronization stored in a GitHub Gist.

```
                  GitHub Actions (Scheduler, every 15 min)
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   Main Feed Bot           Updates Collectors         Digest Senders
 (hourly, main.py)      (08:00 Kyiv, 05:00 UTC)   (09:00 Kyiv, 06:00 UTC)
         │                         │                         │
  • Tracker Atom RSS        • UDB API (3DS/DS)        • Daily Digest
  • Parse topic pages       • ForTheUsers (Switch/WiiU)• Homebrew Digest
  • Translate RU → UA       • VitaForge (Vita/PSP)    • Swuk Digest
  • Lookup screenshots      • GitHub/GitLab APIs      
  • Validate YT trailers    • Swuk RSS feed
         │                         │                         │
         ▼                         ▼                         ▼
   Telegram Post            data/hb_state.json         Telegram Post
  (Immediate post)     data/homebrew_digest_data.json  (Consolidated)
```

## Features

### 1. Main RuTracker Feed Checker (`main.py`)
- Pulls from a configured Atom feed every 15 minutes.
- Parses topic contents using search strategies (phrase search, author changelog patterns) to extract update text.
- Translates descriptions and update details from Russian to Ukrainian using GPT-4o-mini (`gpt-5.4-nano` fallback).
- Validates and searches for game trailers on YouTube using word-overlap and GPT title validation.
- Downloads screenshots using TitleDB by matching game titles.
- Posts detailed announcements to Telegram immediately.

### 2. Multi-Source Homebrew Collector (`collect_homebrew_updates.py`)
Checks various platforms for homebrew updates:
- **Phase 1a (3DS/DS)**: Universal-DB API.
- **Phase 1b (Switch)**: ForTheUsers Switch repository JSON.
- **Phase 1c (Wii U)**: ForTheUsers Wii U repository JSON.
- **Phase 1d (PS Vita & PSP)**: VitaForge / VitaDBtoo database (Homebrew, Plugins, PC Tools, PSP Homebrew).
- **Phase 1e (Switch Ports)**: ChanseyIsTheBest/SwitchPorts markdown tables with Collision Resolution against manual releases and existing repos.
- **Phase 2 (GitHub/GitLab)**: General registry matching of repositories.
- **Descriptions Cache**: Translated app descriptions are cached in `data/hb_descriptions.json` to prevent duplicate translations.
- **Changelog Summarization**: GPT compiles a one-sentence Ukrainian summary from raw update notes.

### 3. Swuk Localizations Collector (`collect_swuk_updates.py`)
- Tracks Ukrainian Switch translation releases via the swuk.com.ua RSS feed.
- Fetches supported game versions and updates state.
- Queues localization entries into `data/swuk_digest_data.json`.

### 4. Custom Switch Repositories Collector (`collect_custom_releases.py`)
- Tracks custom GitHub authors (`NaGaa95`, `ChanseyIsTheBest`, `delsonazevedo`, `boraeskicioglu`, `PalindromicBreadLoaf`) for Nintendo Switch homebrew applications, ports, and games.
- State is persisted in `data/custom_releases_state.json` (synced with Gist), tracking `last_run` timestamp and author history.
- Evaluates releases over the last 3 weeks (21 days) for newly added authors, and since `last_run` for existing authors.
- Uses LLM verification to confirm that repositories are valid Nintendo Switch homebrew software before queueing them to `data/manual_releases.json`.

### 5. Nintendo eShop Deals & Wishlist Module (`send_eshop_deals.py`, `bot_interactive.py`)
- Automatically monitors official Nintendo eShop catalog for active game discounts on top popular franchises (Zero Shovelware).
- Enriches games with **Metacritic** and **RAWG** ratings, original English hashtag genres, and AI synopsis translations with persistent multi-key caching.
- Dynamically generates graphic platform badges directly onto game covers (`Nintendo Switch`, `Nintendo Switch 2 • EXCLUSIVE`, `Nintendo Switch 1 & 2`).
- Real-time multi-regional price comparison:
  - 💰 **🇪🇺 Europe base catalog price**.
  - 🥇 🥈 🥉 **Top 3 cheapest regions worldwide** with currency conversion (~₴ UAH / $ USD).
  - 🇵🇱 **Poland (PLN)** and 🇺🇸 **United States (USD)** guaranteed regional prices.
- **Personal & Chat Wishlists (`/wishlist`)**:
  - Track individual games and check real-time discounts.
  - Automated cron discount alerts sent directly to users/topics when wishlisted games go on sale.

### Interactive Bot Commands

| Command | Description |
| --- | --- |
| `/deals [N]` | Show top N popular Switch game discounts sequentially in real time (e.g. `/deals 5`). |
| `/search <title>` | Search for a specific game and display live multi-region price comparison (e.g. `/search Zelda`). |
| `/wishlist` | View your active wishlist with live discount and price status. |
| `/wishlist add <title>` | Add a game to your wishlist to receive automated sale alerts. |
| `/wishlist remove <title>` | Remove a game from your wishlist. |
| `/wishlist clear` | Clear your entire wishlist. |
| `/subscribe_deals` | Subscribe the current chat or forum topic to automated deals broadcasts. |
| `/unsubscribe_deals` | Unsubscribe from automated deals broadcasts. |
| `/deals_settings` | View active quality filters for the chat. |
| `/set_min_discount <%>` | Adjust minimum discount percentage (e.g. `/set_min_discount 40`). |
| `/set_min_rating <score>` | Adjust minimum Metacritic score (e.g. `/set_min_rating 75`). |
| `/help` | Display command help and usage instructions. |

### 6. Daily Digests (`send_*_digest.py`)
Sends aggregated digests to configured Telegram channels once a day (scheduled at 09:00 Kyiv time, 06:00 UTC):
- **Daily Digest**: Combines new and updated tracker posts.
- **Homebrew Digest**: Groups homebrew updates by platform.
- **Swuk Digest**: Ukrainian Switch translation updates.
- **eShop Deals Digest**: Top Nintendo Switch discounts and regional price comparisons (targets configured topic ID `561344`).

---

## Configuration & Deployment

### Config Files
All configurations are stored in the `config/` directory:
- `settings.json`: Default configuration (channels, endpoints, fallback values).
- `local_settings.json`: Overrides defaults locally (API keys, bot token).

Required keys (environment variables take precedence over both JSON files):

| Key | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot account used for all posting. |
| `OPENAI_API` | Translation and description summarisation. |
| `YOUTUBE_API_KEY` | Trailer lookup. Optional — the feature degrades quietly. |
| `GITHUB_TOKEN` | Reading releases from GitHub. Public read-only is enough. Automatically falls back to unauthenticated requests if token returns HTTP 401. |
| `GIST_ID` | Gist holding the synced state. **No default** — `sync_gist_state.py` exits rather than guess. |
| `GIST_TOKEN` | Gist read/write. Falls back to `GITHUB_TOKEN`, which then needs the `Gists: Read and write` permission. |

### State Synchronization (`sync_gist_state.py`)
State lives in a GitHub Gist so that runs on different machines stay consistent.
These files are synced: `posted_links.json`, `hb_state.json`, `daily_digest_data.json`,
`homebrew_digest_data.json`, `last_entry.txt`, `last_digest_run.json`,
`last_homebrew_digest_run.json`, `manual_releases.json`, `list_hb.json`,
`custom_releases_state.json`.

Public Gist downloading and merge state fetching automatically retry without authentication if `GIST_TOKEN` or `GITHUB_TOKEN` returns HTTP 401 Bad credentials.
If the token lacks Gist write permission or is invalid/expired, `upload` fails with 401/403 and state cannot be pushed to Gist.

### Manual Releases Queue (`data/manual_releases.json`)
Allows queueing custom posts that will be seamlessly merged into the next digest run.
- **Processing limit**: Maximum 5 unprocessed releases are handled per script execution to avoid flood.
- **Updates skip**: Collectors will automatically skip update checking for any app that has a pending (unprocessed) manual release in the queue to avoid announcement ordering bugs.

Format for a manual homebrew entry:
```json
[
  {
    "type": "homebrew",
    "app_name": "App Name",
    "version": "v1.0.0",
    "release_url": "https://github.com/...",
    "platform": "Switch",
    "is_new": true,
    "description": "App description in Ukrainian.",
    "date": "2026-07-03T10:00:00+03:00",
    "processed": false
  }
]
```

### Cloudflare Bypass via FlareSolverr
To bypass Cloudflare JavaScript challenges (*Just a moment...*) when fetching topic pages from RuTracker on server environments:
- The bot features an automated fallback to FlareSolverr (`FLARESOLVERR_URL`, default `"http://localhost:8191/v1"`).
- Run FlareSolverr via Docker on your server:
  ```bash
  docker run -d --name=flaresolverr -p 8191:8191 --restart=always ghcr.io/flaresolverr/flaresolverr:latest
  ```
- When `tracker_parser.py` encounters a 403 response or Cloudflare challenge, it automatically routes the request through FlareSolverr to solve the challenge, fetch HTML, and cache updated `cf_clearance` cookies in memory.

### Scheduling & Cooldowns
To protect against GitHub Actions schedule delays and prevent duplicate posts:
- Collectors and Send scripts implement a **20-hour cooldown check** internally.
- Even if GitHub Actions cron triggers a script multiple times in its scheduled hour, the script runs successfully only once per day.
- A forced run can be triggered manually from GitHub Actions by choosing the task under `force_task` inputs.

