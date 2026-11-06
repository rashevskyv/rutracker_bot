"""SteamGridDB covers: exact names only, every exact match is tried."""
import pytest

from services import steamgriddb


def test_candidate_names_drop_tags_and_non_latin_names():
    assert steamgriddb.candidate_names("BANG! BANG! BANDITS バン！バン！バンディッツ [Nintendo Switch 2]") == ["BANG! BANG! BANDITS"]
    assert steamgriddb.candidate_names("Escape From Mystwood Mansion - Feral Edition (порт)") == \
        ["Escape From Mystwood Mansion - Feral Edition", "Escape From Mystwood Mansion", "Feral Edition"]
    assert steamgriddb.candidate_names("Сборник игр") == []
    assert steamgriddb.normalize_name("Donkey Kong: Bananza") == steamgriddb.normalize_name("donkey kong bananza")


@pytest.mark.asyncio
async def test_cover_from_the_exact_match_that_has_landscape_grids(monkeypatch):
    calls = []

    async def api(path, key):
        calls.append(path)
        if path.startswith("/search/"):
            return [{"id": 1, "name": "Orbitals 2"}, {"id": 2, "name": "Orbitals"}, {"id": 3, "name": "Orbitals"}]
        return [] if path.startswith("/grids/game/2?") else [{"url": "https://cdn/x.png"}]

    monkeypatch.setattr(steamgriddb, "_api", api)
    assert await steamgriddb.find_landscape_cover("Orbitals [NUP]", "key") == "https://cdn/x.png"
    # "Orbitals 2" is another game; game 2 has no landscape grids, game 3 has
    assert [p.split("?")[0] for p in calls] == ["/search/autocomplete/Orbitals", "/grids/game/2", "/grids/game/3"]
    assert await steamgriddb.find_landscape_cover("Orbitals", None) is None
