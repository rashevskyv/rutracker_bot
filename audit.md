## Senior Audit Report

### Status: CHANGES_REQUESTED

### 1. Summary of Review

Round 2. Round 1 approved `v0.7.57`–`v0.7.60` and shipped the reviewer changes as `v0.7.61` (`48a456d`, pushed). The automated `/code-review` pass that was still running at that sign-off has since returned 15 findings. Everything relayed below was re-checked by the reviewer against the code, the GitHub API or the Gist revision history.

The open items share one root, and it is upstream of this range: the Gist sync replaces whole files with last-writer-wins merges, and the custom collector treats a failed request as an empty result. The small tasks in this range did not introduce either weakness; they ran into both.

Round 1 missed three things:

- **The test suite wrote to the production Gist.** Every eShop rotation test ended in `sync_eshop_state_after_change()`, which force-uploads the local `data/eshop_*` state files, so each `pytest` run sent 7–21 real PATCH requests. The reviewer's first run on 2026-10-02 (12:58Z) replaced the Live Showcase state in the Gist (30 cards, last run 2026-10-02T07:10Z) with this machine's stale local copy (empty showcase, last run 2026-08-18); three later runs re-sent the same content. The Junior's `v0.7.57` run had done the same on 2026-10-01 at 12:36:49Z, and the server restored the Gist at 05:01:01Z the next morning. `merge_json_files` keeps the local list when the Gist list is empty, so the server's own showcase state is not wiped by this. Fixed in section 2, where the Gist copy is also restored.
- **The `v0.7.59` and `v0.7.60` entries had been dropped from the Gist.** Gist revision `0892411` (2026-10-02T13:05:57Z), written by the production bot, replaced `manual_releases.json` with the server's 278-row copy and dropped `noJMe (corax89)` and `Need for Speed: Underground 2 (antoxa2584x)`. The upload merge keeps local rows only, and that server cycle had downloaded its copy before the two entries were uploaded. Round 1 verified the Gist at 13:04Z, 96 seconds before the overwrite. Restored in section 2.
- **The `v0.7.60` description would have been posted cut mid-version.** It is 295 characters long; `limit_to_sentences` cut at the last dot inside the first 220, which is the dot in `v0.3.5`, giving "…Оновлення v0.3.". Three earlier rows were already posted that way. The code and the description are both fixed in section 2.

One code-review claim did not hold. `aks796/sm127_nx` and `aks796/bs_joyride_nx` do have a `1.0.0` release with an asset: the release list endpoint returns `[]` for them, but `releases/latest`, which the collector uses, returns the release. The first collector run queues real releases for all 12 ports.

What the reviewer ran in round 2:

- Gist revision history through the API, read-only: 400 revisions listed, file contents compared across about 150 of them to date each change above.
- `sanitize_digest_description` on the real pending rows, before and after the fix.
- GitHub API for the two disputed repositories (`releases/latest`, `releases/tags/1.0.0`, tags, release page).
- The Gist restore in section 2: a dry run first, then a guarded write, then every file re-read.
- `python -m pytest -n auto -q` with the new guard: 110 passed. The newest Gist revision was the same before and after the run, and no file in `data/` or `config/` changed its modification time. Before the guard each run created 7–21 Gist revisions and rewrote three `data/eshop_*` files and `config/local_settings.json`.

### 2. Fixes Applied by Reviewer

Part of `v0.7.62`.

