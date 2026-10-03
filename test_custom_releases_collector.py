"""Custom releases collector: build-infrastructure repos are never queued, and a failed GitHub request,
an unreadable registry or a malformed LLM reply never becomes a wrong row, a lost backfill or a truncated registry."""
import json
import os
import sys
import types
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

import collect_custom_releases as ccr

NOW = datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def tag_url(repo):
    return f"https://github.com/aks796/{repo}/releases/tag/1.0.0"


def queued(tmp_path):
    path = tmp_path / "manual_releases.json"
    return [row["release_url"] for row in json.loads(path.read_text(encoding="utf-8"))] if path.exists() else []


@pytest.fixture
def run_main(monkeypatch, tmp_path):
    """main() with the settings, Gist sync, GitHub API and LLM faked; returns (saved state or None, sync actions)."""
    syncs = []
    # main() reads its GitHub token from the settings module; give it an empty one instead of the real config.
    monkeypatch.setitem(sys.modules, "core.settings_loader", types.SimpleNamespace(settings={}))
    monkeypatch.setattr(ccr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ccr, "MANUAL_RELEASES_FILE", str(tmp_path / "manual_releases.json"))
    monkeypatch.setattr(ccr, "CUSTOM_RELEASES_STATE_FILE", str(tmp_path / "custom_releases_state.json"))
    monkeypatch.setattr(ccr, "TARGET_USERS", ["aks796"])
    monkeypatch.setattr(ccr, "run_gist_sync", lambda action: syncs.append(action) or True)
    monkeypatch.setattr(ccr, "analyze_repo_with_gemini", lambda name, *args: {"is_switch_homebrew": True, "app_name": name})

    def run(repo_names, failing_release=None, published=NOW):
        monkeypatch.setattr(ccr, "fetch_user_repos", lambda username, token=None: None if repo_names is None else [
            {"name": name, "html_url": f"https://github.com/{username}/{name}", "description": None} for name in repo_names
        ])

        def release(owner, repo, token=None):
            if repo == failing_release:
                raise urllib.error.URLError("timed out")
            return {"tag_name": "1.0.0", "html_url": f"https://github.com/{owner}/{repo}/releases/tag/1.0.0",
                    "published_at": iso(published)}

        monkeypatch.setattr(ccr, "fetch_latest_release", release)
        ccr.main()
        state_path = tmp_path / "custom_releases_state.json"
        return (json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None), syncs

    return run


def test_skip_repos_are_never_queued(run_main, tmp_path):
    # libnx32 is in SKIP_REPOS although its name marker would force-accept it past the LLM verdict.
    run_main(["libnx32", "sonic_allstars_nx"])
    assert queued(tmp_path) == [tag_url("sonic_allstars_nx")]


def test_failed_listing_keeps_a_new_author_new(run_main):
    state, _ = run_main(None)
    assert "aks796" not in state["authors"]  # so the next run still gets the 21-day backfill


def test_failed_release_lookup_skips_the_repo_and_retries_the_author(run_main, tmp_path):
    state, _ = run_main(["sonic_allstars_nx", "pvz_touch_nx"], failing_release="pvz_touch_nx")
    assert queued(tmp_path) == [tag_url("sonic_allstars_nx")]  # no placeholder row for pvz_touch_nx
    assert "aks796" not in state["authors"]


def test_existing_author_cutoff_is_their_own_last_complete_check(run_main, tmp_path):
    # An earlier run failed for aks796, so their last_checked lags behind the global last_run.
    (tmp_path / "custom_releases_state.json").write_text(json.dumps({
        "last_run": iso(NOW - timedelta(hours=1)),
        "authors": {"aks796": {"first_seen": iso(NOW - timedelta(days=30)), "last_checked": iso(NOW - timedelta(days=10))}},
    }), encoding="utf-8")
    state, _ = run_main(["sonic_allstars_nx"], published=NOW - timedelta(days=5))
    assert queued(tmp_path) == [tag_url("sonic_allstars_nx")]
    assert state["authors"]["aks796"]["last_checked"] > iso(NOW - timedelta(minutes=5))


def test_unreadable_registry_aborts_without_writing(run_main, tmp_path):
    (tmp_path / "manual_releases.json").write_text("[{", encoding="utf-8")
    state, syncs = run_main(["sonic_allstars_nx"])
    assert (tmp_path / "manual_releases.json").read_text(encoding="utf-8") == "[{"
    assert state is None and syncs == ["download"]


def test_llm_nulls_do_not_reach_the_queue(run_main, monkeypatch, tmp_path):
    monkeypatch.setattr(ccr, "analyze_repo_with_gemini", lambda name, *args: {
        "is_switch_homebrew": "false" if name == "webtool" else True, "app_name": None, "platform": None, "description": None,
    })
    run_main(["webtool", "sonic_allstars_nx"])
    rows = json.loads((tmp_path / "manual_releases.json").read_text(encoding="utf-8"))
    assert [(row["app_name"], row["platform"]) for row in rows] == [("sonic_allstars_nx (aks796)", "Switch")]
    assert rows[0]["description"]


def test_already_added_compares_whole_repositories():
    entries = [
        {"release_url": "https://github.com/a/FPSLocker"},
        {"release_url": "https://github.com/a/nxvk/releases/tag/1.0"},
        {"release_url": ""},  # used to match every repository
    ]
    assert ccr.is_already_added(entries, "https://github.com/a/nxvk", "nxvk")
    assert ccr.is_already_added(entries, "https://github.com/A/fpslocker", "fpslocker")
    assert not ccr.is_already_added(entries, "https://github.com/a/FPSLocker-Warehouse", "FPSLocker-Warehouse")
    assert not ccr.is_already_added(entries, "https://github.com/a/nxvk-bench", "nxvk-bench")


def test_gist_sync_only_touches_the_collector_files(monkeypatch):
    calls = []
    monkeypatch.setattr(ccr.subprocess, "run", lambda args, **kwargs: calls.append(args) or types.SimpleNamespace(
        returncode=0, stdout="", stderr=""))
    assert ccr.run_gist_sync("upload")
    assert [os.path.basename(arg) for arg in calls[0][2:]] == ["upload", "manual_releases.json", "custom_releases_state.json"]
