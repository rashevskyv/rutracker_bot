## Senior Audit Report

### Status: APPROVED

### 1. Summary of Review

Round 3. Round 2 (`v0.7.62`, `7cfb153`) left three handoff items; the user asked the reviewer to implement them instead of handing them to the Junior. They are done in `v0.7.63`, together with the cheap recommendations. No handoff items remain. The round-2 report is in the history of this file.

The three items shared one root: the Gist sync could not tell a deletion from a concurrent addition, and the custom collector read a failed request as an empty result. Both are fixed at that root rather than per symptom: the registry merge is now three-way against a snapshot of the Gist at the last sync, and the collector only records an author as checked after a complete check.

Two round-2 statements are corrected here:

- **Wine-NX `test-build-2` was re-queued but not re-posted.** The `v0.7.57` sync made the stale row pending again (Gist revision `0580b72`, 2026-10-01T12:37:40Z), and the 10:00 Kyiv digest on 2026-10-02 marked it processed. The homebrew digest data still holds that release with its 2026-09-22 timestamp, so it fell outside the posting window.
- **Pending manual releases are published at 10:00 Kyiv (07:00Z), not 12:00.** In the Gist, Far Cry flipped to `processed: true` at 07:00:28Z. The `last_*_run.json` timestamps are naive server-local time (UTC+2), not UTC.

The restored noJMe and NFS Underground 2 rows survived the server cycles at 16:00Z and later. The watcher confirmed both at 16:06:42Z.

What the reviewer ran in round 3:

- The new tests against the committed code (`HEAD` = `7cfb153`) in a scratch copy: 8 of 9 fail, each on the defect it targets. The ninth covers `SKIP_REPOS` from `v0.7.61`. Against the fixed code all 9 pass.
- The new merge on the real 280-row registry. A no-op sync is byte-identical with and without a base, and a replay of the 13:05:57Z overwrite keeps both rows. A later local `processed` flip reaches the Gist.
- `python -m pytest -n auto -q`: 117 passed. The Gist head (`68a1caf`) and the modification times of every file in `data/` and `config/` were the same before and after, and the tests created no `data/.gist_base`.
- `py_compile` on Windows (Python 3.14) and WSL (Python 3.12), `bash -n run_custom_collector.sh`, `git diff --check`.
- Gist revision history, read-only, for the two corrections above and for the cache finding in section 4.

The collector and the Gist sync were not run against production in this round.

### 2. Fixes Applied by Reviewer

Part of `v0.7.63`.

- **`sync_gist_state.py:52-112`** (`load_base`, `save_base`, `merge_manual_releases`): three-way merge of `manual_releases.json` against `data/.gist_base/manual_releases.json`, the Gist content at this machine's last download (`:241`) or upload (`:497`). A row only one side has is an addition unless the base has it unchanged, in which case the other side deleted it. A row both sides have takes the local version only if it was edited since the base, and stays processed if either side processed it. Without a base, on the first sync after deployment, nothing counts as deleted, and the old guard against re-adding a processed, re-versioned row still applies. Covered by `test_gist_config.py::test_merge_manual_releases_three_way`.
- **`sync_gist_state.py:254`** (`merge_json_files`): takes `base` instead of the unused-after-this-change `is_download`; both call sites updated.
- **`sync_gist_state.py:436-439`** (`upload_state`, the pre-merge fetch): when the pre-merge fetch fails, the upload is aborted. It used to upload the local files unmerged, which is the same loss by another path.
- **`collect_custom_releases.py:23-30`** (`run_gist_sync`): syncs only `manual_releases.json` and `custom_releases_state.json`. On the server, `run_checker.sh` already syncs everything else around the command. This also stops the collector's download from resetting `last_entry.txt` and from bypassing `--exclude-eshop-state`.
- **`collect_custom_releases.py:88-129, 250-260, 276-292, 314-321, 366-370`**: three failure paths no longer turn into data.
  - `fetch_user_repos` returns `None` on failure, and the author is skipped without being recorded.
  - `fetch_latest_release` raises on anything but 404; the repository is skipped and the author is not marked as checked.
  - An unreadable or non-list `manual_releases.json` aborts the run.
  - An existing author's cutoff is their own `last_checked` instead of the global `last_run`, so a run that failed for them is retried from there.
