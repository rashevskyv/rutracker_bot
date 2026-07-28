# План інтеграції FlareSolverr для обходу Cloudflare

Цей план описує додавання підтримки FlareSolverr для вирішення JavaScript Challenge від Cloudflare при парсингу сторінок роздач RuTracker.

## Покрокові зміни

### 1. Конфігурація (`core/settings_loader.py` та `config/settings.json`)
- Додати параметр `FLARESOLVERR_URL` в `config/settings.json` (за замовчуванням `"http://localhost:8191/v1"`).
- Зчитувати `FLARESOLVERR_URL` у `core/settings_loader.py`.

### 2. Інтеграція у парсер (`parsers/tracker_parser.py`)
- Створити допоміжну функцію `fetch_via_flaresolverr(url: str)` для відправки POST-запиту до FlareSolverr API (`http://localhost:8191/v1`).
- У функції `fetch_page_content(url)`:
  - Спершу виконувати швидкий запит через `curl_cffi`.
  - Якщо `status_code == 403` або у відповіді виявлено сторінку Cloudflare ("Just a moment..."), виконувати резервний запит через FlareSolverr.
  - Якщо FlareSolverr повернув новий cookie `cf_clearance`, зберегти його в пам'яті для подальших запитів.

### 3. Документація та README (`README.md`, `CHANGELOG.md`)
- Оновити `README.md` з описом налаштування та використання FlareSolverr для роботи бота на сервері.
- Додати запис про зміни в `CHANGELOG.md`.

## Перевірка
- Перевірити коректність імпорту та обробку помилок, якщо FlareSolverr недоступний.
