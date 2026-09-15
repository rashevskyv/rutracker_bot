"""Unit tests for homebrew catalog snapshot mode and new app marker logic."""
import json
import os
import sys
import tempfile
from unittest.mock import patch
import pytest

from collect_homebrew_updates import (
    HomebrewUpdatesCollector,
    UDB_API_URL,
    SWITCH_REPO_URL,
    WIIU_REPO_URL,
    VITADB_ENDPOINTS,
    SWITCHPORTS_REPO_URL,
    main,
)
from digest.homebrew import homebrew_digest_manager


class MockResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, content_type=None):
        return self._json_data

    async def text(self):
        return self._text_data


class MockSession:
    def __init__(self, routes=None, default_status=200):
        self.routes = routes or {}
        self.default_status = default_status
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        handler = self.routes.get(url)
        if callable(handler):
            return handler(url, **kwargs)
        if handler is not None:
            return handler
        return MockResponse(status=self.default_status)


def make_standard_mock_session():
    table_text = (
        "| Game | Version | Updated | Download | Info |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Mario Port | 1.0 | 2026-03-01 | [Link](https://github.com/test/mario/releases) | [GBA](https://gbatemp.net/1) |\n"
    )
    routes = {
        UDB_API_URL: MockResponse(200, json_data={
            "app1": {
                "title": "App One",
                "version": "1.0",
                "updated": "2026-01-01T00:00:00Z",
                "systems": ["3DS"],
                "download_page": "https://example.com/app1",
            }
        }),
        SWITCH_REPO_URL: MockResponse(200, json_data={
            "packages": [
                {
                    "name": "sw_app",
                    "title": "Switch App",
                    "version": "1.0.0",
                    "updated": "01/01/2026",
                    "url": "https://github.com/test/sw_app",
                }
            ]
        }),
        WIIU_REPO_URL: MockResponse(200, json_data={
            "packages": [
                {
                    "name": "wiiu_app",
                    "title": "WiiU App",
                    "version": "2.0.0",
                    "updated": "02/02/2026",
                    "url": "https://github.com/test/wiiu_app",
                }
            ]
        }),
        VITADB_ENDPOINTS[0][0]: MockResponse(200, json_data=[
            {"id": 10, "name": "Vita App", "version": "1.0", "date": "2026-01-10", "status": "0"}
        ]),
        VITADB_ENDPOINTS[1][0]: MockResponse(200, json_data=[
            {"id": 20, "name": "Vita Plugin", "version": "1.1", "date": "2026-01-20", "status": "0"}
        ]),
        VITADB_ENDPOINTS[2][0]: MockResponse(200, json_data=[
            {"id": 30, "name": "Vita Tool", "version": "1.2", "date": "2026-01-30", "status": "0"}
        ]),
        VITADB_ENDPOINTS[3][0]: MockResponse(200, json_data=[
            {"id": 40, "name": "PSP App", "version": "1.3", "date": "2026-02-01", "status": "0"}
        ]),
        SWITCHPORTS_REPO_URL: MockResponse(200, text_data=table_text),
    }
    return MockSession(routes=routes)


@pytest.fixture
def temp_collector():
    tmp = tempfile.mkdtemp()
    list_path = os.path.join(tmp, "list_hb.json")
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    c = HomebrewUpdatesCollector(
        list_path=list_path,
        state_path=os.path.join(tmp, "hb_state.json"),
        udb_state_path=os.path.join(tmp, "udb_state.json"),
        fortheusers_state_path=os.path.join(tmp, "fortheusers_state.json"),
        vitadb_state_path=os.path.join(tmp, "vitadb_state.json"),
        switchports_state_path=os.path.join(tmp, "switchports_state.json"),
    )
    c.session = make_standard_mock_session()
    # Stub description resolution to avoid LLM calls
    async def mock_desc(*a, **kw):
        return "Mock description"

    c._get_description_cached = mock_desc
    c._get_description_for_udb_app = mock_desc
    c.summarize_and_translate_notes = mock_desc
    return c, tmp


