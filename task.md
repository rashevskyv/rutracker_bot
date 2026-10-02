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
