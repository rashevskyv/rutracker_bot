"""Regression tests for 3DS releases and new app marker classification."""
import json
import os
import tempfile
from unittest.mock import patch
import pytest

from collect_homebrew_updates import (
    HomebrewUpdatesCollector,
    UDB_API_URL,
)
from digest.homebrew import homebrew_digest_manager


class MockResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json_data = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, content_type=None):
        return self._json_data


class MockSession:
    def __init__(self, routes=None):
        self.routes = routes or {}

    def get(self, url, **kwargs):
        handler = self.routes.get(url)
        if callable(handler):
            return handler(url, **kwargs)
        if handler is not None:
            return handler
        return MockResponse(200, {})


@pytest.fixture
def udb_collector():
    tmp = tempfile.mkdtemp()
    list_path = os.path.join(tmp, "list_hb.json")
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    collector = HomebrewUpdatesCollector(
        list_path=list_path,
        state_path=os.path.join(tmp, "hb_state.json"),
        udb_state_path=os.path.join(tmp, "udb_state.json"),
        fortheusers_state_path=os.path.join(tmp, "fortheusers_state.json"),
        vitadb_state_path=os.path.join(tmp, "vitadb_state.json"),
        switchports_state_path=os.path.join(tmp, "switchports_state.json"),
        last_run_path=os.path.join(tmp, "last_homebrew_digest_run.json"),
    )
    # Stub description and summary translation
    async def mock_text(*a, **kw):
        return "Mock text"

    collector._get_description_cached = mock_text
    collector._get_description_for_udb_app = mock_text
    collector.summarize_and_translate_notes = mock_text
    return collector, tmp


