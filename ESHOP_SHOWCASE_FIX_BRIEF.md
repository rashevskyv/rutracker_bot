# eShop Showcase — hardening status (after manual orphan cleanup)

**Date:** 2026-08-29  
**Goal:** After you manually delete old duplicate batches, daily cron must never recreate that mess.

---

## Guarantees now in code (v0.7.45)

- After every showcase mutation, eShop state is **force-uploaded to Gist**.
- Digest/rt/hb gist sync **excludes** Live Showcase files (`--exclude-eshop-state`).
- Gist **download merges** JSON; newer local showcase cannot be overwritten by stale Gist.

## Guarantees from v0.7.44 (still in force)

1. **Rotation = live discount check**, not Top-30 snapshot.
2. **Delete failed ⇒ keep tracking** (`message can't be deleted` is failure). Slot is not freed → no extra posts → no new orphan stacks.
3. **Only vacated slots are refilled**; full valid showcase → **0 posts** even with `--force`.
4. **Hard cap** while posting: never exceed `max_active_showcase`.
5. **Atomic writes** of showcase / posted history / last_run under absolute `PROJECT_ROOT/data`.
6. **Gist merge** prefers newer local showcase (higher `message_id` / newer `posted_at`).
7. **Diagnostics** at every run: path, mtime, count, first/last msg_id.
8. Tests: **37 passed** including failed-delete / full-showcase / persistence / gist merge.

---

## What you do manually

1. Delete remaining old duplicate cards in topic 561344 (the ones bot cannot delete).
2. Deploy this hardened `send_eshop_deals.py` (+ `sync_gist_state.py`, tests) to `/root/rutracker_bot`.
3. Ensure `data/eshop_active_showcase.json` lists exactly the **current** 30 `message_id`s that remain in Telegram.
4. If one slot is missing (e.g. Persona 5 Royal `565315` was removed):  
   `python send_eshop_deals.py --force` once → should post **only** the missing count.  
5. Immediately: `python send_eshop_deals.py --force` again → must post **0**.  
6. Next morning cron with `--force` should again post **0** unless some sales truly ended.

---

## Success criteria tomorrow

Log must look like:

```text
[SHOWCASE DIAGNOSTIC] ... Count: 30 | First msg_id: <current> | Last msg_id: <current>
Checking 30 active showcase deals ... for discount expiration...
Showcase ...: 30 active, 0 slot(s) available
No new deals needed.
Posted 0 deal(s).
```

Not:

```text
Diff: 0 keep, 20 delete, 30 add
```

(that old Snapshot Diff path is gone).
