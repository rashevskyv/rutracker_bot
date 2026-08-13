# План переходу на VitaForge / VitaDBtoo (v0.6.66)

Цей план описує заміну відключеного бекенду Vita Homebrew Browser (VitaDB) на сучасну базу даних **VitaForge** / **VitaDBtoo** (`DrDecki/VitaDBtoo-db`) у Phase 1d збирача оновлень [collect_homebrew_updates.py](file:///d:/git/dev/rutracker_bot/collect_homebrew_updates.py).

## Покрокові зміни

### 1. Оновлення ендпоінтів та протоколу збору
- [x] Оновити `VITADB_ENDPOINTS` та `VITA_CATEGORIES` у [collect_homebrew_updates.py](file:///d:/git/dev/rutracker_bot/collect_homebrew_updates.py).
- [x] Змінити HTTP метод у `collect_vitadb_updates()` з POST на GET.
- [x] Оновити логування та мітки на `VitaForge/VitaDBtoo`.

### 2. Тестування та перевірка збору
- [x] Перевірити коректне зчитування та парсинг усіх категорій (`PSVita`, `PSVita Plugin`, `PSVita PC Tool`, `PSP`).
- [x] Запустити тести паралельно (`python -m pytest test_digest_runner.py test_gist_config.py test_manual_merge.py`).

### 3. Документація та версіонування
- [x] Оновити [README.md](file:///d:/git/dev/rutracker_bot/README.md) та [GEMINI.md](file:///d:/git/dev/rutracker_bot/GEMINI.md).
- [x] Оновити [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md) (версія `v0.6.66`).
- [x] Оновити [task.md](file:///d:/git/dev/rutracker_bot/task.md) та [walkthrough.md](file:///d:/git/dev/rutracker_bot/walkthrough.md).
