"""Phase 1e SwitchPorts: Emu Radar Store source, README fallback, and first-run/upgrade behaviour. No network."""
import json
import logging
import os
import tempfile
from unittest.mock import patch

import pytest

from collect_homebrew_updates import (
    HomebrewUpdatesCollector,
    STORE_CATALOG_URL,
    STORE_REPO_URL,
    SWITCHPORTS_REPO_URL,
)
from digest.homebrew import homebrew_digest_manager


README_ANDROID = """# SwitchPorts
### Android
| Game | Version | Last Updated | Link | GBATemp | Instructions |
| --- | --- | --- | --- | --- | --- |
| Mario Port | 1.0 | 01/03/2026 | [test/mario](https://github.com/test/mario) | [Link](https://gbatemp.net/1) | ??? |
| Luigi Port | 1.0 | 02/03/2026 | [test/luigi](https://github.com/test/luigi) | | ??? |
"""

# Emulator table: the README parser reads its columns by position, so this row gets the legacy key '3ds'.
README_EMULATORS = """
### Emulators
| System | Title | Version | Last Updated? | Link | GBATemp Thread? | Instructions accurate? |
| --- | --- | --- | --- | --- | --- | --- |
| 3DS | Dekopon | 2.0.0 | 28/07/2026 | [PalindromicBreadLoaf/dekopon](https://github.com/PalindromicBreadLoaf/dekopon) | [Link](https://gbatemp.net/2) | ??? |
"""


def catalog_json(mario_version="1.0", include_luigi=True):
    entries = [
        {"name": "dekopon", "title": "Dekopon", "repo": "PalindromicBreadLoaf/dekopon", "section": "Emulators", "version_hint": "2.0.0"},
        {"name": "mario", "title": "Mario Port", "repo": "test/mario", "section": "Android", "version_hint": mario_version},
    ]
    if include_luigi:
        entries.append({"name": "luigi", "title": "Luigi Port", "repo": "test/luigi", "section": "Android", "version_hint": "1.0"})
    return json.dumps({"source": "x", "rows_without_github_link": 0, "duplicate_rows": 0, "entries": entries})


def repo_json(mario_updated="01/03/2026"):
    return json.dumps({"packages": [
        {"name": "dekopon", "url": "https://github.com/PalindromicBreadLoaf/dekopon", "version": "2.0.0", "updated": "28/07/2026"},
        {"name": "mario", "url": "https://github.com/test/mario", "version": "1.0", "updated": mario_updated},
    ]})


class Resp:
    def __init__(self, status=200, text=""):
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        return self._text


class Session:
    def __init__(self):
        self.routes = {}
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.routes.get(url, Resp(404))


def serve_store(session, mario_version="1.0", include_luigi=True, mario_updated="01/03/2026"):
    session.routes[STORE_CATALOG_URL] = Resp(200, catalog_json(mario_version, include_luigi))
    session.routes[STORE_REPO_URL] = Resp(200, repo_json(mario_updated))


def serve_readme(session, text=README_ANDROID):
    session.routes[SWITCHPORTS_REPO_URL] = Resp(200, text)


@pytest.fixture
def collector():
    tmp = tempfile.mkdtemp()
    list_path = os.path.join(tmp, "list_hb.json")
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    c = HomebrewUpdatesCollector(
        list_path=list_path,
        state_path=os.path.join(tmp, "hb_state.json"),
        switchports_state_path=os.path.join(tmp, "switchports_state.json"),
    )
    c.session = Session()
    c.unprocessed_manual_names = set()
    c._switchports_state = {}

    async def fake_desc(*a, **kw):
        return "Mock description"

    c._get_description_cached = fake_desc
    return c


@pytest.fixture
def no_manual_rows():
    with patch("services.manual_releases.load_manual_releases", return_value=[]):
        yield


def test_catalog_parser_accepts_valid_and_rejects_broken(collector):
    entries = HomebrewUpdatesCollector._parse_store_catalog(catalog_json())
    assert [e["repo"] for e in entries] == ["PalindromicBreadLoaf/dekopon", "test/mario", "test/luigi"]
    assert entries[1] == {"repo": "test/mario", "title": "Mario Port", "version_hint": "1.0"}
    for bad in ["", "not json", '{"entries": []}', '{"entries": [{"repo": "nope"}]}', '{"entries": [{"repo": "a/b/c"}]}', "[]"]:
        assert HomebrewUpdatesCollector._parse_store_catalog(bad) is None, bad


def test_repo_dates_keyed_by_lowercase_slug(collector):
    dates = collector._parse_store_repo_dates(repo_json())
    assert dates == {"palindromicbreadloaf/dekopon": "28/07/2026", "test/mario": "01/03/2026"}
    assert collector._parse_store_repo_dates("garbage") == {}


