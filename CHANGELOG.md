# Changelog

All notable changes to the RuTracker Bot project will be documented in this file.

## [v0.6.84] - 2026-08-18

### Changed
- **Popular Hits & AAA Deals Algorithm (Zero Shovelware)**:
  - `services/eshop/popular_catalog.py`: Added curated catalog of 200+ top popular AAA franchises and critically acclaimed indie masterpieces on Nintendo Switch (Persona, Wolfenstein, Witcher, DOOM, Dark Souls, Monster Hunter, Resident Evil, Batman, Hogwarts Legacy, Mortal Kombat, Sonic, Celeste, Dead Cells, Disco Elysium, etc.) plus major reputable publishers (SEGA, Capcom, Ubisoft, WB Games, Bethesda, Square Enix, Devolver, etc.).
  - `services/eshop/eshop_service.py`: Added `fetch_popular_discounted_games()` to query discounts directly against genuine popular games, eliminating 100% of $0.99 shovelware and unrated clutter.
  - `services/eshop/deal_filter.py`: Routed `/deals` and scheduled deal broadcasts through the popular catalog engine.

## [v0.6.83] - 2026-08-18

### Added
- **Automated Platform Badges on Game Covers**:
  - `services/eshop/banner_service.py`: Automated dynamic overlay of platform badges on game cover images using Pillow. Renders sleek pill badges with dual Joy-Con icons and responsive typography:
    - **Nintendo Switch (1)**: Classic Nintendo Red badge (`Nintendo Switch`).
    - **Nintendo Switch 2 Exclusive**: Crimson & Gold border badge (`Nintendo Switch 2 • EXCLUSIVE`).
    - **Nintendo Switch 1 & 2**: Red & White dual badge (`Nintendo Switch 1 & 2`).
  - `send_eshop_deals.py` & `services/eshop/bot_commands.py`: Integrated badged image generation into automatic broadcasts and interactive `/deals` & `/search` commands.
  - `requirements.txt`: Added `Pillow>=10.0`.

## [v0.6.82] - 2026-08-18

### Changed
- **Untranslated Genre Hashtags**:
  - `services/eshop/formatters.py`: Kept game genres untranslated in clean English hashtag format (e.g. `🏷 #Lifestyle #Other #Puzzle`, `🏷 #Action #Adventure #RPG`).

## [v0.6.81] - 2026-08-18

### Added
- **Global Persistent Translation Caching**:
  - `services/translation.py`: Implemented SHA-256 text-hash caching (`data/translations_cache.json`) for all tracker post translations and short descriptions. Avoids re-translating unchanged posts across bot restarts and cron runs.
  - `services/eshop/deal_filter.py`: Ensured eShop descriptions are cached by game ID in `data/eshop_descriptions.json`.
  - `sync_gist_state.py`: Added `translations_cache.json` and `hb_descriptions.json` to state synchronization.

## [v0.6.80] - 2026-08-18

### Fixed
- **Cross-Region Price Retrieval (USA & Americas)**:
  - `services/eshop/region_price_service.py`: Integrated automated Nintendo of America Algolia search resolution by game title. This resolves American NSUIDs so that **USA 🇺🇸**, **Canada 🇨🇦**, **Mexico 🇲🇽**, and **Brazil 🇧🇷** prices are reliably fetched alongside European/PAL regional prices.
  - `services/eshop/deal_filter.py`: Passed game titles to regional price resolver to enable dual-region indexing.

## [v0.6.79] - 2026-08-18

### Added
- **Permanent Key Regions Display (Poland, USA, Thailand, Turkey)**:
  - `services/eshop/formatters.py`: Guaranteed display of **Poland 🇵🇱**, **USA 🇺🇸**, **Thailand 🇹🇭**, and **Turkey 🇹🇷** alongside the **Top 3 Cheapest Regions (🥇🥈🥉)** worldwide for every game.
  - `services/eshop/region_price_service.py`: Added Thailand (`TH`) and Turkey (`TR`) to active tracked query regions.
  - `services/eshop/currency_service.py`: Added fallback rates for Thai Baht (`THB`) and Turkish Lira (`TRY`).
  - `services/eshop/models.py`: Added 🇹🇭 and 🇹🇷 flag mappings.

## [v0.6.78] - 2026-08-18

### Added
- **Switch 1 & Switch 2 Platform Detection**:
  - `services/eshop/models.py`: Added `system_names`, `platform_label`, and `is_switch_2_exclusive` property to detect Nintendo Switch 1 vs Switch 2 vs Switch 1 & 2 games.
  - `services/eshop/eshop_service.py`: Extracted `system_names_txt` from Nintendo Solr catalog responses.
  - `services/eshop/formatters.py`: Added explicit platform badge line (e.g. `🕹 Платформа: Nintendo Switch` or `🕹 Платформа: 🌟 Nintendo Switch 2 (Ексклюзив)`).
