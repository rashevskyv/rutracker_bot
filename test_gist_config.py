"""sync_gist_state must refuse to guess which Gist to write to."""
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).with_name("sync_gist_state.py")


def test_no_hardcoded_gist_id():
    """A 32-hex literal in the source means someone re-added the default."""
    body = SRC.read_text(encoding="utf-8")
    leftovers = re.findall(r"['\"][0-9a-f]{32}['\"]", body)
    assert not leftovers, f"hardcoded gist id back in the source: {leftovers}"


def test_missing_gist_id_is_fatal():
    """No GIST_ID anywhere -> exit 1 with an explanation, never a silent default."""
    env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        # deliberately no GIST_ID / GIST_TOKEN
    }
    # Run the script with an empty stand-in for the settings module, so the real config is never
    # read or rewritten and the upload can never resolve credentials for the production Gist.
    launcher = (
        "import runpy, sys, types\n"
        "stub = types.ModuleType('core.settings_loader')\n"
        "stub.settings = {}\n"
        "sys.modules['core.settings_loader'] = stub\n"
        "sys.argv = [sys.argv[1], 'upload']\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", launcher, str(SRC)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(SRC.parent), env=env,
    )
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    combined = (r.stdout + r.stderr).lower()
    assert "gist_id" in combined, combined[-400:]
    assert not re.search(r"\b[0-9a-f]{32}\b", combined), "a gist id leaked into the output"


def test_normalize_target_files():
    import sync_gist_state
    assert sync_gist_state.normalize_target_files(None) == sync_gist_state.FILES_TO_SYNC
    assert sync_gist_state.normalize_target_files([]) == sync_gist_state.FILES_TO_SYNC
    assert sync_gist_state.normalize_target_files(["manual_releases.json"]) == ["manual_releases.json"]
    assert sync_gist_state.normalize_target_files(["data/manual_releases.json"]) == ["manual_releases.json"]
    assert sync_gist_state.normalize_target_files(["manual_releases"]) == ["manual_releases.json"]
    assert sync_gist_state.normalize_target_files(["last_entry"]) == ["last_entry.txt"]

    excluded = sync_gist_state.normalize_target_files(None, exclude_files=sync_gist_state.ESHOP_STATE_FILES)
    for name in sync_gist_state.ESHOP_STATE_FILES:
        assert name not in excluded
    assert "posted_links.json" in excluded
    assert "eshop_region_prices_cache.json" in excluded


def test_merge_eshop_states():
    import json
    import sync_gist_state

    # 1. Test eshop_active_showcase.json merge (local newer / higher msg_id wins over stale gist)
    local_showcase = {
        "-1001790782971_561344": [
            {"title": "New Deal 1", "message_id": 565315, "posted_at": 1788000000.0},
            {"title": "New Deal 2", "message_id": 565316, "posted_at": 1788000100.0},
        ]
    }
    gist_showcase = {
        "-1001790782971_561344": [
            {"title": "Old Deal", "message_id": 561432, "posted_at": 1787000000.0}
        ]
    }
    merged_sc = sync_gist_state.merge_json_files("eshop_active_showcase.json", json.dumps(local_showcase), json.dumps(gist_showcase))
    parsed_sc = json.loads(merged_sc)
    assert len(parsed_sc["-1001790782971_561344"]) == 2
    assert parsed_sc["-1001790782971_561344"][0]["message_id"] == 565315

    # 2. Test eshop_posted_deals.json merge (union with higher timestamps)
    local_posted = {
        "111": {"title": "Game A", "posted_at": 1000.0},
        "222": {"title": "Game B", "posted_at": 3000.0},
    }
    gist_posted = {
        "111": {"title": "Game A", "posted_at": 2000.0},
        "333": {"title": "Game C", "posted_at": 1500.0},
    }
    merged_pd = sync_gist_state.merge_json_files("eshop_posted_deals.json", json.dumps(local_posted), json.dumps(gist_posted))
    parsed_pd = json.loads(merged_pd)
    assert set(parsed_pd.keys()) == {"111", "222", "333"}
    assert parsed_pd["111"]["posted_at"] == 2000.0
    assert parsed_pd["222"]["posted_at"] == 3000.0
    assert parsed_pd["333"]["posted_at"] == 1500.0

    # 3. Test last_eshop_deals_run.json merge (newer timestamp wins)
    local_run = {"last_run_timestamp": 5000.0, "posted_count": 5}
    gist_run = {"last_run_timestamp": 4000.0, "posted_count": 2}
    merged_run = sync_gist_state.merge_json_files("last_eshop_deals_run.json", json.dumps(local_run), json.dumps(gist_run))
    assert json.loads(merged_run)["last_run_timestamp"] == 5000.0


