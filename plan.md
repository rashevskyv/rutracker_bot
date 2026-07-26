# План реалізації: Завантаження та додавання нових ручних релізів (v0.6.58)

## Опис завдання
Завантажити актуальний стан ручних релізів з Gist та додати 4 нові релізи (3 програми: NX-torrent-player, PipenSX, TorrentShopNX та 1 гра: Zelda Oni Link Begins) у `data/manual_releases.json` з прапорцем `"processed": false`, після чого виконати примусове вивантаження стану у Gist (`python sync_gist_state.py upload -f`).

## Кроки виконання:
1. [x] Завантажити найновіший стан бази даних з Gist за допомогою `python sync_gist_state.py download`.
2. [x] Отримати та перевірити метадані 4 релізів з GitHub (версії, посилання, дати, описи українською).
3. [x] Додати записи 4 нових релізів до `data/manual_releases.json` із прапорцем `"processed": false`.
4. [x] Виконати примусове синхронізаційне вивантаження локального стану у Gist (`python sync_gist_state.py upload -f`).
5. [x] Оновити документацію (`CHANGELOG.md`, `README.md`, `GEMINI.md`), `plan.md`, `task.md` та `walkthrough.md` з ітерацією версії до `v0.6.58`.
6. [x] Закомітити зміни локально та створити тег `v0.6.58`.
