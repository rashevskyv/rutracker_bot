"""Manual releases that are forks (same app name, different repo) must still be
update-checked. Regression guard for the app-name collision filter."""
import json
import os
import tempfile

import collect_homebrew_updates as chu
from collect_homebrew_updates import HomebrewUpdatesCollector


def _run(registry, manual):
    tmp = tempfile.mkdtemp()
    list_path = os.path.join(tmp, "list_hb.json")
    manual_path = os.path.join(tmp, "manual_releases.json")
    json.dump(registry, open(list_path, "w", encoding="utf-8"))
    json.dump(manual, open(manual_path, "w", encoding="utf-8"))

    import services.manual_releases as mr
    orig_file = mr.MANUAL_RELEASES_FILE
    mr.MANUAL_RELEASES_FILE = manual_path
    try:
        c = HomebrewUpdatesCollector(list_path, state_path=os.path.join(tmp, "hb_state.json"))
        return c.load_homebrew_list()
    finally:
        mr.MANUAL_RELEASES_FILE = orig_file


def test():
    registry = [{"app_name": "Atmosphere", "api_url": "https://api.github.com/repos/Atmosphere-NX/Atmosphere",
                 "platform": "Switch"}]
    manual = [
        # fork: same name, different repo -> must be merged
        {"type": "homebrew", "processed": True, "app_name": "Atmosphere", "version": "1.11.2",
         "release_url": "https://github.com/NaGaa95/Atmosphere-Pro/releases/tag/v1.11.2"},
        # same repo as registry -> must be skipped
        {"type": "homebrew", "processed": True, "app_name": "Atmosphere Upstream", "version": "1.9.0",
         "release_url": "https://github.com/Atmosphere-NX/Atmosphere/releases/tag/1.9.0"},
        # not processed yet -> must be skipped
        {"type": "homebrew", "processed": False, "app_name": "Pending",
         "release_url": "https://github.com/foo/pending/releases/tag/v1"},
    ]
    apis = {e.get("api_url", "").lower() for e in _run(registry, manual)}

    assert "https://api.github.com/repos/nagaa95/atmosphere-pro" in apis, "fork dropped by name collision"
    assert sum("atmosphere-nx" in a for a in apis) == 1, "registry repo duplicated"
    assert not any("pending" in a for a in apis), "unprocessed entry merged"
    print("ok")


if __name__ == "__main__":
    test()
