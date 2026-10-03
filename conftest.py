"""Shared pytest guard: tests must never reach the production Gist or write into the live data/ directory."""
import pytest

# Module-level state paths that point into data/; every test gets them redirected to its own temp dir.
LIVE_STATE_PATHS = {
    "send_eshop_deals.STATE_FILE": "eshop_posted_deals.json",
    "send_eshop_deals.SHOWCASE_FILE": "eshop_active_showcase.json",
    "send_eshop_deals.LAST_RUN_FILE": "last_eshop_deals_run.json",
    "services.eshop.region_price_service.CACHE_FILE": "eshop_region_prices_cache.json",
}


def _blocked(*args, **kwargs):
    raise AssertionError("test tried to reach the production Gist")


@pytest.fixture(autouse=True)
def _isolate_live_state(monkeypatch, tmp_path):
    # sync_gist_state is the only module that talks to the Gist API, so blocking it here covers every caller.
    monkeypatch.setattr("sync_gist_state.upload_state", _blocked)
    monkeypatch.setattr("sync_gist_state.download_state", _blocked)
    # A sync_gist_state.py subprocess inherits this and targets a Gist that does not exist.
    monkeypatch.setenv("GIST_ID", "pytest-no-such-gist")
    for target, filename in LIVE_STATE_PATHS.items():
        monkeypatch.setattr(target, str(tmp_path / filename))
