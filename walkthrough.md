# Результати виконання — Додавання нових ручних релізів (v0.6.58)

Завантажено свіжий стан бази даних з Gist та додано 4 нові ручні релізи (3 програми та 1 гру) у `data/manual_releases.json` з прапорцем `"processed": false`. Зміни примусово вивантажено у Gist (`python sync_gist_state.py upload -f`).

---

## Внесені зміни (v0.6.58)

### 1. Синхронізація з Gist
- Виконано команду `python sync_gist_state.py download` для завантаження актуальних даних з Gist.

### 2. Додавання 4 нових релізів (`data/manual_releases.json`)
До масиву ручних релізів додано наступні записи із прапорцем `"processed": false`:
- **`NX-torrent-player (shodowlo)`** (`v0.1.1`): Медіаплеєр та клієнт Stremio з підтримкою торрент-стрімінгу для Nintendo Switch (`https://github.com/shodowlo/NX-torrent-player/releases/tag/v0.1.1`).
- **`PipenSX (i3sey)`** (`1.1.1`): Кастомний магазин та оновлювач хоумбрю додатків для консолі Nintendo Switch (`https://github.com/i3sey/pipensx/releases/tag/1.1.1`).
- **`TorrentShopNX (Langegen)`** (`2.1`): Додаток TorrentShopNX для перегляду та завантаження торрент-вмісту безпосередньо на Nintendo Switch (`https://github.com/Langegen/TorrentShopNX/releases/tag/2.1`).
- **`Zelda Oni Link Begins (worthis)`** (`1.1`): Порт фанатської гри Zelda: Oni Link Begins на оновленому рушії для Nintendo Switch (`https://github.com/worthis/ZeldaOLB-new-engine/releases/tag/1.1`).

### 3. Синхронізаційне вивантаження у Gist
- Запущено `python sync_gist_state.py upload -f` для примусового збереження оновленого стану у Gist.

### 4. Версіонування та документація
- Версію проекту підвищено до **`v0.6.58`**.
- Оновлено документацію у файлах [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md), [task.md](file:///d:/git/dev/rutracker_bot/task.md), [plan.md](file:///d:/git/dev/rutracker_bot/plan.md) та [walkthrough.md](file:///d:/git/dev/rutracker_bot/walkthrough.md).

---

## Перевірка та результат

- Файл `data/manual_releases.json` перевірено на валідність JSON.
- Успішно виконано примусове вивантаження в Gist (`Upload successful`).