- **Configurable Cron & Interval Broadcaster**:
  - `send_eshop_deals.py`: Added support for configurable `interval_hours` (e.g. 2 hours), `--force` CLI parameter, and execution state tracking in `data/last_eshop_deals_run.json`.

## [v0.6.77] - 2026-08-18

### Added
- **Full Ukrainian Localization for eShop Deals**:
  - `services/eshop/deal_filter.py`: Automated translation of game descriptions / synopses into Ukrainian using OpenRouter (`openai/gpt-5.6-luna` / `deepseek/deepseek-v4-flash-0731`) with persistent local caching in `data/eshop_descriptions.json`.
  - `services/eshop/formatters.py`: Localized genre names (e.g. `Lifestyle` $\rightarrow$ `Лайфстайл`, `Puzzle` $\rightarrow$ `Головоломка`, `Action` $\rightarrow$ `Екшен`).
  - `services/eshop/formatters.py`: Localized regional country names in comparison lines (e.g. `New Zealand` $\rightarrow$ `Нова Зеландія`, `Norway` $\rightarrow$ `Норвегія`, `Poland` $\rightarrow$ `Польща`, `USA` $\rightarrow$ `США`).
  - `sync_gist_state.py`: Added `eshop_descriptions.json` and `eshop_subscriptions.json` to state synchronization.

## [v0.6.76] - 2026-08-18

### Fixed
- **eShop Formatter Import**: Restored missing `GameDeal` import in `services/eshop/formatters.py` to fix `NameError: name 'GameDeal' is not defined` during bot startup.

## [v0.6.75] - 2026-08-18

### Added
- **OpenRouter & Multi-LLM Routing**:
  - `core/settings_loader.py`: Added first-class support for `OPENROUTER_API_KEY` and OpenRouter endpoint (`https://openrouter.ai/api/v1`) with custom headers.
  - `services/gpt.py`: Configured primary translation and AI engine to use **`openai/gpt-5.6-luna`** ($0.10/M) with automatic fallback to **`deepseek/deepseek-v4-flash-0731`** ($0.14/M) and `google/gemini-3.5-flash-lite`.
  - `services/translation.py`: Routed tracker post translation and short description summarization through OpenRouter.
  - `services/ai_validator.py`: Routed YouTube trailer relevance checking and description compression through OpenRouter.
  - `collect_homebrew_updates.py` & `collect_custom_releases.py`: Integrated with OpenRouter client and Luna/DeepSeek model hierarchy.
  - `.github/workflows/bot_runner.yml`: Added `OPENROUTER_API_KEY` secret support.

## [v0.6.74] - 2026-08-18

### Added
- **Base Price Line UAH Conversion**:
  - `services/eshop/formatters.py`: Updated the top base price line (e.g. `💰 6.99 EUR ➡️ 1.39 EUR (-80%)`) to also display the UAH and USD equivalents: `💰 6.99 EUR ➡️ 1.39 EUR (-80%) (~62 грн / $1.51)`.
  - `services/eshop/formatters.py`: Filtered out unranked popularity placeholder values (`#999999`) to show clean unrated status instead.
  - `services/eshop/bot_commands.py` & `send_eshop_deals.py`: Connected `currency_service` instance directly to deal formatting.

## [v0.6.73] - 2026-08-18

### Added
- **UAH (Hryvnia) Conversion**:
  - `services/eshop/currency_service.py`: Added automatic conversion to Ukrainian Hryvnia (`convert_to_uah`) based on live exchange rates from `open.er-api.com`.
  - `services/eshop/models.py`: Added `converted_uah` attribute to `RegionalPrice`.
  - `services/eshop/formatters.py`: Updated deal card formatting to display local prices with both UAH (e.g. `~80 грн`) and USD (e.g. `$1.94`) approximations (e.g. `🥇 🇳🇿 New Zealand: 3.29 NZD (-85%) (~80 грн / $1.94)`).
  - `test_eshop_module.py`: Added tests for UAH conversion and message formatting.

## [v0.6.72] - 2026-08-17

