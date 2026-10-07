"""Regression tests for manual releases selection priority over automatic releases."""
import json
from unittest.mock import MagicMock

import add_release
import services.manual_releases as mr


def test_manual_releases_priority_selection(tmp_path, monkeypatch):
    """
    1. Place more than five automatic rows before manual rows.
    2. Verify manual rows are selected first and automatic rows fill remaining slots.
    3. Verify stable order within groups, the five-entry limit, and exclusion of processed/wrong-type rows.
    """
    manual_file = tmp_path / "manual_releases.json"
    monkeypatch.setattr(mr, "MANUAL_RELEASES_FILE", str(manual_file))

    # Mock digest managers
    mock_hb_manager = MagicMock()
    mock_daily_manager = MagicMock()
    monkeypatch.setattr(mr, "homebrew_digest_manager", mock_hb_manager)
    monkeypatch.setattr(mr, "digest_manager", mock_daily_manager)

    rows = [
        # 6 automatic homebrew rows placed first (no inbox_id)
        {"type": "homebrew", "app_name": "AutoHB1", "version": "1.0", "release_url": "https://x/auto1", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB2", "version": "2.0", "release_url": "https://x/auto2", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB3", "version": "3.0", "release_url": "https://x/auto3", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB4", "version": "4.0", "release_url": "https://x/auto4", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB5", "version": "5.0", "release_url": "https://x/auto5", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB6", "version": "6.0", "release_url": "https://x/auto6", "processed": False},
        # 3 manual homebrew rows placed after automatic rows (with non-empty inbox_id)
        {"type": "homebrew", "app_name": "ManualHB1", "version": "1.0", "release_url": "https://x/man1", "inbox_id": "id-1", "processed": False},
        {"type": "homebrew", "app_name": "ManualHB2", "version": "2.0", "release_url": "https://x/man2", "inbox_id": "id-2", "processed": False},
        {"type": "homebrew", "app_name": "ManualHB3", "version": "3.0", "release_url": "https://x/man3", "inbox_id": "id-3", "processed": False},
        # Row with already processed=True (must be excluded)
        {"type": "homebrew", "app_name": "ManualProcessed", "version": "0.9", "release_url": "https://x/proc", "inbox_id": "id-proc", "processed": True},
        # Row with wrong release_type (game instead of homebrew, must be excluded)
        {"type": "game", "title": "ManualGame", "url": "https://x/game", "inbox_id": "id-game", "processed": False},
        # Row with empty/whitespace inbox_id (treated as automatic, retains group order)
        {"type": "homebrew", "app_name": "AutoHBEmptyId", "version": "7.0", "release_url": "https://x/auto7", "inbox_id": "   ", "processed": False},
    ]
    manual_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    count = mr.process_manual_releases(release_type="homebrew")

    # Verify five-entry limit
    assert count == 5
    assert mock_hb_manager.add_entry.call_count == 5
    assert mock_daily_manager.add_entry.call_count == 0

    # Verify manual rows are selected first, automatic rows fill remaining slots,
    # and stable relative order within groups is preserved.
    added_apps = [call.kwargs["app_name"] for call in mock_hb_manager.add_entry.call_args_list]
    assert added_apps == ["ManualHB1", "ManualHB2", "ManualHB3", "AutoHB1", "AutoHB2"]

    # Verify stored JSON order is unchanged on disk
    file_on_disk = json.loads(manual_file.read_text(encoding="utf-8"))
    assert file_on_disk == rows


def test_status_displays_priority_order(capsys):
    """4. Verify status displays the same priority order."""
    manual_rows = [
        # Automatic rows placed first
        {"type": "homebrew", "app_name": "AutoHB1", "version": "1.0", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB2", "version": "2.0", "processed": False},
        {"type": "homebrew", "app_name": "AutoHB3", "version": "3.0", "processed": False},
        # Manual rows placed after automatic rows
        {"type": "homebrew", "app_name": "ManualHB1", "version": "1.0", "inbox_id": "id-1", "processed": False},
        {"type": "homebrew", "app_name": "ManualHB2", "version": "2.0", "inbox_id": "id-2", "processed": False},
        # Already processed manual row
        {"type": "homebrew", "app_name": "ManualHBProcessed", "version": "0.1", "inbox_id": "id-proc", "processed": True},
    ]
    inbox_rows = [
        {"inbox_id": "id-1", "app_name": "ManualHB1", "version": "1.0"},
        {"inbox_id": "id-2", "app_name": "ManualHB2", "version": "2.0"},
        {"inbox_id": "id-proc", "app_name": "ManualHBProcessed", "version": "0.1"},
    ]

    add_release.status(manual_rows, inbox_rows)
    captured = capsys.readouterr().out

    lines = [line.strip() for line in captured.splitlines() if line.strip()]
    assert "manual_releases.json: 5 pending of 6" in lines

    pending_lines = lines[lines.index("manual_releases.json: 5 pending of 6") + 1:]
    assert pending_lines == [
        "ManualHB1 1.0",
        "ManualHB2 2.0",
        "AutoHB1 1.0",
        "AutoHB2 2.0",
        "AutoHB3 3.0",
    ]


def test_prioritize_releases_helper():
    """Verify prioritize_releases unit contract."""
    entries = [
        {"app": "a1", "inbox_id": None},
        {"app": "m1", "inbox_id": "uuid-1"},
        {"app": "a2"},
        {"app": "m2", "inbox_id": "uuid-2"},
        {"app": "a3", "inbox_id": ""},
        {"app": "a4", "inbox_id": "   "},
    ]
    result = mr.prioritize_releases(entries)
    assert [e["app"] for e in result] == ["m1", "m2", "a1", "a2", "a3", "a4"]