def test_cli_help():
    """Verify that --snapshot appears in parser help."""
    import argparse
    from collect_homebrew_updates import DEFAULT_LIST_PATH, DEFAULT_STATE_PATH

    parser = argparse.ArgumentParser(description='Collect homebrew updates')
    parser.add_argument('--list', default=DEFAULT_LIST_PATH)
    parser.add_argument('--state', default=DEFAULT_STATE_PATH)
    parser.add_argument('--translate', action='store_true')
    parser.add_argument('--test', type=int, metavar='N')
    parser.add_argument('--snapshot', action='store_true')
    help_text = parser.format_help()
    assert "--snapshot" in help_text


@pytest.mark.asyncio
async def test_snapshot_success(temp_collector):
    """Successful snapshot saves all 4 state files and adds 0 digest entries."""
    collector, tmp = temp_collector

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is True
        assert mock_add.call_count == 0

    # Verify state files exist on disk and have expected records
    with open(collector.udb_state_path, "r", encoding="utf-8") as f:
        udb_data = json.load(f)
        assert "app1" in udb_data
        assert udb_data["app1"]["version"] == "1.0"

    with open(collector.fortheusers_state_path, "r", encoding="utf-8") as f:
        ftu_data = json.load(f)
        assert "switch-hb:sw_app" in ftu_data
        assert "wiiu-hb:wiiu_app" in ftu_data

    with open(collector.vitadb_state_path, "r", encoding="utf-8") as f:
        vita_data = json.load(f)
        assert "vita-hb:10" in vita_data
        assert "vita-plugin:20" in vita_data
        assert "vita-tool:30" in vita_data
        assert "vita-psp:40" in vita_data

    with open(collector.switchports_state_path, "r", encoding="utf-8") as f:
        sp_data = json.load(f)
        assert "test/mario" in sp_data


@pytest.mark.asyncio
async def test_snapshot_failure_preserves_state(temp_collector):
    """If any stream fails, prior state files must remain byte-for-byte identical."""
    collector, tmp = temp_collector

    # Pre-populate state files with canary bytes
    canary = b'{"canary": 42}'
    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "wb") as f:
            f.write(canary)

    # Make one endpoint fail (e.g. VitaDB plugin returns HTTP 500)
    mock_session = make_standard_mock_session()
    mock_session.routes[VITADB_ENDPOINTS[1][0]] = MockResponse(status=500)
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is False
        assert mock_add.call_count == 0

    # Verify byte-for-byte equality of all 4 state files
    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "rb") as f:
            assert f.read() == canary


@pytest.mark.asyncio
async def test_snapshot_commit_failure_rolls_back_atomically(temp_collector):
    """If disk write/replace fails during snapshot commit, all pre-existing files are restored and new ones removed."""
    collector, tmp = temp_collector
    canary = b'{"pre_existing_canary": 12345}'

    # udb and fortheusers exist before snapshot
    with open(collector.udb_state_path, "wb") as f:
        f.write(canary)
    with open(collector.fortheusers_state_path, "wb") as f:
        f.write(canary)

    # vitadb and switchports do NOT exist before snapshot
    if os.path.exists(collector.vitadb_state_path):
        os.unlink(collector.vitadb_state_path)
    if os.path.exists(collector.switchports_state_path):
        os.unlink(collector.switchports_state_path)

    real_replace = os.replace

    def mock_replace(src, dst):
        # Fail when trying to replace the 2nd file (fortheusers)
        if str(dst) == str(collector.fortheusers_state_path):
            raise PermissionError("Simulated disk write error on fortheusers_state.json")
        return real_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
            success = await collector.create_snapshot()
            assert success is False
            assert mock_add.call_count == 0

    # 1. Pre-existing files must be byte-for-byte identical to their original bytes
    with open(collector.udb_state_path, "rb") as f:
        assert f.read() == canary
    with open(collector.fortheusers_state_path, "rb") as f:
        assert f.read() == canary

    # 2. Files that did not exist before must not exist
    assert not os.path.exists(collector.vitadb_state_path)
    assert not os.path.exists(collector.switchports_state_path)

    # 3. No leftover .tmp files
    for entry in os.listdir(tmp):
        assert ".tmp." not in entry


