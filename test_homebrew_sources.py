import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import homebrew_sources as sources, homebrew_registry as registry

SWITCH = "https://api.github.com/repos/author/game-nx"
PC = "https://api.github.com/repos/upstream/game"


@pytest.fixture
def setup_sources(monkeypatch, tmp_path):
    import core.settings_loader as settings
    import services.gpt as gpt
    import digest.homebrew as hb
    import services.store_sync as ss
    monkeypatch.setattr(registry, "REGISTRY_PATH", tmp_path / "list_hb.json")
    monkeypatch.setattr(registry, "MANUAL_PATH", tmp_path / "manual.json")
    payloads = {}
    for api, platform in [(SWITCH, "Switch"), (PC, "PC")]:
        web = api.replace("api.github.com/repos", "github.com")
        payloads[api] = {"html_url": web, "name": api.rsplit("/", 1)[-1], "description": platform + " game port"}
        payloads[api + "/readme"] = {"content": base64.b64encode((platform + " build instructions").encode()).decode()}
        payloads[api + "/releases?per_page=5"] = [
            {"tag_name": "v1", "html_url": web + "/releases/tag/v1", "published_at": "2026-10-14T12:00:00Z",
             "assets": [{"name": "game.nro" if platform == "Switch" else "game-windows.zip"}]}]

    def get(url, **kw):
        context = AsyncMock()
        context.__aenter__.return_value = SimpleNamespace(status=200, json=AsyncMock(return_value=payloads[url]))
        return context

    monkeypatch.setattr(settings, "get_session", lambda: SimpleNamespace(get=get))
    result = {"sources": [{"api_url": api, "platform": platform, "description": "Порт гри для " + platform}
                          for api, platform in [(SWITCH, "Switch"), (PC, "PC")]]}
    ask = AsyncMock(return_value=json.dumps(result))
    monkeypatch.setattr(gpt, "complete", ask)
    digest = hb.HomebrewDigest(str(tmp_path / "digest.json"))
    monkeypatch.setattr(hb, "homebrew_digest_manager", digest)
    monkeypatch.setattr(ss, "sync_pending_digest_items", AsyncMock(return_value={}))
    return ask, result, digest, payloads


@pytest.mark.asyncio
async def test_separates_platforms_and_deduplicates_retries(setup_sources):
    ask, result, digest, _ = setup_sources
    assert await registry.register_tracker_homebrew("Game homebrew", [SWITCH, PC])
    rows = registry.load_registry(registry.REGISTRY_PATH)
    assert {r["api_url"]: r["platform"] for r in rows} == {SWITCH: "Switch", PC: "PC"}
    assert {r["platform"] for r in digest.pending_store_sync()} == {"Switch", "PC"}
    prompt = ask.call_args.args[0]
    assert "game.nro" in prompt and "game-windows.zip" in prompt and "build instructions" in prompt
    assert not await registry.register_tracker_homebrew("Game homebrew", [SWITCH, PC])
    assert len(registry.load_registry(registry.REGISTRY_PATH)) == 2
    assert len(digest._load_data()["entries"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("api_url", "https://api.github.com/repos/invented/repo"),
                                       ("platform", "PS5"), ("description", "x" * 221)])
async def test_unverified_ai_result_writes_no_releases_and_retries(setup_sources, field, value):
    ask, result, digest, _ = setup_sources
    result["sources"][0][field] = value
    ask.return_value = json.dumps(result)
    assert not await registry.register_tracker_homebrew("Game", [SWITCH, PC])
    assert not registry.REGISTRY_PATH.exists()
    assert digest._load_data()["entries"] == []
    assert registry._load_pending() == {"Game": sorted([SWITCH, PC])}


@pytest.mark.asyncio
async def test_ai_outage_is_retried_without_new_tracker_post(setup_sources):
    ask, result, digest, _ = setup_sources
    ask.return_value = None
    assert not await registry.register_tracker_homebrew("Game", [SWITCH, PC])
    ask.return_value = json.dumps(result)
    await registry.retry_tracker_homebrew()
    assert registry._load_pending() == {}
    assert len(digest._load_data()["entries"]) == 2


@pytest.mark.asyncio
async def test_failed_retries_rotate_instead_of_starving_later_posts(setup_sources):
    ask, _, _, _ = setup_sources
    ask.return_value = None
    for title in ["A", "B", "C", "D"]:
        await registry.register_tracker_homebrew(title, [SWITCH, PC])
    await registry.retry_tracker_homebrew()
    assert list(registry._load_pending()) == ["D", "A", "B", "C"]


@pytest.mark.asyncio
async def test_single_pc_source_is_not_assumed_switch(setup_sources):
    ask, result, digest, _ = setup_sources
    result["sources"] = result["sources"][1:]
    ask.return_value = json.dumps(result)
    assert await registry.register_tracker_homebrew("Homebrew", [PC])
    assert registry.load_registry(registry.REGISTRY_PATH)[0]["platform"] == "PC"


@pytest.mark.asyncio
async def test_release_from_other_repo_is_rejected(setup_sources):
    _, _, _, payloads = setup_sources
    payloads[SWITCH + "/releases?per_page=5"][0]["html_url"] = "https://github.com/other/game/releases/tag/v1"
    with pytest.raises(ValueError, match="Release identity"):
        await sources.resolve_sources("Game", {SWITCH, PC})


@pytest.mark.asyncio
async def test_gitlab_project_id_and_pc_release_are_preserved(setup_sources):
    ask, _, digest, payloads = setup_sources
    api = "https://gitlab.com/api/v4/projects/group%2Fgame/releases"
    canonical = "https://gitlab.com/api/v4/projects/42/releases"
    metadata = {"id": 42, "name": "Game", "web_url": "https://gitlab.com/group/game", "description": "PC game"}
    payloads[api.removesuffix("/releases")] = metadata
    payloads[canonical.removesuffix("/releases")] = metadata
    payloads[api] = [{"tag_name": "v1", "released_at": "2026-10-14T12:00:00Z",
                      "_links": {"self": "https://gitlab.com/group/game/-/releases/v1"},
                      "assets": {"links": [{"name": "game-windows.zip"}]}}]
    ask.return_value = json.dumps({"sources": [{"api_url": api, "platform": "PC", "description": "Порт для ПК"}]})
    assert await registry.register_tracker_homebrew("Homebrew", [api])
    assert registry.load_registry(registry.REGISTRY_PATH)[0]["api_url"] == canonical
    assert digest._load_data()["entries"][0]["platform"] == "PC"
