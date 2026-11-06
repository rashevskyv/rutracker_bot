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
    files, file_ids = await telegram_sender._send_strategy_separate(1, None, "", None, paths)
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
    files, file_ids = await telegram_sender._send_strategy_separate(1, None, "", None, ["AgACAgIa", "AgACAgIb"])
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


def _image(width, height):
    from io import BytesIO
    from PIL import Image
    image = BytesIO()
    Image.new("RGB", (width, height)).save(image, "PNG")
    image.seek(0)
    return image


@pytest.mark.asyncio
@pytest.mark.parametrize("cover_size, album", [((920, 430), True), ((600, 900), False)])
async def test_landscape_cover_goes_first_in_the_screenshots_album(monkeypatch, cover_size, album):
    from services import telegram_sender
    bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock(),
                          send_media_group=AsyncMock(return_value=[_photo("cover"), _photo("a"), _photo("b")]))
    monkeypatch.setattr(telegram_sender, "bot", bot)
    monkeypatch.setattr(telegram_sender, "IS_TEST_MODE", True)
    monkeypatch.setattr(telegram_sender, "TEST_GROUPS", [{"group_name": "t", "chat_id": -1, "language": "RU"}])
    monkeypatch.setattr(telegram_sender, "download_cover_image_tg", AsyncMock(return_value=_image(*cover_size)))
    monkeypatch.setattr(telegram_sender.asyncio, "sleep", AsyncMock())
    file_ids = await telegram_sender.send_to_telegram("Title", "https://x.org/c.png", "magnet:?", "Text", "https://x.org/t", ["AgACAgIa", "AgACAgIb"])
    media = bot.send_media_group.await_args.kwargs["media"]
    if album:
        # One album: the cover with the caption, then the screenshots; the cached ids are only the screenshots'
        assert bot.send_photo.await_count == 0 and len(media) == 3 and media[0].caption
        assert [m.media for m in media[1:]] == ["AgACAgIa", "AgACAgIb"]
    else:
        # A portrait cover goes alone with the caption, the screenshots follow as their own album
        assert bot.send_photo.await_count == 1 and [m.media for m in media] == ["AgACAgIa", "AgACAgIb"]
    assert file_ids == ["a", "b"]
