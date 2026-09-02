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
    local_cfg = SRC.parent / "config" / "local_settings.json"
    original_content = None
    if local_cfg.exists():
        original_content = local_cfg.read_text(encoding="utf-8")
        try:
            cfg_dict = __import__("json").loads(original_content)
            if "GIST_ID" in cfg_dict:
                del cfg_dict["GIST_ID"]
                local_cfg.write_text(__import__("json").dumps(cfg_dict), encoding="utf-8")
        except Exception:
            pass

    try:
        r = subprocess.run(
            [sys.executable, str(SRC), "upload"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(SRC.parent), env=env,
        )
        assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
        combined = (r.stdout + r.stderr).lower()
        assert "gist_id" in combined, combined[-400:]
        assert "46128fc489e0fd60e226ff26dc638e97" not in combined
    finally:
        if original_content is not None:
            local_cfg.write_text(original_content, encoding="utf-8")


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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  {name} ok")
    print("gist config ok")

