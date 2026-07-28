# Walkthrough — Інтеграція FlareSolverr для обходу Cloudflare (v0.6.60)

У цьому випуску додано автоматичну обробку та обхід JavaScript Challenge від Cloudflare (*Just a moment...*) при завантаженні сторінок топіків RuTracker.

## Внесені зміни

### 1. Налаштування конфігурації
- **[settings.json](file:///d:/git/dev/rutracker_bot/config/settings.json):** Додано константу `"FLARESOLVERR_URL": "http://localhost:8191/v1"`.
- **[settings_loader.py](file:///d:/git/dev/rutracker_bot/core/settings_loader.py):** Експортовано змінну `FLARESOLVERR_URL` з параметрів.

### 2. Автоматичний обхід у парсері
- **[tracker_parser.py](file:///d:/git/dev/rutracker_bot/parsers/tracker_parser.py):** 
  - Реалізовано асинхронну функцію `fetch_via_flaresolverr(url)`, яка відправляє POST-запит до локального сервера FlareSolverr.
  - Оновлено `fetch_page_content(url)`: при отриманні `HTTP 403` або виявленні повідомлення Cloudflare (*Just a moment...*) запит автоматично повторюється через FlareSolverr.
  - Усі отримані куки (зокрема `cf_clearance`) автоматично додаються до `RUTRACKER_COOKIES` у пам'яті для оптимізації подальших запитів.

### 3. Документація та версіонування
- **[README.md](file:///d:/git/dev/rutracker_bot/README.md):** Додано інструкцію з розгортання FlareSolverr в Docker на сервері.
- **[CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md):** Додано опис релізу **`v0.6.60`**.

---

## Результати тестування

1. **Імпорт та ініціалізація:**
   Успішно перевірено завантаження конфігурації `FLARESOLVERR_URL = http://localhost:8191/v1`.
2. **Перевірка блокування Cloudflare:**
   У разі виявлення `HTTP 403` парсер переходить до використання `fetch_via_flaresolverr`, корректно обробляє відповідь або помилку з'єднання при відсутності сервера.
