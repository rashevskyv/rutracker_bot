"""State files are replaced whole: a failed write leaves the previous content and no temp files."""
import json

import pytest

from utils.atomic_io import atomic_open


def test_replaces_content_and_keeps_mode(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o664)
    with atomic_open(path) as f:
        json.dump({"a": 1}, f)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert path.stat().st_mode & 0o777 == 0o664
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_failed_write_keeps_previous_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("old", encoding="utf-8")
    with pytest.raises(ValueError):
        with atomic_open(path) as f:
            f.write("partial")
            raise ValueError("boom")
    assert path.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_collector_refuses_unreadable_state(tmp_path):
    import collect_homebrew_updates as chu
    path = tmp_path / "hb_state.json"
    path.write_text('{"https://api.github.com/repos/a/b": {"comm_da', encoding="utf-8")
    with pytest.raises(RuntimeError):
        chu.HomebrewUpdatesCollector._load_json(path, "state")


def test_collector_refuses_unreadable_registry(tmp_path):
    import collect_homebrew_updates as chu
    registry = tmp_path / "list_hb.json"
    registry.write_text('[{"app_name": "Ga', encoding="utf-8")
    collector = chu.HomebrewUpdatesCollector(list_path=str(registry), state_path=str(tmp_path / "hb_state.json"))
    with pytest.raises(RuntimeError):
        collector.load_homebrew_list()


def test_unreadable_posted_links_stops_instead_of_reposting(monkeypatch, tmp_path):
    import main
    path = tmp_path / "posted_links.json"
    path.write_text('{"https://rutracker.org/forum/viewtopic.php?t=1": "2026-', encoding="utf-8")
    monkeypatch.setattr(main, "POSTED_LINKS_FILE", str(path))
    with pytest.raises(RuntimeError):
        main.load_posted_links()
