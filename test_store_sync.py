"""services/store_sync.py: offline. Fake gh (test_store_manual.FakeGh), fake page fetch, fake LLM, fake repo check."""
import functools
import json

import pytest

import services.store_manual as sm
import services.store_sync as ss
from digest.homebrew import HomebrewDigest
from test_store_manual import FakeGh, gh_present

CATALOG = {"entries": [{"repo": "Known/Catalog-Port", "title": "Known"}]}


def fetch_json(_url):
    return CATALOG


def load_with(run):
    return functools.partial(ss.load_store_state, fetch_json=fetch_json)


def item(url, app="Proj (owner)", platform="Switch", desc="A port of a game."):
    return {"release_url": url, "app_name": app, "platform": platform, "description": desc}


def no_page(url):
    raise AssertionError(f"fetch must not run for {url}")


async def no_llm(item_, text):
    raise AssertionError("LLM must not run")


def always_exists(repo):
    return True


async def run_sync(items, gh, **overrides):
    kw = dict(run=gh, which=gh_present, fetch=no_page, ask=no_llm, exists=always_exists,
              load=load_with(gh), add=sm.add_manual_rows)
    kw.update(overrides)
    return await ss.sync_new_homebrew_to_store(items, **kw)


def written_rows(gh):
    return json.loads(gh.content)


async def test_github_link_is_added_with_title_category_and_section():
    gh = FakeGh([{"repo": "a/b"}])
    out = await run_sync([item("https://github.com/owner/proj/releases/tag/v1", app="Proj (owner)",
                               desc="Nintendo Switch emulator fork.")], gh)
    assert out == {"https://github.com/owner/proj/releases/tag/v1": "added"}
    assert written_rows(gh)[-1] == {"repo": "owner/proj", "title": "Proj", "section": "Digest", "category": "emu"}


async def test_itch_page_resolved_by_llm_and_verified_on_page():
    page = '<html><a href="https://github.com/owner/proj">source</a> Switch port</html>'
    asked = []

    async def ask(it, text):
        asked.append(text)
        return "owner/proj"

    gh = FakeGh([])
    out = await run_sync([item("https://owner.itch.io/proj", desc="A Switch port tool.")], gh,
                         fetch=lambda u: page, ask=ask)
    assert list(out.values()) == ["added"]
    assert len(asked) == 1 and "GitHub links on the page: owner/proj" in asked[0]
    assert written_rows(gh)[-1]["repo"] == "owner/proj"


async def test_llm_repo_not_on_page_is_rejected():
    async def ask(it, text):
        return "invented/repo"

    gh = FakeGh([])
    out = await run_sync([item("https://x.example/p")], gh,
                         fetch=lambda u: "<html>no links here</html>", ask=ask)
    assert list(out.values()) == ["no_repo"]
    assert gh.puts == []


async def test_repo_already_in_catalog_is_not_written():
    gh = FakeGh([])
    out = await run_sync([item("https://github.com/known/catalog-port")], gh)
    assert list(out.values()) == ["exists"]
    assert gh.puts == []


async def test_disabled_manual_row_is_never_re_added():
    gh = FakeGh([{"repo": "Owner/Proj", "disabled": True}])
    out = await run_sync([item("https://github.com/owner/proj/releases/tag/v2")], gh)
    assert list(out.values()) == ["exists"]
    assert gh.puts == []
    assert written_rows(gh) == [{"repo": "Owner/Proj", "disabled": True}]


async def test_non_switch_platform_is_skipped_without_any_call():
    gh = FakeGh([])
    items = [item("https://github.com/o/vita", platform="PSVita"),
             item("https://github.com/o/ds", platform="3DS/DS(i)/Switch")]
    out = await run_sync(items, gh)
    assert set(out.values()) == {"skipped_platform"}
    assert gh.puts == []


async def test_non_github_org_and_gist_links_are_not_repos():
    assert ss.github_repo_from_url("https://github.com/orgs/acme") is None
    assert ss.github_repo_from_url("https://gist.github.com/u/abc") is None
    assert ss.github_repo_from_url("https://github.com/owner") is None
    assert ss.github_repo_from_url("https://github.com/owner/repo/releases") == "owner/repo"


async def test_cap_adds_at_most_twenty_and_defers_the_rest():
    gh = FakeGh([])
    items = [item(f"https://github.com/o/p{i}") for i in range(25)]
    out = await run_sync(items, gh)
    assert list(out.values()).count("added") == ss.MAX_ADDS
    assert list(out.values()).count("deferred") == 5
    assert len(written_rows(gh)) == 20


async def test_outage_never_raises_and_leaves_items_pending():
    def broken_fetch(url):
        raise OSError("network down")

    async def broken_llm(it, text):
        raise TimeoutError("llm down")

    gh = FakeGh([])
    items = [item("https://itch.example/a"), item("https://itch.example/b")]
    out = await run_sync(items, gh, fetch=lambda u: "<html></html>", ask=broken_llm)
    assert set(out.values()) == {"failed"}
    # Second item must not call the LLM again: the first outage stops LLM use for the run.
    calls = []

    async def counting_llm(it, text):
        calls.append(1)
        raise TimeoutError()

    await run_sync(items, gh, fetch=lambda u: "<html></html>", ask=counting_llm)
    assert len(calls) == 1
    out = await run_sync(items, gh, fetch=broken_fetch)
    assert set(out.values()) == {"failed"}


async def test_unreadable_store_state_defers_everything():
    def broken_load(run, which):
        raise RuntimeError("gh down")

    gh = FakeGh([])
    out = await run_sync([item("https://github.com/o/p")], gh, load=broken_load)
    assert list(out.values()) == ["deferred"]
    assert gh.puts == []


async def test_kill_switch_and_missing_gh_do_nothing(monkeypatch):
    gh = FakeGh([])
    monkeypatch.setenv("STORE_SYNC", "0")
    out = await run_sync([item("https://github.com/o/p")], gh)
    assert out == {} and gh.puts == []
    assert ss.sync_enabled(env={}, which=lambda n: None) is False
    assert ss.sync_enabled(env={}, which=gh_present) is True
    assert ss.sync_enabled(env={"STORE_SYNC": "0"}, which=gh_present) is False


async def test_first_run_does_not_flood_only_new_entries_are_pending(tmp_path):
    digest = HomebrewDigest(data_file=str(tmp_path / "hb.json"))
    digest._save_data({"entries": [{"app_name": "Old", "release_url": "https://github.com/o/old",
                                    "platform": "Switch", "version": "1", "timestamp": "2026-10-01T00:00:00"}]})
    assert digest.pending_store_sync() == []  # legacy entry: never synced
    digest.add_entry("New", "1.0", "https://github.com/o/new", "A Switch port.", platform="Switch")
    pending = digest.pending_store_sync()
    assert [e["release_url"] for e in pending] == ["https://github.com/o/new"]

    gh = FakeGh([])
    outcomes = await ss.sync_pending_digest_items(
        digest, run=gh, which=gh_present, fetch=no_page, ask=no_llm, exists=always_exists,
        load=load_with(gh), add=sm.add_manual_rows)
    assert outcomes == {"https://github.com/o/new": "added"}
    assert digest.pending_store_sync() == []  # decided -> done, not pending again

    # A later re-add of the same release keeps the done state (no second store check).
    digest.add_entry("New", "1.0", "https://github.com/o/new", "A Switch port.", platform="Switch")
    assert digest.pending_store_sync() == []