- **`collect_custom_releases.py:342, 348-358`**: an LLM reply with `"is_switch_homebrew": "false"` is honoured, and `null` platform, name or description fields fall back to defaults. A `null` platform would have broken `digest/homebrew.py:199` for every later digest.
- **`collect_custom_releases.py:131-150`** (`repo_slug`, `is_already_added`): repositories are compared by host/owner/repo instead of two-way substring. `FPSLocker-Warehouse` is no longer hidden behind `FPSLocker`, and an entry with an empty URL no longer hides every repository.
- **`test_custom_releases_collector.py`**: one test per case above, sharing a `run_main` fixture that fakes the settings, Gist sync, GitHub API and LLM.
- **`conftest.py:22-23`**: also sets `GIST_ID` to a Gist that does not exist, so a `sync_gist_state.py` subprocess started by a test cannot reach production.
- **`run_custom_collector.bat`, `run_custom_collector.sh`**: dropped the hand-copied author list, which is how it drifted in `v0.7.58`.
- **`README.md`, `GEMINI.md`**: described the collector's retry behaviour, its two-file sync and the three-way merge.
- **`plan.md`**: re-opened the `v0.7.56` item that `v0.7.57` dropped (check the live eShop messages in Telegram), and added deploying before the 07:00 Kyiv collector run as an open item.
- **`CHANGELOG.md`, `task.md`, `walkthrough.md`**: `v0.7.63` entries.

### 3. Blockers / Handoff Items (Crucial)

None.

### 4. Recommendations & Code Quality Improvements (Optional/Minor)

- [ ] **Deployment timing**: the custom collector runs on the server at 07:00 Kyiv and makes `aks796`'s first pass. The retry fixes protect that pass only if the server runs `v0.7.63` by then.
- [ ] **`sync_gist_state.py:410`** (default branch of `merge_json_files`): files without a dedicated merge return the Gist copy on both download and upload, so local additions never reach the Gist. In 500 Gist revisions since 2026-09-28T07:45Z, `hb_descriptions.json`, `translations_cache.json`, `eshop_descriptions.json`, `eshop_region_prices_cache.json` and `list_hb.json` never changed. New translations are therefore redone on every run, and `list_hb.json` flag changes do not persist. The wishlist and subscription files are not in the Gist at all, so no user data is affected today. For the caches, a key union where local wins would be enough; user-data files would need the same three-way treatment as the registry.
- [ ] **Gist id in a public repository**: the production Gist id is still in the git history (`test_gist_config.py` before `v0.7.62`). A secret Gist is readable by anyone who has its id. Moving the state to a new Gist is the only remedy; this is the user's decision.
- [ ] **Production `eshop_posted_deals.json`**: the Gist copy holds fixture rows from earlier test runs (for example `title_gamec`), which the union merge carries into production state. Low impact; with the guard no new ones arrive.
- [ ] **`aks796` ports outside the window**: `bombsquad_nx`, `infinityblade_nx`, `bse_rebombed_nx`, `abreloaded_nx` and `flappy_bird_nx` are older than 21 days and will not be announced unless added by hand.
- [ ] **`collect_homebrew_updates.py:116`** (`is_unprocessed_manual`): two-way `startswith` on names means a pending `Flappy Birds Family (aks796)` suppresses update posts for the tracked `Flappy Bird` while it waits in the queue. Changing it touches update suppression across all sources, so it needs its own task.
- [ ] **`.github/workflows/bot_runner.yml:95`**: no once-per-day guard for the collector step. Latent, because the workflow has no scheduled runs.
- [ ] **Test dependencies**: the documented `pytest -n auto` needs `pytest-xdist`, which no requirements file lists.

### 5. Next Assignment

- **Original goal**: manual release entries added from a dev machine must survive in the shared Gist state while the production bot syncs every 30 minutes, and the custom releases collector must fail safe instead of writing wrong or missing data.
- **Already done**: everything in section 2 (`v0.7.63`), on top of `v0.7.57`–`v0.7.62`.
- **Required**: nothing; there are no handoff items. If a section 4 item is taken up, it gets its own task with a test.
- **Do not touch**: the `conftest.py` guard; the LLM prompt and the name-marker safeguard in `collect_custom_releases.py`; the eShop rotation logic; `data/` and the remote Gist.
- Update `walkthrough.md` and `audit.md`, run `graphify update`, re-submit for review.
