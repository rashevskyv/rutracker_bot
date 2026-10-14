import sys

import pytest
import add_release as ar


@pytest.mark.parametrize("platform,dry,expected", [("Switch", False, 1), ("Switch", True, 0), ("PSVita", False, 0)])
def test_existing_release_repairs_store_without_requeue(monkeypatch, platform, dry, expected):
    url = "https://github.com/owner/game"
    row = {"release_url": url, "version": "v1", "app_name": "Game"}
    monkeypatch.setattr(sys, "argv", ["add_release.py", url, "--platform", platform] + (["--dry-run"] if dry else []))
    monkeypatch.setattr(ar.sgs, "resolve_gist_credentials", lambda: ("fake", "fake", None))
    monkeypatch.setattr(ar, "read_gist", lambda *a: ([row], []))
    monkeypatch.setattr(ar, "build_row", lambda *a: row)
    monkeypatch.setattr(ar, "write_inbox", lambda *a: pytest.fail("Existing releases must not be requeued"))
    synced = []
    monkeypatch.setattr(ar.store_manual, "sync_release", lambda u: synced.append(u) or "ok")
    ar.main()
    assert synced == [url] * expected