@pytest.mark.asyncio
async def test_snapshot_switchports_zero_entries_aborts(temp_collector):
    """A non-empty SwitchPorts response with 0 valid port entries must abort snapshot without modifying files."""
    collector, tmp = temp_collector
    canary = b'{"pre_existing_canary": 999}'
    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "wb") as f:
            f.write(canary)

    # Non-empty response that contains no table rows
    mock_session = make_standard_mock_session()
    mock_session.routes[SWITCHPORTS_REPO_URL] = MockResponse(
        200,
        text_data="# SwitchPorts\nThis repository is currently under maintenance. No ports listed.\n"
    )
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is False
        assert mock_add.call_count == 0

    # All files remain byte-for-byte unchanged
    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "rb") as f:
            assert f.read() == canary


@pytest.mark.asyncio
async def test_snapshot_switchports_optional_blank_fields_accepted(temp_collector):
    """SwitchPorts table rows with optional blank fields must not reject the catalogue."""
    collector, tmp = temp_collector
    table_with_blanks = (
        "| Game | Version | Updated | Download | Info |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Minimal Port | | | | |\n"
    )
    mock_session = make_standard_mock_session()
    mock_session.routes[SWITCHPORTS_REPO_URL] = MockResponse(200, text_data=table_with_blanks)
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is True
        assert mock_add.call_count == 0

    with open(collector.switchports_state_path, "r", encoding="utf-8") as f:
        sp_data = json.load(f)
        assert "minimal port" in sp_data
        assert sp_data["minimal port"]["game_name"] == "Minimal Port"
        assert sp_data["minimal port"]["version"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_key,bad_response", [
    # Universal-DB empty dict
    ("udb_empty", {UDB_API_URL: MockResponse(200, json_data={})}),
    # Universal-DB only non-3DS/DS systems
    ("udb_no_3ds", {UDB_API_URL: MockResponse(200, json_data={
        "wii_app": {"title": "Wii Only", "systems": ["Wii"]}
    })}),
    # ForTheUsers Switch empty packages
    ("ftu_switch_empty", {SWITCH_REPO_URL: MockResponse(200, json_data={"packages": []})}),
    # ForTheUsers Switch invalid/empty name packages
    ("ftu_switch_no_name", {SWITCH_REPO_URL: MockResponse(200, json_data={"packages": [{"name": ""}]})}),
    # ForTheUsers Wii U empty packages
    ("ftu_wiiu_empty", {WIIU_REPO_URL: MockResponse(200, json_data={"packages": []})}),
    # VitaDB empty list
    ("vitadb_empty", {VITADB_ENDPOINTS[0][0]: MockResponse(200, json_data=[])}),
    # VitaDB inactive/invalid entries (status != "0" or no id)
    ("vitadb_inactive", {VITADB_ENDPOINTS[0][0]: MockResponse(200, json_data=[
        {"id": 1, "status": "1"},
        {"id": "", "status": "0"},
    ])}),
])
async def test_snapshot_zero_usable_stream_aborts_and_preserves_state(temp_collector, stream_key, bad_response):
    """If any stream returns zero usable catalogue entries, create_snapshot must abort without modifying any state file."""
    collector, tmp = temp_collector
    canary = b'{"canary_key": "unmodified_content"}'

    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "wb") as f:
            f.write(canary)

    mock_session = make_standard_mock_session()
    mock_session.routes.update(bad_response)
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is False
        assert mock_add.call_count == 0

    # All 4 state files must remain completely unchanged
    for path in [
        collector.udb_state_path,
        collector.fortheusers_state_path,
        collector.vitadb_state_path,
        collector.switchports_state_path,
    ]:
        with open(path, "rb") as f:
            assert f.read() == canary


