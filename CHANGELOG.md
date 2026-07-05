# Changelog

All notable changes to the RuTracker Bot project will be documented in this file.

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