async def test_first_run_seeds_silently_and_covers_catalog(collector, no_manual_rows):
    serve_store(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        covered = await collector.collect_switchports_updates([])
    assert add.call_count == 0
    assert covered == {"palindromicbreadloaf/dekopon", "test/mario", "test/luigi"}
    assert set(collector._switchports_state) == covered
    assert all(v["source"] == "store" for v in collector._switchports_state.values())


async def test_upgrade_from_readme_state_does_not_reannounce(collector, no_manual_rows):
    # Old state written by the README path, with its own keys (the emulator row got key '3ds').
    serve_readme(collector.session, README_ANDROID + README_EMULATORS)
    collector.session.routes[STORE_CATALOG_URL] = Resp(500)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        await collector.collect_switchports_updates([])
    assert "test/mario" in collector._switchports_state
    assert "3ds" in collector._switchports_state

    # First run after the change: store is up, nothing changed in the README.
    serve_store(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        covered = await collector.collect_switchports_updates([])
    assert add.call_count == 0
    assert "palindromicbreadloaf/dekopon" in covered
    assert collector._switchports_state["test/mario"]["source"] == "store"
    assert collector._switchports_state["test/mario"]["updated"] == "01/03/2026"


async def test_version_bump_announces_once_as_update(collector, no_manual_rows):
    serve_store(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry"):
        await collector.collect_switchports_updates([])  # baseline

    serve_store(collector.session, mario_version="1.1")
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        await collector.collect_switchports_updates([])
        assert add.call_count == 1
        _, kw = add.call_args
        assert kw["app_name"] == "Mario Port (Port)"
        assert kw["version"] == "1.1"
        assert kw["is_new"] is False
        assert kw["release_url"] == "https://github.com/test/mario"
    assert collector._switchports_state["test/mario"]["version"] == "1.1"


async def test_release_date_change_announces_update(collector, no_manual_rows):
    serve_store(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry"):
        await collector.collect_switchports_updates([])

    serve_store(collector.session, mario_updated="05/10/2026")
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        await collector.collect_switchports_updates([])
    assert add.call_count == 1
    assert add.call_args.kwargs["is_new"] is False


async def test_new_catalog_entry_after_baseline_announced_as_new(collector, no_manual_rows):
    serve_store(collector.session, include_luigi=False)
    with patch.object(homebrew_digest_manager, "add_entry"):
        await collector.collect_switchports_updates([])

    serve_store(collector.session, include_luigi=True)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        await collector.collect_switchports_updates([])
    assert add.call_count == 1
    assert add.call_args.kwargs["app_name"] == "Luigi Port (Port)"
    assert add.call_args.kwargs["is_new"] is True


async def test_pending_manual_release_suppresses_new_entry(collector, no_manual_rows):
    serve_store(collector.session, include_luigi=False)
    with patch.object(homebrew_digest_manager, "add_entry"):
        await collector.collect_switchports_updates([])

    collector.unprocessed_manual_names = {"Luigi Port"}
    serve_store(collector.session, include_luigi=True)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        covered = await collector.collect_switchports_updates([])
    assert add.call_count == 0
    assert "test/luigi" in covered and "test/luigi" in collector._switchports_state


async def test_store_outage_falls_back_to_readme_and_warns(collector, no_manual_rows, caplog):
    serve_store(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry"):
        await collector.collect_switchports_updates([])

    collector.session.routes[STORE_CATALOG_URL] = Resp(503)
    serve_readme(collector.session, README_ANDROID.replace("| Mario Port | 1.0 |", "| Mario Port | 1.2 |"))
    with caplog.at_level(logging.WARNING), patch.object(homebrew_digest_manager, "add_entry") as add:
        covered = await collector.collect_switchports_updates([])
    assert SWITCHPORTS_REPO_URL in collector.session.urls
    assert "falling back to README" in caplog.text
    assert add.call_count == 1
    assert add.call_args.kwargs["version"] == "1.2"
    assert "test/mario" in covered


async def test_invalid_store_json_falls_back(collector, no_manual_rows):
    collector.session.routes[STORE_CATALOG_URL] = Resp(200, "<html>maintenance</html>")
    serve_readme(collector.session)
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        covered = await collector.collect_switchports_updates([])
    assert add.call_count == 0
    assert SWITCHPORTS_REPO_URL in collector.session.urls
    assert "test/mario" in covered


async def test_flip_flop_between_store_and_readme_is_silent(collector, no_manual_rows):
    serve_store(collector.session)
    serve_readme(collector.session)
    collector.session.routes[STORE_CATALOG_URL] = Resp(200, catalog_json("1.0"))
    with patch.object(homebrew_digest_manager, "add_entry") as add:
        await collector.collect_switchports_updates([])          # store seeds
        collector.session.routes[STORE_CATALOG_URL] = Resp(500)
        await collector.collect_switchports_updates([])          # README day, same versions
        collector.session.routes[STORE_CATALOG_URL] = Resp(200, catalog_json("1.0"))
        await collector.collect_switchports_updates([])          # store again
    assert add.call_count == 0
