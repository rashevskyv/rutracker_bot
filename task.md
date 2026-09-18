# Завдання: Виправлення помилки HTTP 403 RuTracker Cloudflare та документування Ubuntu Server (v0.7.52)

## Виконані завдання
- [x] **Документування архітектури середовища Ubuntu Server**:
  - [x] Додано розділ `Server Deployment Environment (Ubuntu Server)` у `GEMINI.md`.
  - [x] Оновлено `README.md` із командами запуску, моніторингу та перевірки працездатності FlareSolverr через Docker на Ubuntu Server.
- [x] **Покращення обробки та діагностики Cloudflare/FlareSolverr у `parsers/tracker_parser.py`**:
  - [x] Додано фіксацію та збереження детальної причини відмови FlareSolverr (`last_flaresolverr_error` / `get_last_flaresolverr_error()`).
  - [x] Реалізовано Fail-Fast переривання: при недоступності сервісу FlareSolverr (connection refused) бот негайно зупиняє циклічні запити та викидає інформативне повідомлення з готовою Docker-командою для Ubuntu Server.
  - [x] Впроваджено прямий фолбек на дзеркало `rutracker.net` через `curl_cffi` перед зверненням до FlareSolverr.
  - [x] Синхронізація повернутого `userAgent` від FlareSolverr (`FLARESOLVERR_USER_AGENT`) у подальші HTTP-запити для збереження валідності `cf_clearance`.
  - [x] Увімкнено виведення детальної причини FlareSolverr у фінальний виняток `ValueError` для сповіщень Telegram.
- [x] **Безпека збереження куків**:
  - [x] `core/settings_loader.py`: ініціалізація `RUTRACKER_COOKIES` як mutable dict (`{}` за замовчуванням), що гарантує збереження динамічних куків у спільній сесії.
- [x] **Тестування**:
  - [x] Створено новий файл юніт-тестів `test_tracker_flaresolverr.py` (5 тестів для перевірки unconfigured, connection error, cookie/UA sync, fail-fast та direct mirror).
  - [x] Усі 93 тести проєкту успішно виконані у паралельному режимі (`pytest -n auto`).
- [x] **Оновлення релізу та документації**:
  - [x] Ітеровано версію програми до `v0.7.52`.
  - [x] Оновлено `CHANGELOG.md`, `plan.md`, `task.md` та `walkthrough.md`.
