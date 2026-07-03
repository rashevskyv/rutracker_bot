# Changelog

All notable changes to the RuTracker Bot project will be documented in this file.

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
