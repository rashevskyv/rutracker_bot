# План: виключити інфраструктурні репозиторії aks796 (v0.7.61)

- [x] Сухий прогін першого обходу `aks796` (лише читання): 17 із 22 репозиторіїв проходять відбір, 5 із них — бібліотеки та рантайми.
- [x] Додати `SKIP_REPOS` і перевірку на початку циклу репозиторіїв у `collect_custom_releases.py`.
- [x] Додати `test_custom_releases_collector.py`: `libnx32` не потрапляє в чергу, `sonic_allstars_nx` потрапляє.
- [x] Оновити списки авторів та опис збирача в `README.md`, `GEMINI.md`, `run_custom_collector.bat`, `run_custom_collector.sh`.
- [x] `pytest -n auto`: 110 passed. Зміни не закомічено.

## Попередній план

# План: ручний реліз NFS Underground 2 (v0.7.60)

- [x] Download `manual_releases.json` перед змінами.
- [x] Перевірити актуальний реліз `antoxa2584x/nfsu2-sw`: `v0.3.5`.
- [x] Додати запис для Switch з українським описом і `processed: false`, виконати upload.
- [x] Перевірити запис безпосередньо у Gist: 280 записів, noJMe збережено.

## Попередній план

# План: ручний запис noJMe (v0.7.59)

- [x] Завантажити `manual_releases.json` із Gist перед змінами.
- [x] Перевірити GitHub API та README: релізів немає, Switch-версія `switchui` зазначена.
- [x] Додати `noJMe (corax89)` як `dev (6da353a)` зі статусом `processed: false`.
- [x] Вивантажити список і перевірити запис безпосередньо у Gist: 279 записів.

## Попередній план

# План: моніторинг репозиторіїв aks796 (v0.7.58)

- [x] Перевірити потік збору та публічні репозиторії автора через GitHub API.
- [x] Додати `aks796` до наявного `TARGET_USERS` без зміни фільтрів.
- [x] Перевірити синтаксис, шість авторів і обхід `TARGET_USERS` через AST у WSL; `git diff --check` пройдено.
- [x] Оновити документи для `v0.7.58`; зміни готові до коміту.

## Попередній план

# План: додавання ручного релізу Far Cry (NearChuckle NX) (v0.7.57)

## Мета

Синхронізувати актуальний реєстр ручних релізів із сервером (GitHub Gist), додати новий порт Far Cry для Nintendo Switch від `artslay` та вивантажити оновлену базу назад у Gist.

## Реалізація

1. [x] Завантажити актуальний стан `manual_releases.json` із віддаленого Gist-сховища за допомогою `sync_gist_state.py download manual_releases.json`.
2. [x] Отримати метадані релізу `https://github.com/artslay/NearChuckle_nx/releases` (`1.0.1`).
3. [x] Додати реліз `Far Cry (NearChuckle NX) (artslay)` у `data/manual_releases.json` з українським описом та статусом `processed: false`.
4. [x] Вивантажити оновлену базу (278 записів) назад у GitHub Gist через `sync_gist_state.py upload manual_releases.json`.
5. [x] Верифікувати успішність збереження та злиття на Gist повторним завантаженням.

## Перевірка й доставка

- [x] Прогнати тести у паралельному режимі (`pytest -n auto`: 109 passed).
- [x] Оновити CHANGELOG.md до `v0.7.57`, walkthrough.md, task.md та plan.md.
- [x] Створити коміт та тег `v0.7.57`.
