## Senior Audit Report

### Status: APPROVED

### 1. Summary of Review

Scope: the unpushed range `origin/main` (`d2f4346`) .. `1522b6f`, i.e. `v0.7.57`–`v0.7.60`, plus the reviewer changes that ship as `v0.7.61`. `v0.7.59` and `v0.7.60` were committed while this review was already running, so the review was extended to cover them.

The submitted work is small and does what `task.md` and `plan.md` asked. `v0.7.58` adds `aks796` to `TARGET_USERS` in `collect_custom_releases.py` (one line). `v0.7.57`, `v0.7.59` and `v0.7.60` are data tasks: one manual release entry each in the gitignored, Gist-synced `data/manual_releases.json`, with only documentation in git. Every commit touched only the files its plan declared, and nothing speculative was added.

What the reviewer ran:

- `python -m pytest -n auto -q` (Windows, Python 3.14.3, pytest 9.1.1, xdist 3.8.0): 109 passed on the submitted range, 110 passed after the reviewer changes. No existing test imported `collect_custom_releases.py`, so the green suite did not exercise the `v0.7.58` change on its own; that change was verified by the checks below.
- `py_compile` plus an AST check of `TARGET_USERS` on Windows and on WSL Python 3.12.3: six authors, no duplicates, one loop over the list.
- GitHub API, read-only: `aks796` exists with that exact login casing and has 22 public repositories; `antoxa2584x/nfsu2-sw` latest release is `v0.3.5`, published `2026-10-01T20:48:37Z`; `corax89/noJMe` has no releases or tags, head commit `6da353a` dated `2026-10-01T14:41:45Z`, and its README names `switchui` as the Switch version.
- Gist, one read-only GET: remote `manual_releases.json` is identical to the local file (280 entries), with exactly one `noJMe` entry and one NFS Underground 2 entry, both `processed: false`. Remote `custom_releases_state.json` has no `aks796` key, so the first collector run treats the author as new and uses the 21-day window.
- A read-only dry run of the first collector pass for `aks796`, reusing the collector's own functions with no LLM calls and no writes: 17 of 22 repositories pass dedup and the cutoff, and 5 of those are build infrastructure rather than end-user releases.
- `git diff --check`: clean for `v0.7.58`–`v0.7.60`; `v0.7.57` left a blank line at the end of `walkthrough.md` (fixed below).

Every walkthrough claim that was spot-checked held: the repository count, the 21-day first pass, the release metadata, the Gist entry counts and the `processed` flags.

Two process notes. The range was committed before review, and two commits landed in the same working tree during the review. A separate automated `/code-review` pass over the range was started at the user's request and had not returned when the user asked for the commit and push; this verdict rests on the checks listed above, and any finding from that pass is to be recorded as a follow-up.

### 2. Fixes Applied by Reviewer

- **`README.md:56`, `GEMINI.md:150`, `run_custom_collector.bat:4`, `run_custom_collector.sh:5,16`**: the tracked-author lists still named five authors after `v0.7.58` added the sixth. Earlier author additions (`f1c0657`, `53ce04f`) updated these lists in the same commit. Added `aks796`. Verified with a script asserting that each list equals `TARGET_USERS`, with `bash -n run_custom_collector.sh`, and with the full suite.
- **`walkthrough.md` (end of file)**: removed the trailing blank line introduced by `v0.7.57`; `git diff --check origin/main` now passes.
- **`collect_custom_releases.py:16-18,299-300`**: at the user's direct request, after seeing the dry-run projection, added `SKIP_REPOS` and a check at the top of the repository loop so `aks796/android32`, `libnx32`, `mesa-switch32`, `mesa32` and `ffmpeg32` are never queued. Name markers (`libnx`, `-switch`) force-accept two of them past the LLM verdict, so the filter alone would not have excluded them. The first run now queues the 12 game ports only.
- **`test_custom_releases_collector.py`** (new): runs `main()` with the network, Gist sync and LLM patched out and asserts that `libnx32` is skipped while `sonic_allstars_nx` is queued. Confirmed that the test fails when `SKIP_REPOS` is emptied.
- **`README.md:60`, `GEMINI.md:156`**: documented `SKIP_REPOS`.
- **`CHANGELOG.md`, `task.md`, `plan.md`, `walkthrough.md`**: added the `v0.7.61` entries describing the items above.
- **`graphify-out/`**: ran `graphify update .` after the code change; the graph was rebuilt (1062 nodes, 2101 edges) from the working tree that became `v0.7.61`.

### 3. Blockers / Handoff Items (Crucial)

None.

### 4. Recommendations & Code Quality Improvements (Optional/Minor)

- [ ] **`collect_custom_releases.py:282-288`**: when `fetch_user_repos` fails on an author's first run, the author is still written to `authors_state`. The next run then treats the author as existing and uses `last_run` as the cutoff, so the 21-day backfill is lost for good. Record the author only after a successful fetch.
- [ ] **`collect_custom_releases.py:109-131,305-314`**: `fetch_latest_release` returns `None` for any HTTP error, and the caller reads `None` as "no release", falling back to `pushed_at` with the placeholder version `v1.0.0` and the bare repository URL. Under rate limiting this queues a wrong entry that also blocks the real release through `is_already_added`. Reproduced in the unauthenticated dry run (HTTP 403 on the 23rd call). Treat only 404 as "no release" and skip the repository on other errors.
- [ ] **`run_custom_collector.bat:4`, `run_custom_collector.sh:5,16`**: the launchers repeat the author list for display only, which is how it drifted. Drop the names from those lines; the collector already prints each author as it processes them.
- [ ] **`graphify-out/`**: `graphify update` reported 83 communities against 76 saved labels; run `graphify label` to refresh the names.

### 5. Next Assignment

- **Original goal**: ship the unpushed work on `rutracker_bot` — three manual release entries synced to the Gist (`v0.7.57`, `v0.7.59`, `v0.7.60`) and `aks796` added to the custom releases collector's monitored authors (`v0.7.58`).
- **Already done**: all of the above, verified as listed in section 1, plus the reviewer changes in section 2 (`v0.7.61`).
- **Required**: nothing. There are no handoff items.
- **Do not touch**: `data/` and the remote Gist, which hold the authoritative state; the LLM prompt and the name-marker safeguard in `collect_custom_releases.py`, unless a new task asks for it.
- If a section 4 item is taken up: update `walkthrough.md` and `audit.md`, run `graphify update`, re-submit for review.