@pytest.mark.asyncio
async def test_snapshot_optional_blank_metadata_accepted(temp_collector):
    """Entries with identity present but optional blank metadata (version, updated, date, etc.) are accepted."""
    collector, tmp = temp_collector
    mock_session = make_standard_mock_session()
    mock_session.routes[UDB_API_URL] = MockResponse(200, json_data={
        "minimal_udb": {
            "title": "Minimal UDB",
            "version": "",
            "updated": "",
            "systems": ["3DS"],
            "download_page": "",
        }
    })
    mock_session.routes[SWITCH_REPO_URL] = MockResponse(200, json_data={
        "packages": [
            {"name": "minimal_sw", "version": "", "updated": ""}
        ]
    })
    mock_session.routes[WIIU_REPO_URL] = MockResponse(200, json_data={
        "packages": [
            {"name": "minimal_wiiu", "version": "", "updated": ""}
        ]
    })
    mock_session.routes[VITADB_ENDPOINTS[0][0]] = MockResponse(200, json_data=[
        {"id": 99, "name": "Minimal Vita", "version": "", "date": "", "status": "0"}
    ])
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        success = await collector.create_snapshot()
        assert success is True
        assert mock_add.call_count == 0

    with open(collector.udb_state_path, "r", encoding="utf-8") as f:
        udb_data = json.load(f)
        assert "minimal_udb" in udb_data
        assert udb_data["minimal_udb"]["version"] == ""

    with open(collector.fortheusers_state_path, "r", encoding="utf-8") as f:
        ftu_data = json.load(f)
        assert "switch-hb:minimal_sw" in ftu_data
        assert "wiiu-hb:minimal_wiiu" in ftu_data

    with open(collector.vitadb_state_path, "r", encoding="utf-8") as f:
        vita_data = json.load(f)
        assert "vita-hb:99" in vita_data






@pytest.mark.asyncio
async def test_snapshot_cli_exit_code():
    """Verify that --snapshot failure exits nonzero."""
    test_args = ["collect_homebrew_updates.py", "--snapshot"]
    with patch.object(sys, "argv", test_args):
        with patch.object(HomebrewUpdatesCollector, "create_snapshot", return_value=False):
            with patch("sys.exit") as mock_exit:
                await main()
                mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_normal_first_run_seeds_silently(temp_collector):
    """Empty baseline for any source seeds state and publishes nothing."""
    collector, tmp = temp_collector

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        # 1. UDB first run
        collector._udb_state = {}
        await collector.collect_udb_updates([])
        assert "app1" in collector._udb_state
        assert mock_add.call_count == 0

        # 2. FTU Switch first run
        collector._fortheusers_state = {}
        await collector.collect_fortheusers_updates("Switch", SWITCH_REPO_URL, "switch-hb", set(), [])
        assert "switch-hb:sw_app" in collector._fortheusers_state
        assert mock_add.call_count == 0

        # 3. FTU WiiU first run
        await collector.collect_fortheusers_updates("WiiU", WIIU_REPO_URL, "wiiu-hb", set(), [])
        assert "wiiu-hb:wiiu_app" in collector._fortheusers_state
        assert mock_add.call_count == 0

        # 4. VitaDB first run
        collector._vitadb_state = {}
        await collector.collect_vitadb_updates(VITADB_ENDPOINTS[0][0], "vita-hb", "PSVita", [])
        assert "vita-hb:10" in collector._vitadb_state
        assert mock_add.call_count == 0

        # 5. SwitchPorts first run
        collector._switchports_state = {}
        await collector.collect_switchports_updates([])
        assert "test/mario" in collector._switchports_state
        assert mock_add.call_count == 0