### Added
- **Nintendo eShop Deals Module (`services/eshop`)**:
  - `services/eshop/eshop_service.py`: Direct client for official Nintendo Store Catalog Search API without Cloudflare barriers.
  - `services/eshop/currency_service.py`: Real-time FX exchange rates with fallback cache (`open.er-api.com`).
  - `services/eshop/region_price_service.py`: Multi-regional price query engine across 12+ countries.
  - `services/eshop/rating_service.py`: RAWG & Metacritic score enrichment engine.
  - `services/eshop/deal_filter.py`: Quality evaluation algorithm (`deal_score`, discount %, Metacritic >= 70).
  - `services/eshop/formatters.py`: Telegram message formatter with 🥇🥈🥉 Top 3 cheapest regions, Poland 🇵🇱 (PLN), and USA 🇺🇸 (USD).
- **eShop Deals Sender Script (`send_eshop_deals.py`)**: Standalone and scheduled broadcaster that sends top discounted Switch games to configured channels/groups (`DIGEST_CHANNEL` / `GROUPS` / `TEST_GROUPS`).
- **Gist State Sync**: Added `eshop_posted_deals.json` and `last_eshop_deals_run.json` to `sync_gist_state.py`.
- **Configuration**: Added `ESHOP_DEALS` settings block in `config/settings.json`.
- **Tests**: Added `test_eshop_module.py` and `pytest.ini` with 10 passing parallel tests.

## [v0.6.71] - 2026-08-17

