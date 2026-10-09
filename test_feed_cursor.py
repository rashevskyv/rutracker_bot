"""Feed cursor: entries are selected by feed update time, so an updated last topic cannot hide newer ones."""
import time
from unittest.mock import AsyncMock, Mock

import feedparser
import pytest

from parsers import feed_handler

T0 = 1_760_000_000


def feed_entry(n, ts):
    return feedparser.FeedParserDict(link=f"https://rutracker.org/forum/viewtopic.php?t={n}", updated_parsed=time.gmtime(ts))


def mock_feed(monkeypatch, entries):
    response = Mock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    response.raise_for_status = Mock()
    response.text = AsyncMock(return_value="<feed/>")
    session = Mock()
    session.get = Mock(return_value=response)
    monkeypatch.setattr(feed_handler, "get_session", lambda: session)
    parsed = Mock(bozo=False, entries=entries)
    monkeypatch.setattr(feed_handler.feedparser, "parse", lambda text: parsed)


@pytest.mark.asyncio
async def test_updated_last_topic_does_not_hide_newer_entries(monkeypatch):
    # A was processed at T0; then B appeared and A was updated again, moving above B.
    a_updated, b = feed_entry(1, T0 + 200), feed_entry(2, T0 + 100)
    mock_feed(monkeypatch, [a_updated, b, feed_entry(3, T0 - 100)])
    new = await feed_handler.get_new_feed_entries("feed", a_updated["link"], float(T0))
    assert [e["link"] for e in new] == [b["link"], a_updated["link"]]


@pytest.mark.asyncio
async def test_falls_back_to_link_cursor_without_time(monkeypatch):
    entries = [feed_entry(1, T0 + 200), feed_entry(2, T0 + 100), feed_entry(3, T0)]
    mock_feed(monkeypatch, entries)
    new = await feed_handler.get_new_feed_entries("feed", entries[1]["link"], None)
    assert [e["link"] for e in new] == [entries[0]["link"]]


def test_time_cursor_round_trips_and_never_moves_back(tmp_path):
    path = str(tmp_path / "last_entry_time.txt")
    assert feed_handler.read_last_entry_time(path) is None
    feed_handler.write_last_entry_time(path, T0 + 10)
    feed_handler.write_last_entry_time(path, T0)
    assert feed_handler.read_last_entry_time(path) == T0 + 10