@pytest.mark.asyncio
async def test_udb_known_app_update_is_not_new(udb_collector):
    """An update to an already known app in _udb_state must be published with is_new=False."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "app1": {
            "version": "1.0",
            "updated": "2026-08-01T00:00:00Z",
            "release_url": "https://example.com/app1",
        }
    }
    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "app1": {
                "title": "App One",
                "version": "1.1",
                "updated": "2026-09-01T00:00:00Z",
                "systems": ["3DS"],
                "download_page": "https://example.com/app1",
            }
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "App One"
        assert kwargs["version"] == "1.1"
        assert kwargs["is_new"] is False


@pytest.mark.asyncio
async def test_udb_genuinely_new_app_after_boundary_is_new(udb_collector):
    """A genuinely new app released after the persisted time boundary must have is_new=True."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
            "release_url": "https://example.com/existing",
        }
    }
    # Set persisted time boundary: 2026-08-27
    with open(collector.last_run_path, "w", encoding="utf-8") as f:
        json.dump({"last_digest_time": "2026-08-27T08:00:00"}, f)

    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "brand_new_app": {
                "title": "Brand New App",
                "version": "1.0.0",
                "updated": "2026-09-01T12:00:00Z",
                "systems": ["3DS"],
                "download_page": "https://example.com/new",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Brand New App"
        assert kwargs["is_new"] is True


@pytest.mark.asyncio
async def test_udb_newly_indexed_app_with_old_release_date_is_not_new(udb_collector):
    """An app newly indexed into UDB whose release date precedes the persisted time boundary must receive is_new=False."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
            "release_url": "https://example.com/existing",
        }
    }
    # Persisted time boundary: 2026-08-27
    with open(collector.last_run_path, "w", encoding="utf-8") as f:
        json.dump({"last_digest_time": "2026-08-27T08:00:00"}, f)

    # Booru3DS released on 2026-08-22, before the 2026-08-27 boundary
    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "booru3ds": {
                "title": "Booru3DS",
                "version": "v1.0",
                "updated": "2026-08-22T10:00:00Z",
                "systems": ["3DS"],
                "download_page": "https://example.com/booru",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Booru3DS"
        assert kwargs["is_new"] is False


@pytest.mark.asyncio
async def test_udb_known_in_local_registry_is_not_new(udb_collector):
    """An app present in local registry (list_hb.json) must not be flagged as a new app even without UDB state."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
        }
    }
    local_entries = [{
        "name": "aurorachat",
        "api_url": "https://api.github.com/repos/Unitendo/aurorachat",
        "platform": "3DS",
    }]
    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "aurorachat-3ds": {
                "title": "aurorachat-3ds",
                "version": "v7.1",
                "updated": "2026-09-01T10:00:00Z",
                "systems": ["3DS"],
                "github": "https://github.com/Unitendo/aurorachat",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates(local_entries)
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "aurorachat-3ds"
        assert kwargs["is_new"] is False


@pytest.mark.asyncio
async def test_udb_hb_state_prefix_collision_does_not_treat_app_as_known(udb_collector):
    """An app whose slug is a prefix of an hb_state key (owner/repo vs owner/repo-tools) must not be treated as known."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
        }
    }
    # hb_state contains repo-tools, NOT repo
    collector._state = {
        "https://api.github.com/repos/testowner/coolapp-tools": {
            "comm_date": "2026-08-01T00:00:00Z",
            "tag_name": "v1.0",
        }
    }
    with open(collector.last_run_path, "w", encoding="utf-8") as f:
        json.dump({"last_digest_time": "2026-08-27T08:00:00"}, f)

    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "coolapp": {
                "title": "Cool App",
                "version": "1.0",
                "updated": "2026-09-01T10:00:00Z",
                "systems": ["3DS"],
                "github": "https://github.com/testowner/coolapp",
                "download_page": "https://example.com/coolapp",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "Cool App"
        # Must be recognized as genuinely new, not matched against coolapp-tools
        assert kwargs["is_new"] is True


@pytest.mark.asyncio
async def test_udb_local_timezone_boundary_evaluation(udb_collector):
    """Verify that get_persisted_time_boundary() interprets naive timestamps using the host's local timezone."""
    from datetime import datetime, timezone, timedelta
    collector, tmp = udb_collector

    raw = "2026-08-27T08:00:00"
    with open(collector.last_run_path, "w", encoding="utf-8") as f:
        json.dump({"last_digest_time": raw}, f)

    # 1. Direct check: the real method must match datetime.fromisoformat(raw).astimezone()
    boundary = collector.get_persisted_time_boundary()
    expected_boundary = datetime.fromisoformat(raw).astimezone()
    assert boundary is not None
    assert boundary == expected_boundary
    assert boundary.tzinfo is not None

    # 2. Integration check with collect_udb_updates using the real method
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
        }
    }
    newer_iso = (expected_boundary + timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    older_iso = (expected_boundary - timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "app_newer": {
                "title": "App Newer",
                "version": "1.0",
                "updated": newer_iso,
                "systems": ["3DS"],
                "download_page": "https://example.com/newer",
            },
            "app_older": {
                "title": "App Older",
                "version": "1.0",
                "updated": older_iso,
                "systems": ["3DS"],
                "download_page": "https://example.com/older",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 2
        calls = {call.kwargs["app_name"]: call.kwargs["is_new"] for call in mock_add.call_args_list}
        assert calls["App Newer"] is True
        assert calls["App Older"] is False


@pytest.mark.asyncio
async def test_udb_missing_or_invalid_updated_is_conservative_not_new(udb_collector):
    """An app with missing or invalid updated timestamp must be conservatively classified as ordinary (is_new=False)."""
    collector, tmp = udb_collector
    collector._udb_state = {
        "existing_app": {
            "version": "1.0",
            "updated": "2026-08-20T00:00:00Z",
        }
    }
    with open(collector.last_run_path, "w", encoding="utf-8") as f:
        json.dump({"last_digest_time": "2026-08-27T08:00:00"}, f)

    session = MockSession({
        UDB_API_URL: MockResponse(200, {
            "existing_app": {
                "title": "Existing",
                "version": "1.0",
                "updated": "2026-08-20T00:00:00Z",
                "systems": ["3DS"],
            },
            "no_date_app": {
                "title": "No Date App",
                "version": "1.0",
                "updated": "",  # missing updated date
                "systems": ["3DS"],
                "download_page": "https://example.com/nodate",
            },
        })
    })
    collector.session = session

    with patch.object(homebrew_digest_manager, "add_entry") as mock_add:
        await collector.collect_udb_updates([])
        assert mock_add.call_count == 1
        _, kwargs = mock_add.call_args
        assert kwargs["app_name"] == "No Date App"
        assert kwargs["is_new"] is False
        assert kwargs["release_date"] is not None