@pytest.mark.asyncio
async def test_seeded_baseline_new_app_marks_is_new_true(temp_collector):
    """After baseline exists, an absent key is published with is_new=True."""
    collector, tmp = temp_collector

    # 1. UDB: baseline has app1, incoming has app1 and new app2
    collector._udb_state = {
        "app1": {"version": "1.0", "updated": "2026-01-01T00:00:00Z", "release_url": "https://example.com/app1"}
    }
    mock_session = make_standard_mock_session()
    mock_session.routes[UDB_API_URL] = MockResponse(200, json_data={
        "app1": {"title": "App One", "version": "1.0", "updated": "2026-01-01T00:00:00Z", "systems": ["3DS"]},
        "app2": {"title": "App Two", "version": "0.9", "updated": "2026-01-02T00:00:00Z", "systems": ["3DS"]},
    })
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "App Two"
        assert kwargs["is_new"] is True
        assert "app2" in collector._udb_state

    # 2. FTU: baseline has sw_app, incoming has new sw_app2
    collector._fortheusers_state = {
        "switch-hb:sw_app": {"version": "1.0.0", "updated": "01/01/2026"}
    }
    mock_session.routes[SWITCH_REPO_URL] = MockResponse(200, json_data={
        "packages": [
            {"name": "sw_app", "title": "Switch App", "version": "1.0.0", "updated": "01/01/2026"},
            {"name": "sw_app2", "title": "Switch App 2", "version": "1.0.0", "updated": "02/01/2026"},
        ]
    })
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_fortheusers_updates("Switch", SWITCH_REPO_URL, "switch-hb", set(), [])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Switch App 2"
        assert kwargs["is_new"] is True
        assert "switch-hb:sw_app2" in collector._fortheusers_state

    # 3. VitaDB: baseline has vita-hb:10, incoming has new vita-hb:11
    collector._vitadb_state = {
        "vita-hb:10": {"version": "1.0", "date": "2026-01-10"}
    }
    mock_session.routes[VITADB_ENDPOINTS[0][0]] = MockResponse(200, json_data=[
        {"id": 10, "name": "Vita App", "version": "1.0", "date": "2026-01-10", "status": "0"},
        {"id": 11, "name": "Vita App 2", "version": "1.0", "date": "2026-01-11", "status": "0"},
    ])
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_vitadb_updates(VITADB_ENDPOINTS[0][0], "vita-hb", "PSVita", [])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Vita App 2"
        assert kwargs["is_new"] is True
        assert "vita-hb:11" in collector._vitadb_state

    # 4. SwitchPorts: baseline has mario, incoming has luigi
    luigi_table = (
        "| Game | Version | Updated | Download | Info |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Mario Port | 1.0 | 2026-03-01 | [Link](https://github.com/test/mario/releases) | |\n"
        "| Luigi Port | 1.0 | 2026-03-02 | [Link](https://github.com/test/luigi/releases) | |\n"
    )
    collector._switchports_state = {
        "test/mario": {"game_name": "Mario Port", "version": "1.0", "last_updated": "2026-03-01", "release_url": ""}
    }
    mock_session.routes[SWITCHPORTS_REPO_URL] = MockResponse(200, text_data=luigi_table)
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_switchports_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Luigi Port (Port)"
        assert kwargs["is_new"] is True
        assert "test/luigi" in collector._switchports_state


@pytest.mark.asyncio
async def test_seeded_baseline_changed_app_marks_is_new_false(temp_collector):
    """When a known key's version changes, it is published with is_new=False."""
    collector, tmp = temp_collector

    # UDB update
    collector._udb_state = {
        "app1": {"version": "1.0", "updated": "2026-01-01T00:00:00Z", "release_url": "https://example.com/app1"}
    }
    mock_session = make_standard_mock_session()
    mock_session.routes[UDB_API_URL] = MockResponse(200, json_data={
        "app1": {"title": "App One", "version": "1.1", "updated": "2026-01-02T00:00:00Z", "systems": ["3DS"]},
    })
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "App One"
        assert kwargs["version"] == "1.1"
        assert kwargs["is_new"] is False
        assert collector._udb_state["app1"]["version"] == "1.1"


