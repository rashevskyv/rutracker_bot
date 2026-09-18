# Walkthrough: Виправлення помилки HTTP 403 RuTracker Cloudflare та фіксація середовища Ubuntu Server (v0.7.52)

У версії `v0.7.52`:
1. **Зафіксовано архітектуру середовища розгортання**:
   - У `GEMINI.md` та `README.md` чітко задокументовано, що продакшн-сервер бота розгорнуто та запущено на **Ubuntu Server** (Linux).
   - Описано вимоги до Docker-стеку для обходу Cloudflare (контейнер `flaresolverr` на порту `8191`).
   - Додано готові команди для діагностики, моніторингу та тестування на сервері.

2. **Покращено обробку Cloudflare challenge (HTTP 403) та FlareSolverr у `parsers/tracker_parser.py`**:
   - **Fail-Fast при відсутності сервісу**: якщо контейнер FlareSolverr не запущений на Ubuntu Server (помилка підключення до `localhost:8191`), бот не витрачає час на 15 повторів, а негайно перериває спроби та надсилає в Telegram конкретну команду для підняття Docker-контейнера.
   - **Діагностичні повідомлення про помилку**: точна причина відмови FlareSolverr (`last_flaresolverr_error`) тепер фіксується та додається до тексту помилки в Telegram замість сухого "HTTP error 403 after 15 attempts".
   - **Прямий фолбек на дзеркало**: перед активацією важкого запиту через FlareSolverr парсер намагається виконати прямий запит до дзеркала `rutracker.net`.
   - **Синхронізація User-Agent**: User-Agent, з яким FlareSolverr успішно розв'язав challenge, зберігається (`FLARESOLVERR_USER_AGENT`) і автоматично передається у наступні запити для підтримки валідності токена `cf_clearance`.

3. **Безпека стану куків у `core/settings_loader.py`**:
   - `RUTRACKER_COOKIES` завжди ініціалізується як змінний словник `dict` (`settings.get('RUTRACKER_COOKIES') or {}`), завдяки чому отримані куки динамічно зберігаються в спільній сесії.

4. **Тестування**:
   - Створено набір юніт-тестів `test_tracker_flaresolverr.py` (5 тестів):
     - `test_flaresolverr_unconfigured`
     - `test_flaresolverr_connection_error`
     - `test_flaresolverr_success_updates_cookies_and_ua`
     - `test_fetch_page_content_fail_fast_on_unreachable_flaresolverr`
     - `test_fetch_page_content_mirror_success`
   - Усі 93 тести проєкту виконано паралельно (`pytest -n auto`) — 100% успішно.

---

## Що потрібно виконати на вашому Ubuntu Server зараз:
Помилка `HTTP error 403 after 15 attempts` виникає через те, що на сервері RuTracker видає перевірку Cloudflare, а сервіс FlareSolverr зупинений або не запущений.

1. **Перевірте стан контейнера FlareSolverr**:
   ```bash
   docker ps -a | grep flaresolverr
   ```
2. **Якщо контейнер зупинений, запустіть його**:
   ```bash
   docker start flaresolverr
   ```
3. **Якщо контейнер відсутній, створіть і запустіть його з автоперезапуском**:
   ```bash
   docker run -d --name=flaresolverr -p 8191:8191 -e LOG_LEVEL=info --restart=unless-stopped ghcr.io/flaresolverr/flaresolverr:latest
   ```
4. **Перевірте працездатність**:
   ```bash
   curl -s -X POST http://localhost:8191/v1 -H "Content-Type: application/json" -d '{"cmd":"request.get","url":"https://rutracker.org"}'
   ```
