"""Tests for RuTracker homebrew genre detection and screenshot bypass logic."""
import pytest
from parsers.tracker_parser import is_homebrew_genre


def test_is_homebrew_genre_from_genres_list():
    # English variations
    assert is_homebrew_genre(genres=["Homebrew"]) is True
    assert is_homebrew_genre(genres=["#Homebrew"]) is True
    assert is_homebrew_genre(genres=["homebrew", "Action"]) is True
    assert is_homebrew_genre(genres=["Home-Brew"]) is True
    assert is_homebrew_genre(genres=["Home brew"]) is True

    # Cyrillic variations
    assert is_homebrew_genre(genres=["Хоумбрю"]) is True
    assert is_homebrew_genre(genres=["#Хоумбрю"]) is True
    assert is_homebrew_genre(genres=["Хомбрю"]) is True
    assert is_homebrew_genre(genres=["хоум-брю"]) is True
    assert is_homebrew_genre(genres=["хоумбру"]) is True

    # Non-homebrew genres
    assert is_homebrew_genre(genres=["Action", "RPG"]) is False
    assert is_homebrew_genre(genres=["Platformer", "Adventure"]) is False
    assert is_homebrew_genre(genres=[]) is False
    assert is_homebrew_genre(genres=None) is False


def test_is_homebrew_genre_from_description():
    # Genre headers in description
    assert is_homebrew_genre(description="<b>Жанр:</b> Homebrew, Action\n<b>Год:</b> 2024") is True
    assert is_homebrew_genre(description="<b>Жанр:</b> #Homebrew\n<b>Язык:</b> ENG") is True
    assert is_homebrew_genre(description="<b>Жанр:</b> Хоумбрю\n<b>Разработчик:</b> Dev") is True
    assert is_homebrew_genre(description="<b>Жанр:</b> Хомбрю, Порт") is True
    assert is_homebrew_genre(description="<b>Genre:</b> Homebrew / Utility") is True
    assert is_homebrew_genre(description="<b>Жанр:</b> Action, Adventure, Homebrew") is True
    assert is_homebrew_genre(description="Жанр: хоум-брю") is True

    # Standalone hashtag in description
    assert is_homebrew_genre(description="Опис: Чудовий порт гри #Homebrew для Switch") is True
    assert is_homebrew_genre(description="Теги: #хоумбрю #switch") is True
    assert is_homebrew_genre(description="Теги: #хомбрю #game") is True

    # Non-homebrew descriptions
    assert is_homebrew_genre(description="<b>Жанр:</b> Action, RPG\n<b>Год:</b> 2024") is False
    assert is_homebrew_genre(description="<b>Genre:</b> Platformer\n<b>Language:</b> ENG") is False
    assert is_homebrew_genre(description="") is False
    assert is_homebrew_genre(description=None) is False


def test_is_homebrew_genre_from_title():
    assert is_homebrew_genre(title="Super Mario NX [Homebrew]") is True
    assert is_homebrew_genre(title="Portal NX (Хоумбрю) [Nintendo Switch]") is True
    assert is_homebrew_genre(title="Retro Game [Хомбрю]") is True
    assert is_homebrew_genre(title="Super Mario Odyssey [Nintendo Switch]") is False
    assert is_homebrew_genre(title="The Legend of Zelda: Tears of the Kingdom") is False


def test_is_homebrew_genre_all_empty():
    assert is_homebrew_genre() is False
    assert is_homebrew_genre(genres=[], description="", title="") is False



def test_find_screenshots_reads_only_the_screenshots_spoiler():
    from bs4 import BeautifulSoup
    from parsers.tracker_parser import find_screenshots
    thumb, link = "https://i1.fastpic.org/thumb/2026/1105/a3/abc.jpeg", "https://fastpic.org/view/1/2026/1105/abc.avif.html"
    shot = f'<a class="postLink" href="{link}"><var class="postImg" title="{thumb}"></var></a>'
    post = BeautifulSoup(
        f'<div><div class="sp-wrap"><div class="sp-head">Cкриншоты</div><div class="sp-body">{shot}{shot}'
        '<var class="postImg" title="https://x.org/bare.jpg"></var></div></div>'
        '<div class="sp-wrap"><div class="sp-head">Трейлер</div><div class="sp-body">'
        '<var class="postImg" title="https://x.org/no.jpg"></var></div></div></div>', "html.parser")
    assert find_screenshots(post) == [(thumb, link), ("https://x.org/bare.jpg", "https://x.org/bare.jpg")]


@pytest.mark.asyncio
@pytest.mark.parametrize("pages, expected", [
    # fastpic viewer: the thumbnail is on the page too, the original is the signed /big/ image
    (['<img src="https://i1.fastpic.org/preview/2026/1105/a3/abc.avif?md5=p"><img src="https://i1.fastpic.org/thumb/2026/1105/a3/abc.jpeg"><img src="https://i1.fastpic.org/big/2026/1105/a3/abc.avif?md5=x&amp;expires=1">'],
     "https://i1.fastpic.org/big/2026/1105/a3/abc.avif?md5=x&expires=1"),
    # fastpic error page first, the real page on the retry
    (['Could not connect to DB server', '<img src="https://i1.fastpic.org/big/2026/1105/a3/abc.avif?md5=x">'],
     "https://i1.fastpic.org/big/2026/1105/a3/abc.avif?md5=x"),
    # No original on any attempt: no screenshot rather than a thumbnail
    (['<img src="https://ads.example/banner.jpg"><img src="https://i1.fastpic.org/thumb/2026/1105/a3/abc.jpeg">'] * 3, None),
])
async def test_resolve_full_image_picks_the_original_from_the_viewer_page(monkeypatch, pages, expected):
    from parsers import tracker_parser
    pages = iter(pages)

    class Response:
        content_type = "text/html"
        def raise_for_status(self): pass
        async def text(self): return next(pages)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    monkeypatch.setattr(tracker_parser, "get_session", lambda: type("S", (), {"get": lambda self, url, timeout: Response()})())
    assert await tracker_parser.resolve_full_image(
        "https://i1.fastpic.org/thumb/2026/1105/a3/abc.jpeg", "https://fastpic.org/view/1/2026/1105/abc.avif.html", retry_delay=0) == expected


@pytest.mark.asyncio
async def test_resolve_full_image_keeps_bare_image_but_never_a_bare_thumbnail():
    from parsers.tracker_parser import resolve_full_image
    assert await resolve_full_image("https://x.org/shot.png", "https://x.org/shot.png") == "https://x.org/shot.png"
    thumb = "https://i1.imageban.ru/thumbs/2026.11.06/abc.png"
    assert await resolve_full_image(thumb, thumb) is None