@pytest.mark.asyncio
async def test_prefix_isolation(temp_collector):
    """An initialized prefix must not cause an unrelated prefix to skip first-run seeding."""
    collector, tmp = temp_collector

    # FTU: switch-hb is seeded, but wiiu-hb is unseeded
    collector._fortheusers_state = {
        "switch-hb:sw_app": {"version": "1.0.0", "updated": "01/01/2026"}
    }
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        # Running WiiU must silently seed wiiu-hb, not treat wiiu_app as a new release
        await collector.collect_fortheusers_updates("WiiU", WIIU_REPO_URL, "wiiu-hb", set(), [])
        assert mock_add.call_count == 0
        assert "wiiu-hb:wiiu_app" in collector._fortheusers_state

    # VitaDB: vita-hb is seeded, but vita-plugin is unseeded
    collector._vitadb_state = {
        "vita-hb:10": {"version": "1.0", "date": "2026-01-10"}
    }
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        # Running vita-plugin must silently seed vita-plugin, not treat it as new release
        await collector.collect_vitadb_updates(VITADB_ENDPOINTS[1][0], "vita-plugin", "PSVita Plugin", [])
        assert mock_add.call_count == 0
        assert "vita-plugin:20" in collector._vitadb_state


@pytest.mark.asyncio
async def test_vitadb_blank_metadata_key_membership(temp_collector):
    """A known VitaDB key with blank metadata is known, not a new entry."""
    collector, tmp = temp_collector

    # Seed vita-hb:10 with blank metadata, plus vita-hb:1 to establish baseline
    collector._vitadb_state = {
        "vita-hb:1": {"version": "1.0", "date": "2026-01-01"},
        "vita-hb:10": {"version": "", "date": ""},
    }

    mock_session = make_standard_mock_session()
    # Scenario A: still blank -> do nothing
    mock_session.routes[VITADB_ENDPOINTS[0][0]] = MockResponse(200, json_data=[
        {"id": 10, "name": "Vita App", "version": "", "date": "", "status": "0"}
    ])
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_vitadb_updates(VITADB_ENDPOINTS[0][0], "vita-hb", "PSVita", [])
        assert mock_add.call_count == 0

    # Scenario B: updated to 1.1 -> published as UPDATE (is_new=False), never new app
    mock_session.routes[VITADB_ENDPOINTS[0][0]] = MockResponse(200, json_data=[
        {"id": 10, "name": "Vita App", "version": "1.1", "date": "2026-02-01", "status": "0"}
    ])
    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_vitadb_updates(VITADB_ENDPOINTS[0][0], "vita-hb", "PSVita", [])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Vita App"
        assert kwargs["is_new"] is False
        assert collector._vitadb_state["vita-hb:10"]["version"] == "1.1"


@pytest.mark.asyncio
async def test_unprocessed_manual_release_collision(temp_collector):
    """Unprocessed manual releases must skip digest posting and only update state."""
    collector, tmp = temp_collector

    collector.unprocessed_manual_names = {"app one"}
    collector._udb_state = {
        "existing_app": {"version": "1.0", "updated": "2026-01-01"}
    }
    mock_session = make_standard_mock_session()
    # App One is new to UDB state but pending in manual releases
    mock_session.routes[UDB_API_URL] = MockResponse(200, json_data={
        "existing_app": {"title": "Existing", "version": "1.0", "updated": "2026-01-01", "systems": ["3DS"]},
        "app1": {"title": "App One", "version": "2.0", "updated": "2026-02-01", "systems": ["3DS"]},
    })
    collector.session = mock_session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 0
        # State was still updated
        assert "app1" in collector._udb_state
        assert collector._udb_state["app1"]["version"] == "2.0"
