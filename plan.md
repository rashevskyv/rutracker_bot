# План: Виправлення помилки HTTP 403 RuTracker Cloudflare та документування середовища Ubuntu Server (v0.7.52)

## Опис проблеми
Бот на продакшн Ubuntu Server натрапив на Cloudflare challenge (HTTP 403 "Just a moment...") під час завантаження роздачі `https://rutracker.org/forum/viewtopic.php?t=5734418`. 
Через те, що фолбек FlareSolverr або був недоступний (контейнер не запущений), або не зміг пройти перевірку, бот здійснив 15 повторних спроб без зміни стану та надіслав загальну неінформативну помилку в Telegram: `Failed to fetch page content (HTTP error 403 after 15 attempts)`.

Користувач нагадав: **запуск сервера виконується на Ubuntu Server**. Це середовище має бути чітко зафіксовано в системній документації (`GEMINI.md` та `README.md`).

## Етапи реалізації

1. **Документування архітектури середовища Ubuntu Server**
   - [x] Додати розділ `Server Deployment Environment (Ubuntu Server)` у `GEMINI.md`.
   - [x] Оновити інструкції в `README.md` щодо запуску, моніторингу та автоперезапуску Docker-контейнера FlareSolverr на Ubuntu Server.

2. **Покращення діагностики та обробки помилок у `parsers/tracker_parser.py`**
   - [x] Зберігати та повертати точну причину невдачі FlareSolverr (наприклад, `ConnectionRefusedError`, таймаут Turnstile, або помилка статусу).
   - [x] Впровадити режим **Fail-Fast**: якщо FlareSolverr недоступний (порт 8191 не відповідає), негайно переривати 15 безглуздих повторів і генерувати зрозумілу помилку з точною командою для запуску Docker на Ubuntu Server.
   - [x] Синхронізувати `User-Agent` із рішення FlareSolverr, щоб майбутні запити з `cf_clearance` не відхилялися Cloudflare.
   - [x] Додати пряму перевірку дзеркала `rutracker.net` через `curl_cffi` перед викликом FlareSolverr.
   - [x] Додати додаткову діагностичну інформацію у повідомлення Telegram про помилку.

3. **Тестування**
   - [x] Додати юніт-тести для перевірки fail-fast поведінки, збереження причини помилки FlareSolverr та User-Agent синхронізації (`test_tracker_flaresolverr.py`).
   - [x] Запустити повний набір тестів паралельно (`pytest -n auto` — 93 passed).

4. **Оновлення документації та версіонування**
   - [x] Ітерувати версію до `v0.7.52`.
   - [x] Оновити `CHANGELOG.md`, `task.md` та `walkthrough.md`.
