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
