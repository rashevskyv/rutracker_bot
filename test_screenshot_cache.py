"""Screenshots go to Telegram once; reposts and the next groups reuse their file_ids."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _photo(file_id):
    return SimpleNamespace(photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id=file_id)])


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 3])
async def test_screenshots_return_their_file_ids(monkeypatch, tmp_path, count):
    from services import telegram_sender
    paths = []
    for i in range(count):
        path = tmp_path / f"shot{i}.jpg"
        path.write_bytes(b"jpg")
        paths.append(str(path))
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=_photo("id0")),
                          send_media_group=AsyncMock(return_value=[_photo(f"id{i}") for i in range(count)]),
                          send_message=AsyncMock())
    monkeypatch.setattr(telegram_sender, "bot", bot)
    monkeypatch.setattr(telegram_sender.asyncio, "sleep", AsyncMock())
    files, file_ids = await telegram_sender._send_strategy_separate(1, None, "", None, None, paths)
    for f in files:
        f.close()
    assert file_ids == [f"id{i}" for i in range(count)]
    # A media group needs 2-10 items, so one screenshot goes as a photo
    assert (bot.send_photo.await_count, bot.send_media_group.await_count) == ((1, 0) if count == 1 else (0, 1))


@pytest.mark.asyncio
async def test_cached_file_ids_are_sent_as_is(monkeypatch):
    from services import telegram_sender
    bot = SimpleNamespace(send_media_group=AsyncMock(return_value=[_photo("a"), _photo("b")]), send_message=AsyncMock())
    monkeypatch.setattr(telegram_sender, "bot", bot)
    monkeypatch.setattr(telegram_sender.asyncio, "sleep", AsyncMock())
    files, file_ids = await telegram_sender._send_strategy_separate(1, None, "", None, None, ["AgACAgIa", "AgACAgIb"])
    assert files == [] and file_ids == ["a", "b"]
    assert [m.media for m in bot.send_media_group.await_args.kwargs["media"]] == ["AgACAgIa", "AgACAgIb"]


def test_screenshot_cache_round_trip(monkeypatch, tmp_path):
    import main
    monkeypatch.setattr(main, "SCREENSHOT_CACHE_FILE", str(tmp_path / "data" / "screenshot_file_ids.json"))
    assert main.load_screenshot_cache() == {}
    main.save_screenshot_file_ids("https://rutracker.org/forum/viewtopic.php?t=1", ["a", "b"])
    assert main.load_screenshot_cache() == {"https://rutracker.org/forum/viewtopic.php?t=1": ["a", "b"]}


@pytest.mark.asyncio
async def test_no_cover_means_no_placeholder(monkeypatch):
    from utils import telegram_utils
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(telegram_utils, "_try_download_image_tg", fetch)
    assert await telegram_utils.download_cover_image_tg(None) is None
    assert await telegram_utils.download_cover_image_tg("https://x.org/dead.jpg") is None
    assert fetch.await_count == 1
