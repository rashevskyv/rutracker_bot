"""A manual release is marked processed only once its entry is in the digest data that was sent."""
import json

import services.manual_releases as mr


def test_marks_only_rows_in_the_digest(tmp_path, monkeypatch):
    path = tmp_path / "manual_releases.json"
    monkeypatch.setattr(mr, "MANUAL_RELEASES_FILE", str(path))
    rows = [
        {"type": "homebrew", "app_name": "Sent", "release_url": "https://x/sent", "processed": False},
        {"type": "homebrew", "app_name": "Lost", "release_url": "https://x/lost", "processed": False},
        {"type": "game", "title": "Game", "url": "https://x/sent", "processed": False},
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")

    assert mr.mark_manual_releases_published("homebrew", {"https://x/sent"}) == 1
    after = {r.get("app_name") or r.get("title"): r["processed"] for r in json.loads(path.read_text(encoding="utf-8"))}
    # "Lost" never reached the digest data (2026-10-03): it stays pending for the next digest.
    assert after == {"Sent": True, "Lost": False, "Game": False}
