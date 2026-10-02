"""Repositories listed in SKIP_REPOS (build infrastructure) must never be queued, even when
their name carries a Switch marker that would otherwise override the LLM verdict."""
import json
import sys
import types
from datetime import datetime, timezone

import collect_custom_releases as ccr


def test_skip_repos_are_never_queued(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manual_path = tmp_path / "manual_releases.json"

    # main() reads its GitHub token from the settings module; give it an empty one instead of the real config.
    monkeypatch.setitem(sys.modules, "core.settings_loader", types.SimpleNamespace(settings={}))
    monkeypatch.setattr(ccr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ccr, "MANUAL_RELEASES_FILE", str(manual_path))
    monkeypatch.setattr(ccr, "CUSTOM_RELEASES_STATE_FILE", str(tmp_path / "custom_releases_state.json"))
    monkeypatch.setattr(ccr, "TARGET_USERS", ["aks796"])
    monkeypatch.setattr(ccr, "run_gist_sync", lambda action: True)
    monkeypatch.setattr(ccr, "fetch_user_repos", lambda username, token=None: [
        {"name": name, "html_url": f"https://github.com/{username}/{name}", "description": None}
        for name in ("libnx32", "sonic_allstars_nx")
    ])
    monkeypatch.setattr(ccr, "fetch_latest_release", lambda owner, repo, token=None: {
        "tag_name": "1.0.0", "html_url": f"https://github.com/{owner}/{repo}/releases/tag/1.0.0", "published_at": now,
    })
    monkeypatch.setattr(ccr, "analyze_repo_with_gemini", lambda name, *args: {"is_switch_homebrew": True, "app_name": name})

    ccr.main()

    queued = [entry["release_url"] for entry in json.loads(manual_path.read_text(encoding="utf-8"))]
    assert queued == ["https://github.com/aks796/sonic_allstars_nx/releases/tag/1.0.0"]