def test_download_merge_keeps_newer_local_showcase():
    """Simulates digest download: stale Gist must not overwrite newer local showcase."""
    import json
    import tempfile
    from pathlib import Path
    import sync_gist_state

    local = {
        "-1001790782971_561344": [
            {"title": "Fresh", "message_id": 565432, "posted_at": 1788000000.0},
        ]
    }
    stale_gist = {
        "-1001790782971_561344": [
            {"title": "Stale", "message_id": 561432, "posted_at": 1787000000.0},
        ]
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "eshop_active_showcase.json"
        path.write_text(json.dumps(local), encoding="utf-8")
        # Same merge path download_state uses before writing the file.
        merged = sync_gist_state.merge_json_files(
            "eshop_active_showcase.json",
            path.read_text(encoding="utf-8"),
            json.dumps(stale_gist),
        )
        path.write_text(merged, encoding="utf-8")
        got = json.loads(path.read_text(encoding="utf-8"))
        assert got["-1001790782971_561344"][0]["message_id"] == 565432


def test_prune_showcase_to_keys():
    from send_eshop_deals import prune_showcase_to_keys

    data = {
        "-1001790782971_561344": [{"message_id": 1}],
        "-1001277664260_29459": [{"message_id": 2}],
        "-1001738235675_1216": [{"message_id": 3}],
    }
    pruned = prune_showcase_to_keys(data, {"-1001790782971_561344"})
    assert list(pruned.keys()) == ["-1001790782971_561344"]
    assert pruned["-1001790782971_561344"][0]["message_id"] == 1


def test_merge_manual_releases_three_way():
    import json
    import sync_gist_state
    merge = sync_gist_state.merge_manual_releases

    def row(name, processed=False, **extra):
        return {"app_name": name, "version": "1.0", "release_url": f"https://example.com/{name}", "processed": processed, **extra}

    a, b, c = row("A"), row("B", processed=True), row("C")
    base = [a, b]  # the Gist content at this machine's last sync

    # C was queued by another machine after our sync: an upload from our older copy keeps it (lost on 2026-10-02).
    assert merge([a, b], [a, b, c], base) == [a, b, c]
    assert json.loads(sync_gist_state.merge_json_files(
        "manual_releases.json", json.dumps([a, b]), json.dumps([a, b, c]), base=base)) == [a, b, c]
    # Deleted locally and unchanged in the Gist: stays deleted.
    assert merge([a], [a, b], base) == [a]
    # Removed from the Gist (re-versioned by the server) and unchanged locally: not resurrected.
    assert merge([a, b], [a], base) == [a]
    # Unchanged locally and newer in the Gist: the Gist values win; a local edit wins over the Gist.
    b_newer = dict(b, date="2026-10-02")
    assert merge([a, b], [a, b_newer], base) == [a, b_newer]
    a_edited = dict(a, description="edited")
    assert merge([a_edited, b], [a, b], base)[0] == a_edited
    # Processed on either side stays processed.
    assert merge([dict(a, processed=True), b], [a, b], base)[0]["processed"] is True
    # A stale copy with a local edit does not re-queue a row the Gist processed...
    assert merge([dict(a, description="x"), b], [dict(a, processed=True), b], base)[0]["processed"] is True
    # ...but a row re-queued in the Gist is not flipped back by an unchanged local copy.
    assert merge([a, b], [a, dict(b, processed=False)], base)[1]["processed"] is False
    # Without a base nothing counts as deleted, but a processed row the Gist re-versioned is not brought back.
    assert merge([a, c], [a, b], None) == [a, b, c]
    assert merge([a, dict(b, version="0.9")], [a, b], None) == [a, b]


def test_absorb_inbox():
    import sync_gist_state
    absorb = sync_gist_state.absorb_inbox

    def row(name, inbox_id=None, **extra):
        r = {"app_name": name, "version": "1.0", "release_url": f"https://example.com/{name}", "processed": False, **extra}
        return dict(r, inbox_id=inbox_id) if inbox_id else r

    queued, new = row("A", "id-a"), row("B", "id-b")
    # A is already taken (and later re-versioned by the collector, which keeps inbox_id); only B is queued.
    manual = [dict(queued, version="2.0", processed=True)]
    assert absorb(manual, [queued, new]) == manual + [new]
    # Same release as a collector row without inbox_id, or an inbox row without an id: not queued twice.
    assert absorb([row("C")], [row("C", "id-c"), row("D")]) == [row("C")]
    # Inbox rows are always queued as pending.
    assert absorb([], [dict(new, processed=True)])[0]["processed"] is False


def test_catalog_states_in_files_to_sync():
    import sync_gist_state
    for filename in (
        "udb_state.json",
        "fortheusers_state.json",
        "vitadb_state.json",
        "switchports_state.json",
    ):
        assert filename in sync_gist_state.FILES_TO_SYNC


def test_merge_catalog_states():
    import json
    import sync_gist_state

    # 1. udb_state.json: local newer timestamp wins, disjoint keys unioned
    local_udb = {
        "app1": {"version": "1.1", "updated": "2026-08-30T00:00:00Z", "release_url": "https://example.com/1"},
        "local_only": {"version": "1.0", "updated": "2026-08-01T00:00:00Z"},
    }
    gist_udb = {
        "app1": {"version": "1.0", "updated": "2026-08-20T00:00:00Z", "release_url": "https://example.com/1"},
        "gist_only": {"version": "2.0", "updated": "2026-08-15T00:00:00Z"},
    }
    merged_udb = json.loads(sync_gist_state.merge_json_files("udb_state.json", json.dumps(local_udb), json.dumps(gist_udb)))
    assert merged_udb["app1"]["version"] == "1.1"
    assert "local_only" in merged_udb
    assert "gist_only" in merged_udb

    # 2. fortheusers_state.json: parsed DD/MM/YYYY date comparison across month boundary
    # 01/02/2026 is chronologically newer than 31/01/2026, even though "31/01/2026" > "01/02/2026" lexicographically
    local_ftu_newer = {"switch-hb:app": {"version": "1.1", "updated": "01/02/2026"}}
    gist_ftu_older = {"switch-hb:app": {"version": "1.0", "updated": "31/01/2026"}}
    merged_ftu = json.loads(sync_gist_state.merge_json_files("fortheusers_state.json", json.dumps(local_ftu_newer), json.dumps(gist_ftu_older)))
    assert merged_ftu["switch-hb:app"]["version"] == "1.1"

    merged_ftu_b = json.loads(sync_gist_state.merge_json_files("fortheusers_state.json", json.dumps(gist_ftu_older), json.dumps(local_ftu_newer)))
    assert merged_ftu_b["switch-hb:app"]["version"] == "1.1"

    # 3. vitadb_state.json: equal dates, higher version wins
    local_vita = {"vita-hb:10": {"version": "1.5", "date": "2026-05-01"}}
    gist_vita = {"vita-hb:10": {"version": "1.0", "date": "2026-05-01"}}
    merged_vita = json.loads(sync_gist_state.merge_json_files("vitadb_state.json", json.dumps(local_vita), json.dumps(gist_vita)))
    assert merged_vita["vita-hb:10"]["version"] == "1.5"

    # 4. switchports_state.json: preserves newer last_updated
    local_sp = {"test/game": {"game_name": "Game", "version": "1.0", "last_updated": "2026-01-01"}}
    gist_sp = {"test/game": {"game_name": "Game", "version": "1.1", "last_updated": "2026-02-01"}}
    merged_sp = json.loads(sync_gist_state.merge_json_files("switchports_state.json", json.dumps(local_sp), json.dumps(gist_sp)))
    assert merged_sp["test/game"]["version"] == "1.1"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  {name} ok")
    print("gist config ok")

