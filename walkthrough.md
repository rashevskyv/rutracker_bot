# Звіт про виконану роботу: Інтеграція VitaForge / VitaDBtoo (v0.6.66)

## Огляд задачі

31 липня 2026 року оригінальний бекенд сервісу **VitaDB** (на `rinnegatamante.eu`), який використовувався клієнтом **Vita Homebrew Browser (VHBB)**, припинив свою роботу і повертає порожні дані (`[]`).

На заміну полеглому VHBB спільнотою було створено сучасний хомбрю-браузер **VitaForge** ([josephinoo/vitaForge](https://github.com/josephinoo/vitaForge)), який використовує базу даних **VitaDBtoo** ([DrDecki/VitaDBtoo-db](https://github.com/DrDecki/VitaDBtoo-db)).

---

## Звідки VitaForge бере дані та формат API

1. **Джерело даних**:
   - Каталог **VitaDBtoo** (`DrDecki/VitaDBtoo-db`) — це збережена та щоденно оновлювана база даних застосунків, плагінів, ПК-інструментів та PSP-хомбрю.
   - Дані надаються як статичні JSON-файли через GitHub / GitHub Pages:
     - `https://raw.githubusercontent.com/DrDecki/VitaDBtoo-db/main/apps.json` — PS Vita Homebrew застосунки та ігри (1030+ записів).
     - `https://raw.githubusercontent.com/DrDecki/VitaDBtoo-db/main/preserved/plugins.json` — PS Vita плагіни (124+ записи).
     - `https://raw.githubusercontent.com/DrDecki/VitaDBtoo-db/main/preserved/tools.json` — ПК-утиліти для PS Vita (33+ записи).
     - `https://raw.githubusercontent.com/DrDecki/VitaDBtoo-db/main/psp_apps.json` — PSP Homebrew застосунки (127+ записів).
   - Також існує REST API бекенд VitaForge `https://vitaforge.josephinoo.dev/api/v1` (який синхронізує VitaDBtoo + NPS, проте вимагає обов'язкових заголовків клієнта `X-Client-ID` та має рейт-ліміти).

2. **Формат записів**:
   - Зберігає 100% сумісність із полями VitaDB:
     `id`, `name`, `version`, `author`, `date` (формат `YYYY-MM-DD`), `status`, `source`, `release_page`, `url`, `description`, `long_description`, `changelog`.
   - Запити виконуються методом **GET** (замість старого порожнього POST у VitaDB).
   - Ідентифікатори `id` збережено без змін (наприклад, `534` для Noboru), завдяки чому наявна історія в `data/vitadb_state.json` (`vita-hb:{id}`, `vita-plugin:{id}`, `vita-tool:{id}`) зберігається і плавно продовжує роботу без помилкових повторних сповіщень.

---

## Впроваджені зміни

### 1. Збирач оновлень [collect_homebrew_updates.py](file:///d:/git/dev/rutracker_bot/collect_homebrew_updates.py)
- **Оновлено `VITADB_ENDPOINTS`**: налаштовано прямі GET URL на `apps.json`, `preserved/plugins.json`, `preserved/tools.json`, `psp_apps.json`.
- **Розширено `VITA_CATEGORIES`**: додано підтримку категорії `PSP`.
- **Оновлено `collect_vitadb_updates()`**:
  - Метод HTTP-запитів змінено з `self.session.post` на `self.session.get` із таймаутом і заголовками `BROWSER_HEADERS`.
  - Оновлено логування та мітки на `VitaForge/VitaDBtoo`.
  - Додано підтримку префікса `vita-psp` для PSP-застосунків.

### 2. Документація та версіонування
- Оновлено [README.md](file:///d:/git/dev/rutracker_bot/README.md) та [GEMINI.md](file:///d:/git/dev/rutracker_bot/GEMINI.md) з описом нової архітектури джерел Phase 1d.
- Оновлено [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md) (версія `v0.6.66`).
- Оновлено [plan.md](file:///d:/git/dev/rutracker_bot/plan.md) та [task.md](file:///d:/git/dev/rutracker_bot/task.md).

---

## Результати тестування

1. **Тестове завантаження Phase 1d**:
   - Успішно завантажено та розпарсено 1033 записів PSVita, 124 плагіни, 33 ПК-інструменти та 127 PSP застосунків (покриття 618 GitHub репозиторіїв).
   - Усі поля, дати релізів, посилання на завантаження та changelog'и коректно обробляються.
2. **Модульні тести**:
   - `python -m pytest test_digest_runner.py test_gist_config.py test_manual_merge.py` — 8/8 тестів пройдено успішно.
