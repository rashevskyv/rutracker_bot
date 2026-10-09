"""RuTracker discovery and registry sync are isolated from live data and external services."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bs4 import BeautifulSoup

from services import homebrew_registry as registry
import sync_gist_state as sync

API = "https://api.github.com/repos/author/game-nx"
DOWNLOAD = sync.download_state
UPLOAD = sync.upload_state


def row(api=API, name="Game"):
    return {"api_url": api, "app_name": name, "platform": "Switch"}


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/Author/Game-NX/releases/tag/v1?x=1", API),
    ("https://api.github.com/repos/Author/Game-NX/", API),
    ("https://github.com/author/game-nx.git", API),
    ("https://gitlab.com/group/subgroup/game/-/releases/v1", "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fgame/releases"),
    ("https://gitlab.com/api/v4/projects/42/releases", "https://gitlab.com/api/v4/projects/42/releases"),
    ("https://github.com/author", ""),
    ("https://github.com.evil.test/author/game", ""),
    ("https://github.com@evil.test/author/game", ""),
    ("https://github.com:8080/author/game", ""),
    ("https://github.com/author/..", ""),
    ("https://github.com/topics/switch", ""),
    ("https://gitlab.com/author", ""),
    ("file:///author/game", ""),
    (None, ""),
])
def test_source_identity(url, expected):
    assert registry.repository_api_url(url) == expected


def test_source_urls_include_spoilers_and_plain_text():
    post = BeautifulSoup('<div><div class="sp-wrap"><a href="https://github.com/Author/Game-NX/releases">Source</a></div>'
                         'https://github.com/author/game-nx/releases/tag/v1.</div>', "html.parser")
    assert registry.source_urls(post) == [API]


@pytest.fixture
def discovery(monkeypatch, tmp_path):
    import core.settings_loader as settings
    monkeypatch.setattr(registry, "REGISTRY_PATH", tmp_path / "list_hb.json")
    monkeypatch.setattr(registry, "MANUAL_PATH", tmp_path / "manual_releases.json")
    response = SimpleNamespace(status=200, json=AsyncMock(return_value={
        "name": "game-nx", "html_url": "https://github.com/author/game-nx",
    }))
    context = AsyncMock()
    context.__aenter__.return_value = response
    get = Mock(return_value=context)
    monkeypatch.setattr(settings, "get_session", lambda: SimpleNamespace(get=get))
    return response, get


@pytest.mark.asyncio
async def test_register_then_repeat_without_reannouncement(discovery):
    before = datetime.now(timezone.utc)
    assert await registry.register_tracker_homebrew("Torrent title [Homebrew]", [API])
    rows = registry.load_registry(registry.REGISTRY_PATH)
    assert len(rows) == 1
    assert rows[0]["api_url"] == API
    assert rows[0]["platform"] == "Switch"
    assert rows[0]["new"] is False
    assert "tag_name" not in rows[0]
    assert datetime.fromisoformat(rows[0]["comm_date"]) >= before
    assert not await registry.register_tracker_homebrew("Updated title", [API])
    assert discovery[1].call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("processed", [True, False])
async def test_manual_source_is_already_tracked(discovery, processed):
    registry.MANUAL_PATH.write_text(json.dumps([{
        "type": "homebrew", "release_url": "https://github.com/Author/Game-NX/releases/tag/v1", "processed": processed,
    }]), encoding="utf-8")
    assert not await registry.register_tracker_homebrew("Game", [API])
    discovery[1].assert_not_called()
    assert not registry.REGISTRY_PATH.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("urls", [[], [API, "https://github.com/other/game"], ["https://github.com.evil.test/a/b"]])
async def test_missing_ambiguous_or_invalid_sources(discovery, urls):
    assert not await registry.register_tracker_homebrew("Game", urls)
    discovery[1].assert_not_called()
    assert not registry.REGISTRY_PATH.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["{broken", "{}", "[42]", "[{}]"])
async def test_corrupt_registry_is_never_overwritten(discovery, content):
    registry.REGISTRY_PATH.write_text(content, encoding="utf-8")
    assert not await registry.register_tracker_homebrew("Game", [API])
    assert registry.REGISTRY_PATH.read_text(encoding="utf-8") == content
    discovery[1].assert_not_called()


@pytest.mark.asyncio
async def test_failed_lookup_does_not_write(discovery):
    discovery[0].status = 503
    assert not await registry.register_tracker_homebrew("Game", [API])
    assert not registry.REGISTRY_PATH.exists()
    discovery[0].status = 200
    discovery[0].json.side_effect = TimeoutError("offline")
    assert not await registry.register_tracker_homebrew("Game", [API])
    assert not registry.REGISTRY_PATH.exists()


@pytest.mark.asyncio
async def test_mismatched_source_is_rejected(discovery):
    discovery[0].json.return_value = {"name": "Other", "html_url": "https://github.com/other/game"}
    assert not await registry.register_tracker_homebrew("Game", [API])
    assert not registry.REGISTRY_PATH.exists()


@pytest.mark.asyncio
async def test_registration_preserves_rows_added_during_lookup(discovery):
    added = row("https://api.github.com/repos/other/game")

    async def metadata():
        registry.REGISTRY_PATH.write_text(json.dumps([added]), encoding="utf-8")
        return {"name": "game-nx", "html_url": "https://github.com/author/game-nx"}

    discovery[0].json.side_effect = metadata
    assert await registry.register_tracker_homebrew("Game", [API])
    rows = registry.load_registry(registry.REGISTRY_PATH)
    assert rows[0] == added
    assert rows[1]["api_url"] == API


@pytest.mark.asyncio
async def test_collector_ignores_old_release_and_detects_future_update(discovery, monkeypatch, tmp_path):
    from datetime import timedelta
    from collect_homebrew_updates import HomebrewUpdatesCollector
    import services.manual_releases as manual
    monkeypatch.setattr(manual, "load_manual_releases", lambda: [])
    assert await registry.register_tracker_homebrew("Game", [API])
    collector = HomebrewUpdatesCollector(list_path=str(registry.REGISTRY_PATH), state_path=str(tmp_path / "hb_state.json"))
    entry = collector.load_homebrew_list()[0]
    date = datetime.fromisoformat(entry["comm_date"])
    release = {"published_at": (date - timedelta(days=1)).isoformat(), "tag_name": "v1", "html_url": "https://github.com/author/game-nx/releases/tag/v1"}
    monkeypatch.setattr(collector, "github_request", AsyncMock(return_value=[release]))
    assert await collector.check_github_updates(entry) is None
    release["published_at"] = (date + timedelta(hours=1)).isoformat()
    assert (await collector.check_github_updates(entry))["tag_name"] == "v1"


@pytest.mark.asyncio
async def test_gitlab_numeric_identity_deduplicates_existing_entry(discovery):
    api = "https://gitlab.com/api/v4/projects/42/releases"
    registry.REGISTRY_PATH.write_text(json.dumps([row(api)]), encoding="utf-8")
    discovery[0].json.return_value = {"id": 42, "name": "Game"}
    assert not await registry.register_tracker_homebrew("Game", ["https://gitlab.com/group/game/-/releases"])
    assert registry.load_registry(registry.REGISTRY_PATH) == [row(api)]


def test_sync_union_remote_metadata_and_idempotence():
    remote = [row(name="Remote name"), row("https://api.github.com/repos/b/game")]
    local = [row("https://github.com/Author/Game-NX/", "Stale name"), row("https://api.github.com/repos/c/game")]
    merged = json.loads(sync.merge_json_files("list_hb.json", json.dumps(local), json.dumps(remote)))
    assert merged == remote + [local[1]]
    assert registry.merge_registry(merged, remote) == merged
    assert registry.merge_registry(local + local, remote + remote) == merged


def test_sync_does_not_revive_deleted_base_rows():
    base = [row()]
    added = row("https://api.github.com/repos/b/game")
    assert registry.merge_registry(base + [added], [], base) == [added]
    assert registry.merge_registry([], base, base) == []


def test_sync_preserves_existing_distinct_aliases():
    aliases = [row(name="First tool"), row(name="Second tool")]
    assert registry.merge_registry(aliases, aliases) == aliases


@pytest.mark.parametrize("local, remote", [("{broken", "[]"), ("[]", "{broken"), ("{}", "[]"), ('[{"app_name":"Game"}]', "[]")])
def test_sync_rejects_invalid_registries(local, remote):
    with pytest.raises(ValueError):
        sync.merge_json_files("list_hb.json", local, remote)


def test_registry_base_is_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "BASE_DIR", str(tmp_path))
    content = json.dumps([row()])
    sync.save_base("list_hb.json", content)
    assert sync.load_base("list_hb.json") == [row()]


@pytest.mark.parametrize("action", ["download", "upload"])
def test_real_sync_paths_keep_both_additions(monkeypatch, tmp_path, action):
    local = [row("https://api.github.com/repos/local/game")]
    remote = [row("https://api.github.com/repos/remote/game")]
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sync, "BASE_DIR", str(tmp_path / ".gist_base"))
    path = tmp_path / "list_hb.json"
    path.write_text(json.dumps(local), encoding="utf-8")
    requests = []

    def urlopen(request):
        requests.append(request)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status = 200
        response.read.return_value = json.dumps({"files": {"list_hb.json": {"content": json.dumps(remote)}}}).encode()
        return response

    monkeypatch.setattr(sync.urllib.request, "urlopen", urlopen)
    function = DOWNLOAD if action == "download" else UPLOAD
    function("pytest-no-such-gist", "fake-token", target_files=["list_hb.json"])
    assert json.loads(path.read_text(encoding="utf-8")) == remote + local
    if action == "upload":
        payload = json.loads(requests[-1].data)
        assert json.loads(payload["files"]["list_hb.json"]["content"]) == remote + local
        assert sync.load_base("list_hb.json") == remote + local
    else:
        assert sync.load_base("list_hb.json") == remote


def _gist_response(files):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status = 200
    response.read.return_value = json.dumps({"files": files}).encode()
    return response


def test_invalid_gist_registry_does_not_block_other_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    path = tmp_path / "list_hb.json"
    original = json.dumps([row()])
    path.write_text(original, encoding="utf-8")
    response = _gist_response({"list_hb.json": {"content": "{broken"}, "last_entry.txt": {"content": "new-link"}})
    monkeypatch.setattr(sync.urllib.request, "urlopen", Mock(return_value=response))
    DOWNLOAD("pytest-no-such-gist", "fake-token", target_files=["list_hb.json", "last_entry.txt"])
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / "last_entry.txt").read_text(encoding="utf-8") == "new-link"


def test_invalid_local_registry_is_not_uploaded_but_others_are(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    (tmp_path / "list_hb.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "last_entry.txt").write_text("new-link", encoding="utf-8")
    opener = Mock(return_value=_gist_response({"list_hb.json": {"content": json.dumps([row()])}}))
    monkeypatch.setattr(sync.urllib.request, "urlopen", opener)
    UPLOAD("pytest-no-such-gist", "fake-token", target_files=["list_hb.json", "last_entry.txt"])
    patched = json.loads(opener.call_args_list[-1].args[0].data)["files"]
    assert set(patched) == {"last_entry.txt"}
    assert (tmp_path / "list_hb.json").read_text(encoding="utf-8") == "{broken"


def test_valid_local_registry_repairs_broken_gist_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    original = json.dumps([row()])
    (tmp_path / "list_hb.json").write_text(original, encoding="utf-8")
    opener = Mock(return_value=_gist_response({"list_hb.json": {"content": "{broken"}}))
    monkeypatch.setattr(sync.urllib.request, "urlopen", opener)
    UPLOAD("pytest-no-such-gist", "fake-token", target_files=["list_hb.json"])
    patched = json.loads(opener.call_args_list[-1].args[0].data)["files"]
    assert patched["list_hb.json"]["content"] == original


@pytest.mark.asyncio
async def test_parser_extracts_raw_homebrew_sources(monkeypatch):
    from parsers import tracker_parser
    soup = BeautifulSoup('<title>Game :: RuTracker</title><div class="post_body">Game<br>'
                         '<b>Жанр:</b> Action, RPG, Homebrew<br><div class="sp-wrap">'
                         '<a href="https://github.com/Author/Game-NX/releases">Source</a></div></div>'
                         '<a class="magnet-link" href="magnet:?xt=urn:btih:123abc">Torrent</a>', "html.parser")
    monkeypatch.setattr(tracker_parser, "fetch_page_content", AsyncMock(return_value=soup))
    monkeypatch.setattr(tracker_parser, "clean_description_html", lambda text: "cleaned")
    result = await tracker_parser.parse_tracker_entry("https://rutracker.org/forum/viewtopic.php?t=1", "Game")
    assert result[-2:] == (True, [API])


@pytest.mark.asyncio
@pytest.mark.parametrize("is_homebrew, test_mode, send_fails, expected", [
    (True, False, False, 1), (False, False, False, 0), (True, True, False, 0), (True, False, True, 0),
])
async def test_main_registers_only_published_production_homebrew(monkeypatch, tmp_path, is_homebrew, test_mode, send_fails, expected):
    import main
    monkeypatch.chdir(tmp_path)
    (tmp_path / "log").mkdir()
    monkeypatch.setattr(main, "IS_TEST_MODE", test_mode)
    monkeypatch.setattr(main, "TEST_LAST_ENTRY_LINK", "https://rutracker.org/forum/viewtopic.php?t=1")
    monkeypatch.setattr(main, "read_last_entry_link", lambda path: "")
    monkeypatch.setattr(main, "write_last_entry_link", lambda *args: None)
    monkeypatch.setattr(main, "read_last_entry_time", lambda path: None)
    monkeypatch.setattr(main, "write_last_entry_time", lambda *args: None)
    monkeypatch.setattr(main, "get_new_feed_entries", AsyncMock(return_value=[{"link": "https://rutracker.org/forum/viewtopic.php?t=1"}]))
    parsed = ("Game", "Game", None, "magnet", "description", "1 MB", "ENG", ["Homebrew"], None, is_homebrew, [API])
    monkeypatch.setattr(main, "parse_tracker_entry", AsyncMock(return_value=parsed))
    monkeypatch.setattr(main, "db_manager", None)
    for name in ("search_trailer_on_youtube", "send_message_to_admin", "send_document_to_admin", "close_clients", "send_error_to_telegram"):
        monkeypatch.setattr(main, name, AsyncMock(return_value=[]))
    monkeypatch.setattr(main, "send_to_telegram", AsyncMock(side_effect=RuntimeError("send failed") if send_fails else None))
    monkeypatch.setattr(main, "save_posted_link", lambda url: None)
    monkeypatch.setattr(main.digest_manager, "add_entry", lambda **kwargs: None)
    register = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "register_tracker_homebrew", register)
    await main.main_loop()
    assert register.await_count == expected
    if expected:
        register.assert_awaited_once_with("Game", [API])


def test_valid_gist_registry_repairs_broken_local_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    path = tmp_path / "list_hb.json"
    path.write_text('[{"app_name": "Ga', encoding="utf-8")
    remote = json.dumps([row()])
    monkeypatch.setattr(sync.urllib.request, "urlopen", Mock(return_value=_gist_response({"list_hb.json": {"content": remote}})))
    DOWNLOAD("pytest-no-such-gist", "fake-token", target_files=["list_hb.json"])
    assert path.read_text(encoding="utf-8") == remote
