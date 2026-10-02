# Завдання: ізоляція тестів від Gist і коректне обрізання описів (v0.7.62)

- [x] `pytest` не звертається до продакшн-Gist і не пише в живі `data/` та `config/` (`conftest.py`, `test_gist_config.py`).
- [x] `limit_to_sentences` обрізає опис на кінці речення, а не на крапці всередині версії (`digest/homebrew.py`).
- [x] Не змінювати логіку злиття в `sync_gist_state.py`, не писати в `data/` та Gist; перевірити повним прогоном і порівнянням ревізій Gist до та після.
- [x] Повернути в Gist записи noJMe та NFS Underground 2 (опис NFS Underground 2 скорочено до 211 символів) і стан eShop, затертий тестами.

## Попереднє завдання

# Завдання: виключити інфраструктурні репозиторії aks796 (v0.7.61)

- [x] Збирач не ставить у чергу `android32`, `libnx32`, `mesa-switch32`, `mesa32`, `ffmpeg32` (`SKIP_REPOS` у `collect_custom_releases.py`).
- [x] Додати `aks796` до списків авторів у `README.md`, `GEMINI.md`, `run_custom_collector.bat`, `run_custom_collector.sh`.
- [x] Не змінювати LLM-фільтр і маркери назв, не чіпати `data/` та Gist; перевірити новим тестом і `pytest -n auto`.

## Попереднє завдання

# Завдання: ручний реліз NFS Underground 2 (v0.7.60)

- [x] Download → додавання NFS Underground 2 v0.3.5 → upload.
- [x] Перевірити запис у віддаленому Gist і збереження noJMe.
- [x] Оновити CHANGELOG і документи для `v0.7.60`.

## Попереднє завдання

# Завдання: ручний запис noJMe (v0.7.59)

- [x] Download → додавання noJMe → upload для `manual_releases.json`.
- [x] Перевірити єдиний запис noJMe у віддаленому Gist та `processed: false`.
- [x] Оновити CHANGELOG і документи для `v0.7.59`.

## Попереднє завдання

# Завдання: моніторинг репозиторіїв aks796 (v0.7.58)

- [x] Додати автора `aks796` до автоматичного обходу репозиторіїв.
- [x] Перевірити зміну у WSL та `git diff --check`, підготувати коміт `v0.7.58`.

## Попереднє завдання

# Завдання: додавання ручного релізу Far Cry (NearChuckle NX) (v0.7.57)

- [x] Оновити `data/manual_releases.json` із віддаленого Gist-сховища (`python sync_gist_state.py download manual_releases.json`).
- [x] Отримати метадані релізу `https://github.com/artslay/NearChuckle_nx/releases` (`1.0.1`).
- [x] Додати реліз `Far Cry (NearChuckle NX) (artslay)` у `data/manual_releases.json` з описом українською мовою та статусом `processed: false`.
- [x] Вивантажити оновлену базу (278 записів) назад у GitHub Gist через `sync_gist_state.py upload manual_releases.json`.
- [x] Верифікувати успішність збереження та злиття на Gist повторним завантаженням.
- [x] Прогнати повний набір тестів у паралельному режимі (`pytest -n auto`: 109 passed).
- [x] Оновити документацію (CHANGELOG.md, plan.md, task.md, walkthrough.md) та зафіксувати версію `v0.7.57`.