- **`conftest.py`** (new): an autouse fixture replaces `sync_gist_state.upload_state` and `download_state` with a function that raises, and points `send_eshop_deals.STATE_FILE`, `SHOWCASE_FILE`, `LAST_RUN_FILE` and `region_price_service.CACHE_FILE` at the test's temp dir. `sync_gist_state.py` is the only module that calls the Gist API, so this covers every in-process caller. Verified as described above.
- **`test_gist_config.py:17-42`** (`test_missing_gist_id_is_fatal`): the test used to delete `GIST_ID` from the real `config/local_settings.json`, run the real `sync_gist_state.py upload` and restore the file. It now runs the script with an empty stand-in for the settings module, so the real config is neither read nor rewritten. The assertion that carried a literal Gist id now checks for any 32-hex id instead.
- **`test_custom_releases_collector.py:15-16`**: the test added in `v0.7.61` loaded the real settings module for its token; it now gets an empty stand-in.
- **`digest/homebrew.py:54-56`** (`limit_to_sentences`): the cut point is the last punctuation mark followed by whitespace, not the last dot. Case added to `test_homebrew_digest_formatting.py::test_limit_to_sentences`; checked on the real rows that were cut mid-token.
- **Gist (production state; with the user's approval)**: one write, revision `9ec222a` at 15:36:09Z. It re-added the two dropped entries to a fresh copy of the Gist's `manual_releases.json` (278 → 280 rows). The NFS Underground 2 description was shortened to 211 characters, which `sanitize_digest_description` leaves unchanged. The same write restored `eshop_active_showcase.json`, `eshop_posted_deals.json` and `last_eshop_deals_run.json` from revision `389ee81` (12:58:27Z), the last revision before the test runs: 30 showcase cards, 134 history entries, last run 07:10Z. The write ran only after checking that the Gist head was still the server's 15:30:24Z revision and that the eShop files still held exactly the test-run content. Afterwards every file was re-read and matched the expected content. The local `data/manual_releases.json` was replaced with the Gist copy, so a later download merge cannot bring back the long description or the older dates; the previous local copy is kept as a backup outside the repository. A read-only watcher checks the entries after the 16:00Z server cycle.
- **`plan.md`**: the `v0.7.61` plan said the changes were not committed; corrected to name the commit.
- **`CHANGELOG.md`, `task.md`, `plan.md`, `walkthrough.md`**: `v0.7.62` entries for the items above.

### 3. Blockers / Handoff Items (Crucial)

- [ ] **`sync_gist_state.py:240-256`** (upload merge of `manual_releases.json`): the merge keeps local rows only, so any writer whose copy predates another writer's upload silently deletes that upload. This is what removed the two entries above. Decide and implement a rule that cannot lose a queued row, for example keeping Gist-only rows that are still `processed: false`, and cover it with a test in `test_gist_config.py::test_merge_manual_releases_download_and_upload`. The download merge at `:211-238` has the mirror problem: local fields always win, so a stale machine never accepts newer values.
- [ ] **`collect_custom_releases.py:282-288`, `:109-131` with `:305-314`, `:250-252`**: three places read a failure as an empty result. A failed repository listing still records the author, so a new author's 21-day backfill is lost for good; a non-404 error from `releases/latest` produces a placeholder `v1.0.0` row that then blocks the real release; an unparsable `manual_releases.json` becomes `[]` and the file is rewritten with only the new rows. Make each abort or skip instead, the way a failed Gist download already does, and add a test per case to `test_custom_releases_collector.py`.
- [ ] **`collect_custom_releases.py:21-42`** (`run_gist_sync`): the collector syncs all 24 state files although it uses two. Its download rewrites `last_entry.txt` that `main.py` advanced earlier in the same job, and it bypasses the runner's `--exclude-eshop-state`. Pass `manual_releases.json` and `custom_releases_state.json` explicitly. `CHANGELOG.md` records that the full upload was once made unconditional on purpose, so confirm with the user that nothing relies on it.

### 4. Recommendations & Code Quality Improvements (Optional/Minor)

- [ ] **Gist id in a public repository**: the production Gist id was a literal in `test_gist_config.py` and is still in the git history. A secret Gist is readable by anyone who has its id, and this one holds subscription and wishlist files with Telegram ids. Moving the state to a new Gist is the only real remedy; this is the user's decision.
- [ ] **Production `eshop_posted_deals.json`**: the Gist copy contains fixture rows from earlier test runs (for example `title_gamec`), and the union merge has carried them into production state. Remove them from the server copy; with the guard in place no new ones will arrive.
- [ ] **First `aks796` pass**: the 21-day window is counted from the first successful run. All 12 ports are inside it only until 2026-10-03T18:57Z; five older ports (`bombsquad_nx`, `infinityblade_nx`, `bse_rebombed_nx`, `abreloaded_nx`, `flappy_bird_nx`) are already outside and will not be announced unless added by hand.
- [ ] **`collect_custom_releases.py:133-147`** (`is_already_added`): two-way substring matching on URLs hides repositories whose URL extends a tracked one (`FPSLocker-Warehouse` behind `FPSLocker`, `nxvk-bench` behind `nxvk`). Compare `owner/repo` slugs.
- [ ] **`collect_homebrew_updates.py:116`** (`is_unprocessed_manual`): two-way `startswith` on names means a pending `Flappy Birds Family (aks796)` suppresses update posts for the tracked `Flappy Bird` while it waits in the queue.
- [ ] **`collect_custom_releases.py:334`**: the LLM reply is stored unvalidated. A reply with `"platform": null` is saved as `null` and breaks `digest/homebrew.py` grouping for every later digest. Validate the types before building the row.
- [ ] **`plan.md` history**: `v0.7.57` replaced the plan wholesale and dropped the only open item of `v0.7.56`, the check of real Telegram messages after the eShop change went live. It is tracked nowhere now; re-open it or close it explicitly.
- [ ] **`.github/workflows/bot_runner.yml:95`**: the collector step has no once-per-day guard although `README.md` describes a 20-hour cooldown. Latent, because the workflow has no scheduled runs.
- [ ] **`requirements.txt`**: the documented verification command is `pytest -n auto`, but `pytest-xdist` is not listed.
- [ ] **`run_custom_collector.bat:4`, `run_custom_collector.sh:5,16`**: the launchers repeat the author list for display only, which is how it drifted in `v0.7.58`. Drop the names from those lines.

### 5. Next Assignment

- **Original goal**: manual release entries added from a dev machine must survive in the bot's shared Gist state while the production bot syncs every 30 minutes, and the custom releases collector must fail safe instead of writing wrong or missing data.
- **Already done**: `v0.7.57`–`v0.7.61` are pushed (`48a456d`): `aks796` is monitored and its five build-infrastructure repositories are skipped. The reviewer changes in section 2 (`v0.7.62`) isolate the tests from the Gist and from live `data/`, fix the description cut, and restore the two dropped entries and the eShop state in the Gist.
- **Required**: the three items in section 3, in that order; each needs a test.
- **Do not touch**: the `conftest.py` guard — never remove or bypass it, and do not run a test that reaches the Gist; the LLM prompt and the name-marker safeguard in `collect_custom_releases.py`; the eShop rotation logic; `data/` and the remote Gist.
- Update `walkthrough.md` and `audit.md`, run `graphify update`, re-submit for review.