### Added
- **Manual Releases Addition**: Added 5 new homebrew and decompilation releases to `data/manual_releases.json` with detailed, game-specific Ukrainian descriptions:
  - `Lighthouse (Banjo-Kazooie) (HarbourMasters)` (`1.1.0`, PC) from [HarbourMasters/Lighthouse](https://github.com/HarbourMasters/Lighthouse)
  - `Silent Hill (DerilDX)` (`1.1.0`, Switch) from [DerilDX/silent-hill-decomp-nx](https://github.com/DerilDX/silent-hill-decomp-nx)
  - `GTA: Liberty City Stories (StevensND)` (`v1.0.3`, Switch) from [StevensND/gtalcs_nx](https://github.com/StevensND/gtalcs_nx)
  - `Subway Surfers (StevensND)` (`1.0.2`, Switch) from [StevensND/subwaysurfers_nx](https://github.com/StevensND/subwaysurfers_nx)
  - `Zombotron Re-Boot (StevensND)` (`v1.0.2`, Switch) from [StevensND/zombotron_nx](https://github.com/StevensND/zombotron_nx)
- **State Synchronization**: Downloaded current state from Gist and uploaded the updated `manual_releases.json` to GitHub Gist.

## [v0.6.70] - 2026-08-16

### Changed
- **Manual Releases Descriptions Translation**: Reviewed and translated all English descriptions for queued Switch homebrew releases in `data/manual_releases.json` into Ukrainian (`G-Diffuser`, `lsfg`, `porpoise`, `dekopon`, `uam`, `dynarmic`).
- **State Synchronization**: Uploaded updated `manual_releases.json` and state files to GitHub Gist.

## [v0.6.69] - 2026-08-16

### Added
- **Custom Releases Collector (`PalindromicBreadLoaf`)**: Added Nintendo Switch homebrew developer `PalindromicBreadLoaf` to `TARGET_USERS` in `collect_custom_releases.py`.
- **New Switch Homebrew Releases**: Automatically discovered and queued 9 new Nintendo Switch homebrew releases from `PalindromicBreadLoaf` (including `G-Diffuser`, `lsfg`, `porpoise`, `dekopon`, `fzerox`, `uam`, `libultraship`, `nxvk`, `dynarmic`) and 1 new release from `ChanseyIsTheBest` (`baldi_nx`) to `data/manual_releases.json` with `"processed": false`.
- **State Synchronization**: Updated `data/custom_releases_state.json` and synchronized state with GitHub Gist.
- **Documentation & Scripts**: Updated `README.md`, `GEMINI.md`, and `run_custom_collector.bat` to include `PalindromicBreadLoaf`.

## [v0.6.68] - 2026-08-14

### Added
- **Manual Release Addition (`The Legend of Zelda: The Minish Cap`)**: Added Nintendo 3DS native port release `The Legend of Zelda: The Minish Cap (EstebanPdN)` (`1.1`, 3DS) from [EstebanPdN/zelda-tmc-3ds](https://github.com/EstebanPdN/zelda-tmc-3ds) to `data/manual_releases.json` with `"processed": false` for upcoming homebrew digest publication.
- **State Synchronization**: Downloaded the latest state and uploaded the updated state to GitHub Gist.

## [v0.6.67] - 2026-08-13

### Added
- **Manual Release Addition (`Docklight`)**: Added Nintendo Switch native Banjo-Kazooie decompilation port release `Docklight (Banjo-Kazooie) (PalindromicBreadLoaf)` (`1.0.3`, Switch) from [PalindromicBreadLoaf/Docklight](https://github.com/PalindromicBreadLoaf/Docklight) to `data/manual_releases.json` with `"processed": false` for upcoming homebrew digest publication.
- **State Synchronization**: Downloaded the latest state and uploaded the updated state to GitHub Gist.

## [v0.6.66] - 2026-08-13

### Added
- **VitaForge & VitaDBtoo Integration (Phase 1d)**: Migrated PS Vita and PSP homebrew update tracking from the defunct Vita Homebrew Browser / VitaDB backend (`rinnegatamante.eu`) to the community-maintained **VitaDBtoo** catalog and **VitaForge** database endpoints (`DrDecki/VitaDBtoo-db`).
- **PSP Homebrew Support**: Added `psp_apps.json` endpoint to Phase 1d, expanding homebrew update monitoring to PSP applications in addition to PS Vita homebrews, plugins, and PC tools.
- **GET Request Protocol & Seamless State Compatibility**: Updated `collect_vitadb_updates()` to fetch static catalog JSONs using HTTP `GET` requests while maintaining 100% ID backwards compatibility with existing entries in `data/vitadb_state.json`.
- **Documentation**: Updated `README.md` and `GEMINI.md` to reflect the new VitaForge / VitaDBtoo data source architecture.

## [v0.6.65] - 2026-08-13

### Added
- **Custom Releases Collector (`boraeskicioglu`)**: Integrated Nintendo Switch port developer `boraeskicioglu` into `TARGET_USERS` in `collect_custom_releases.py`.
- **New Manual Releases**: Automatically collected and queued 3 new Nintendo Switch port releases (`Golden Balloon (boraeskicioglu)` v1.2.1-nx, `Sonic the Hedgehog 4: Episode II (boraeskicioglu)` v0.2, and `How Many Dudes? (boraeskicioglu)` v1.0.0) to `data/manual_releases.json` with `"processed": false`.
- **State Synchronization**: Updated `data/custom_releases_state.json` and synchronized state with GitHub Gist.
- **Documentation & Scripts**: Updated `README.md`, `GEMINI.md`, and `run_custom_collector.bat` to include `boraeskicioglu`.

## [v0.6.64] - 2026-08-11

### Added
- **Manual Release Addition (`Gen1Recomp`)**: Added Nintendo Switch native recreation release `Gen1Recomp (Pokémon Red/Blue/Yellow) (bryanthaboi)` (`0.1.77`, Switch) from [bryanthaboi/gen1recomp](https://github.com/bryanthaboi/gen1recomp) to `data/manual_releases.json` with `"processed": false` for upcoming homebrew digest publication.
- **State Synchronization**: Synchronized and uploaded updated bot state including manual releases to GitHub Gist.

## [v0.6.63] - 2026-08-08

### Fixed
- **GitHub API 401 Unauthorized Fallback**: Implemented automatic unauthenticated retries across `collect_custom_releases.py` (`fetch_user_repos`, `fetch_latest_release`), `collect_homebrew_updates.py` (`github_request`), and `sync_gist_state.py` (`upload_state` pre-merge Gist fetch). Public GitHub endpoints now seamlessly fallback to unauthenticated requests if an invalid or expired token is provided in `local_settings.json`.
- **Subprocess Encoding Safety (`UnicodeDecodeError`)**: Updated `run_gist_sync` in `collect_custom_releases.py` to set `PYTHONIOENCODING="utf-8"` and `errors="replace"` on `subprocess.run`, preventing crashes when reading non-UTF-8 console characters on Windows.

## [v0.6.62] - 2026-08-05

### Added
- **Manual Release Addition**: Downloaded current Gist state and added Ukrainian GBA localization release `Golden Sun: The Lost Age (Black Dragon Studio)` (v1.0, GBA) by author `turbodiesel` to `data/manual_releases.json` with `"processed": false` for digest announcement.

### Fixed
- **Gist Download 401 Fallback**: Updated `sync_gist_state.py` with `User-Agent` headers and automatic unauthenticated download fallback when receiving HTTP 401 Bad Credentials for public Gists. Added `GIST_ID` to `config/local_settings.json`.

## [v0.6.61] - 2026-07-28

### Fixed
- **FlareSolverr Cookie Payload & Mirror Fallback**: Fixed FlareSolverr 500 error caused by sending outdated/invalid `bb_session` cookies in FlareSolverr payload. Added fallback to alternative mirror `rutracker.net` if `rutracker.org` FlareSolverr request times out.

## [v0.6.60] - 2026-07-28

### Added
- **Cloudflare Challenge Bypass & FlareSolverr Fallback**: Added automatic Cloudflare JavaScript Challenge bypass integration in `parsers/tracker_parser.py`. When `curl_cffi` receives HTTP 403 or encounters Cloudflare's *"Just a moment..."* challenge page, requests automatically fall back to a local FlareSolverr instance (`FLARESOLVERR_URL`, default `"http://localhost:8191/v1"`).
- **Cookie Caching**: FlareSolverr response cookies (including `cf_clearance`) are dynamically cached in `RUTRACKER_COOKIES` in memory to speed up subsequent topic page fetches.
- **Config & Documentation**: Configured `FLARESOLVERR_URL` in `config/settings.json` and `core/settings_loader.py`, and updated `README.md` with Docker installation and configuration instructions.

## [v0.6.59] - 2026-07-26

### Added
- **Custom Releases Collector Enhancement & State Tracking**: Added author `delsonazevedo` to `TARGET_USERS` in `collect_custom_releases.py`. Implemented state persistence via `data/custom_releases_state.json` (tracked in `sync_gist_state.py`) to record `last_run` timestamp and per-author tracking history.
- **Dynamic Cutoff & Switch Homebrew AI Verification**: New authors are evaluated for releases over the last 3 weeks (21 days), while existing authors check all releases published since `last_run`. Added LLM verification to filter and verify that collected repositories are homebrew games, ports, or applications for Nintendo Switch. Updated `run_custom_collector.bat`.

## [v0.6.58] - 2026-07-26

### Added
- **Manual Release Additions**: Downloaded latest state from Gist and added 4 new manual homebrew releases (`NX-torrent-player` v0.1.1 by `shodowlo`, `PipenSX` v1.1.1 by `i3sey`, `TorrentShopNX` v2.1 by `Langegen`, and fan game port `Zelda Oni Link Begins` v1.1 by `worthis`) to `manual_releases.json` with `"processed": false` for upcoming digest announcements. Force-uploaded updated state to GitHub Gist (`python sync_gist_state.py upload -f`).

## [v0.6.57] - 2026-07-25

### Added
- **SwitchPorts Collector Integration (Phase 1e)**: Added multi-source homebrew collector phase for parsing Nintendo Switch port tables from [ChanseyIsTheBest/SwitchPorts](https://github.com/ChanseyIsTheBest/SwitchPorts) (`README.md`).
- **Collision Resolution Engine**: Implemented cross-checks against pending (`processed: false`) and processed (`processed: true`) entries in `manual_releases.json`, as well as GitHub Phase 2 `list_hb.json` slugs, preventing duplicate announcements or premature update notifications.
- **State Management & Caching**: Added `data/switchports_state.json` to persist version/update states, along with automated Ukrainian description generation via repo READMEs and GPT translation.

## [v0.6.56] - 2026-07-25

### Added
- **Manual Release Addition**: Added homebrew release `ys1x_nx` v0.1 (Port of Ys Chronicles 1 / Ys I: Ancient Ys Vanished for Nintendo Switch by `DI4VOLO-dev`) to `manual_releases.json` with `"processed": false` and force-uploaded updated state to GitHub Gist.

## [v0.6.55] - 2026-07-23

### Added
- **Manual Release Addition**: Added homebrew release `green-nx` v1.0.5 (Xbox Cloud Gaming client for Nintendo Switch by `rmrf404`) to `manual_releases.json` and force-uploaded updated state to GitHub Gist.

## [v0.6.54] - 2026-07-23

### Fixed
- **Gist State Upload Local Edits & Deletions Preservation**: Fixed merge logic in `sync_gist_state.py` for `manual_releases.json`. Previously, `merge_json_files` iterated over server Gist content and re-added items deleted locally. Updated merge logic to base merged list on `local_data` to preserve local deletions and edits. Added `--force` (`-f`) flag to `sync_gist_state.py upload` to allow direct forced overwrite of Gist state with local files.

## [v0.6.53] - 2026-07-23

### Fixed
- **Conditional Gist Upload Optimization**: Restored conditional `run_gist_sync("upload")` inside `if total_added_count > 0:` in `collect_custom_releases.py`. Since the script starts with `run_gist_sync("download")`, performing an upload when no new releases were generated is unnecessary and avoids superfluous Gist API calls.

## [v0.6.52] - 2026-07-23

### Fixed
- **Unconditional Gist Upload in Custom Collector**: Modified `collect_custom_releases.py` to always run `sync_gist_state.py upload` at the end of execution regardless of whether new releases were found. Ensures any manual user modifications to `manual_releases.json` or other state files are consistently synced to Gist.

## [v0.6.51] - 2026-07-23

### Changed
- **All Releases Starting From Yesterday**: Simplified `collect_custom_releases.py` to collect any new release published by target authors (`NaGaa95`, `ChanseyIsTheBest`) starting from yesterday (last 48 hours). Removed complex AI category filtering to guarantee every new release from the target authors is captured, using Gemini 3.5 Flash thinking to generate clean titles and Ukrainian descriptions.

## [v0.6.50] - 2026-07-23

### Fixed
- **Strict Game & Recency Filtering in Custom Collector**: Updated `collect_custom_releases.py` to filter out non-game repositories (kernels, DTBs, firmwares, drivers, hekate/atmosphere patches, sysmodules, tools). Added release age limit (`MAX_RELEASE_AGE_DAYS = 3`) to ensure only fresh releases published within the last 3 days are collected. Cleaned up non-game test entries from `manual_releases.json` and synchronized state with Gist.

## [v0.6.49] - 2026-07-23

### Changed
- **Gemini Web2API Model Integration**: Updated `collect_custom_releases.py` to prioritize `http://localhost:8081/v1` with `gemini-3.5-flash-thinking` model for repo analysis and translation. Fallbacks gracefully to OpenAI API and keyword extraction if local proxy is offline.

## [v0.6.48] - 2026-07-23

### Fixed
- **Custom Collector API Fallback**: Refactored OpenAI/Gemini client initialization in `collect_custom_releases.py`. Added proper loading of settings from `core.settings_loader` (supporting `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and custom models). Configured `max_retries=0` and timeouts to ensure that if local/remote LLM endpoint is unreachable, the collector immediately falls back to keyword-based extraction without hanging or crashing with connection retries.

## [v0.6.47] - 2026-07-22

### Fixed
- **Homebrew Collector Update Tracking for Manual Releases**: Updated `load_homebrew_list` in `collect_homebrew_updates.py` to automatically include all processed homebrew entries from `manual_releases.json` (`processed: true`) into the update checking pipeline. Previously, processed manual releases were never checked for subsequent GitHub/GitLab updates. Now, when an existing manual release app receives a new release/tag on GitHub, the collector detects the update, sets `is_new: false` (marking it as an update, not a new release), posts the update note, and updates both `hb_state.json` and `manual_releases.json`.

## [v0.6.46] - 2026-07-22

### Added
- **Multi-Author Repository Collector**: Refactored `collect_nagaa_releases.py` into `collect_custom_releases.py` and renamed batch script to `run_custom_collector.bat`. Added support for tracking multiple GitHub authors (`NaGaa95`, `ChanseyIsTheBest`).
- **Manual Releases**: Automatically collected 5 new Switch ports by `ChanseyIsTheBest` (`Colorsheep`, `Angry Birds Classic`, `Burger Shop`, `Burger Shop 2`, `Bloons TD 5`) into `manual_releases.json` and synchronized state with Gist.

## [v0.6.45] - 2026-07-22

### Added
- **Manual Releases**: Added 3 new homebrew ports by `ChanseyIsTheBest` to the manual releases registry:
  - `Zookeeper DX NX` (release2) — ZOOKEEPER DX port for Nintendo Switch.
  - `Bad Piggies NX` (release2) — Bad Piggies port for Nintendo Switch.
  - `PvZ Fusion EN NX` (1.0.0) — English Plants vs Zombies Fusion 3.61 port for Nintendo Switch.
- **Gist State Synchronization**: Synchronized latest database state from Gist and uploaded updated `manual_releases.json`.

## [v0.6.44] - 2026-07-18

### Added
- **Manual Release**: Added native Nintendo Switch homebrew port of `th06-switch` (Touhou 6: Embodiment of Scarlet Devil) by Swiizyu to the manual releases list.

## [v0.6.43] - 2026-07-17

### Fixed
- **Manual Releases processed field**: Fixed an issue where new manual releases generated by `collect_nagaa_releases.py` were missing the `"processed"` key. Added `"processed": false` to the dictionary of newly generated releases.
- **Database patch**: Ran a script to add `"processed": false` to all existing entries in `manual_releases.json` that lacked this field, and successfully synchronized this corrected state to Gist.

## [v0.6.42] - 2026-07-15

### Fixed
- **Gist Sync for Non-JSON Files**: Fixed a bug in `sync_gist_state.py` upload logic where non-JSON files (specifically `last_entry.txt`) were being overwritten by the Gist (server) version instead of using the updated local version. This caused `last_entry.txt` to get stuck on an outdated link, leading the bot to process the entire feed as new and re-post previously sent game updates.

## [v0.6.41] - 2026-07-15

### Added
- **NaGaa95 Repository Collector**: Added `collect_nagaa_releases.py` and `run_nagaa_collector.bat`. This script automatically monitors user `NaGaa95`'s repositories, checks if they are Nintendo Switch-related using your local Gemini API (`http://localhost:8081/v1`), translates and generates descriptions in Ukrainian, and adds them to `manual_releases.json` with safe Gist synchronization.

## [v0.6.40] - 2026-07-15

### Fixed
- **Documentation**: Finalized and checked off checklist tasks for manual release split implementation.

## [v0.6.39] - 2026-07-15

### Fixed
- **Manual Releases Separation**: Modified `process_manual_releases` to support filtering by type (`game` or `homebrew`). Updated `send_daily_digest.py` and `send_homebrew_digest.py` to only process manual releases of their respective types. This prevents the two digests from blocking each other and ensures that up to 5 releases of each type are correctly processed per run.

## [v0.6.38] - 2026-07-15

### Fixed
- **Documentation**: Finalized and marked off development tasks in `task.md`.

## [v0.6.37] - 2026-07-15

### Added
- **Safe Gist Sync Merging**: Updated `sync_gist_state.py` upload logic. Before updating the Gist, it now downloads the current Gist data and performs a field-level and entry-level merge of JSON state files (like `manual_releases.json`, `posted_links.json`, `daily_digest_data.json`, `hb_state.json`) rather than blindly overwriting. This prevents local upload commands from erasing changes made on the production server or by direct Gist edits.

## [v0.6.36] - 2026-07-15

### Fixed
- **HTML Description Truncation**: Replaced the character-slice HTML cleaning logic in `main.py` with a robust regex pattern (`r'<[^>]*$'`) that cleans any partial/incomplete HTML tags (e.g. `<a`, `</`, or `<`) at the very end of truncated update descriptions. It also correctly closes any open `<a>` tags by appending `</a>` if they remain unclosed after truncation. This prevents raw `<` characters from breaking the Telegram HTML parser and resolves the daily digest `Unsupported start tag ""` API errors.

## [v0.6.35] - 2026-07-14

### Added
- **Manual Releases Pending Count**: Updated the stats block format in both Daily and Homebrew digests to display the number of pending (unprocessed) manual releases in the queue (e.g., `Ручні релізи: додано 0 (в черзі: 12)`). This helps to easily monitor the state of the queue directly from Telegram.
- **Automated Gist Sync in run_checker**: Added automatic Gist state download (`python sync_gist_state.py download`) before running commands and state upload (`python sync_gist_state.py upload`) after commands inside `config/run_checker.sh.example`. This ensures that the local state on production servers is always in sync with GitHub Gist, preventing state mismatch and resolving the issue where manual releases were not processed on the remote server.

## [v0.6.34] - 2026-07-13

### Added
- **Manual Releases**: Added 7 new Switch ports by `delsonazevedo` to the manual releases queue (`Zelda: Link's Awakening DX HD`, `Celeste 64`, `BattleShip`, `Starship`, `Castlevania: ReVamped - Open Source Edition`, `Crazy Taxi NX`, and `OpenBOR`).
- **Author Tagging**: Updated names of existing Zelda and Castlevania manual releases in the registry to include their author names (e.g., `ZeldaMC`, `Black Dragon Studio`, `NaGaa95`, `HayatoG`, `delsonazevedo`) for better identification of duplicate/different versions.

## [v0.6.33] - 2026-07-09

### Added
- **Manual Release**: Added `Laytonbmr NX (Layton Brothers: Mystery Room)` and `Vln NX (Very Little Nightmares)` to the manual releases queue.

### Fixed
- **Dummy GitHub Token Filtering**: Improved token loading logic in `scratch/fetch_new_releases.py` to filter out invalid environment-level dummy tokens (e.g., `github_pat_antigravitydummytoken`) and local placeholder tokens, enabling successful fallback to public unauthenticated GitHub API requests.

## [v0.6.32] - 2026-07-08

### Fixed
- **HTML Sanitization for Telegram**: Updated `fix_html_for_telegram` in `utils/telegram_utils.py` to escape any HTML tags that are not allowed by Telegram (such as `<input>`, `<textarea>`, `<canvas>`), rather than passing them through as-is. Also added conversion of `<br>` tags to actual newlines `\n`.
- **Digest HTML Safety**: Integrated `fix_html_for_telegram` into `BaseDigest.send_digest` in `digest/base.py` to sanitize all digest messages and split parts before sending them, preventing Telegram API from rejecting messages with `Bad Request: can't parse entities` error due to raw tags in release names or update notes.

## [v0.6.31] - 2026-07-08

### Fixed
- **Homebrew Collector UnboundLocalError**: Removed redundant local `import os` inside the `main()` function of `collect_homebrew_updates.py` to prevent shadowing the global `os` module, which was causing an `UnboundLocalError` on startup and preventing the homebrew update checker from running.

## [v0.6.30] - 2026-07-05

### Added
- **Automatic Gist Auto-Detection**: Configured `sync_gist_state.py` to automatically detect Gist ID (`46128fc489e0fd60e226ff26dc638e97`) and local `GITHUB_TOKEN` from settings, allowing seamless one-command local state uploading (`python sync_gist_state.py upload`).

## [v0.6.29] - 2026-07-05

### Added
- **Manual Releases Stats Reporting**: Added processed manual release counts (`Ручних релізів: X`) to the daily and homebrew digest stats reports sent to test/admin Telegram channels.

## [v0.6.28] - 2026-07-05

### Fixed
- **Gist Sync Integration for Homebrew Registry**: Removed `data/list_hb.json` from git tracking and added it to `.gitignore`. Homebrew registry state is now fully synchronized via Gist alongside `manual_releases.json`, eliminating runtime git conflicts and auto-commit overheads in GitHub Actions.

## [v0.6.27] - 2026-07-05

### Added
- **Gist Config Fallback**: Updated `sync_gist_state.py` to load `GIST_ID` and `GIST_TOKEN` from `local_settings.json` or `settings.json` if they are not defined in the environment variables, simplifying local synchronization.

## [v0.6.26] - 2026-07-05

### Fixed
- **Gist Sync Integration for Manual Releases**: Removed `data/manual_releases.json` from git tracking and added it to `.gitignore` to avoid git pull conflicts on the production server. The file is now fully managed and synchronized via GitHub Gist.
- **Git line endings normalization**: Created `.gitattributes` to enforce Unix-style line endings (`LF`) for all JSON, Python, YAML, and Shell files, preventing false modifications caused by CRLF/LF line-ending mismatches.

## [v0.6.25] - 2026-07-05

### Added
- **Manual Release**: Added Marathon Recomp NX (Marathon Recomp port for Nintendo Switch) to the manual releases queue and processed the pending queue (including Ffd NX, LainNX, and Marathon Recomp NX), successfully posting them to Telegram.

## [v0.6.24] - 2026-07-03

### Added
- **Manual Release**: Added LainNX (WebGL implementation of Serial Experiments Lain PSX game for Nintendo Switch) to the manual releases queue.

## [v0.6.23] - 2026-07-03

### Added
- **Manual Release**: Added Ffd NX (Final Fantasy Dimensions port for Nintendo Switch) to the manual releases queue.

## [v0.6.22] - 2026-07-03

### Fixed
- **Description Verbosity**: Cleaned up the manual releases registry file (`data/manual_releases.json`) by removing redundant, wordy phrases like "який дає змогу грати...", "який дозволяє...", and "щоб ви могли грати...".
- **GPT Description Translation Rules**: Added strict prompt instructions to the short description translation service in `services/translation.py` to prevent the AI from generating verbose or obvious explanations in future automated updates, keeping game/app descriptions concise and direct (e.g. "Порт гри X для Nintendo Switch.").

## [v0.6.21] - 2026-07-03

### Fixed
- **Manual Releases Inclusion**: Fixed a bug where manual releases with older release dates (historical timestamps) were added to the state but excluded from the Telegram digest because their timestamp fell outside the digest's sliding window (since last run). Now, manual releases are processed with `timestamp=None` (defaulting to the current run time) so they are captured by the upcoming digest window, while their historical date is preserved in the `release_date` field for correct display in the homebrew channel.
- **Digest Scheduler Reliability**: Fixed daily digest skipping issues on GitHub Actions caused by strict timing checks in the YAML workflow (such as checks for minute < 15). GitHub Actions cron runs are frequently delayed by 10-30 minutes, which caused digest runs to be entirely skipped. 
  - Strict minutes constraints were removed from the workflow.
  - Python scripts (`send_daily_digest.py`, `send_homebrew_digest.py`, `send_swuk_digest.py`, `collect_homebrew_updates.py`, `collect_swuk_updates.py`) now implement an internal 20-hour cooldown check using new state files (`data/last_hb_collect_run.json`, `data/last_swuk_collect_run.json`).
  - This ensures that each collector and digest script runs exactly once per day, even if GitHub Actions execution is delayed or rescheduled.

### Added
- **Swuk updates workflow automation**: Added missing steps for running the Ukrainian Switch localizations RSS collector (`collect_swuk_updates.py`) and Swuk digest sender (`send_swuk_digest.py`) directly to the scheduled GitHub Actions workflow (`bot_runner.yml`).
- **Comprehensive Project Documentation**: Created a structured `README.md` at the project root documenting the core architecture, collectors, manual release formatting, scheduling, and configuration settings.
