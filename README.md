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
  • Translate RU → UA       • VitaDB API (Vita)       • Swuk Digest
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
- **Phase 1d (PS Vita)**: VitaDB APIs (Homebrew, Plugins, PC Tools).
- **Phase 2 (GitHub/GitLab)**: General registry matching of repositories.
- **Descriptions Cache**: Translated app descriptions are cached in `data/hb_descriptions.json` to prevent duplicate translations.
- **Changelog Summarization**: GPT compiles a one-sentence Ukrainian summary from raw update notes.

### 3. Swuk Localizations Collector (`collect_swuk_updates.py`)
- Tracks Ukrainian Switch translation releases via the swuk.com.ua RSS feed.
- Fetches supported game versions and updates state.
- Queues localization entries into `data/swuk_digest_data.json`.

### 4. Daily Digests (`send_*_digest.py`)
Sends aggregated digests to configured Telegram channels once a day (scheduled at 09:00 Kyiv time, 06:00 UTC):
- **Daily Digest**: Combines new and updated tracker posts.
- **Homebrew Digest**: Groups homebrew updates by platform.
- **Swuk Digest**: Ukrainian Switch translation updates.

---

## Configuration & Deployment

### Config Files
All configurations are stored in the `config/` directory:
- `settings.json`: Default configuration (channels, endpoints, fallback values).
- `local_settings.json`: Overrides defaults locally (API keys, bot token).
- `credentials.json`: Google Service Account keys for secondary services.

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

### Scheduling & Cooldowns
To protect against GitHub Actions schedule delays and prevent duplicate posts:
- Collectors and Send scripts implement a **20-hour cooldown check** internally.
- Even if GitHub Actions cron triggers a script multiple times in its scheduled hour, the script runs successfully only once per day.
- A forced run can be triggered manually from GitHub Actions by choosing the task under `force_task` inputs.
