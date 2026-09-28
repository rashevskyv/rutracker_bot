# Завдання: додавання ручного релізу Need for Speed: Most Wanted (v0.7.55)

- [x] Завантажити актуальний стан `manual_releases.json` із віддаленого GitHub Gist.
- [x] Отримати метадані релізу `https://github.com/StevensND/nfsmw-nx` (`v1.0.0`).
- [x] Додати реліз `Need for Speed: Most Wanted (StevensND)` у `data/manual_releases.json` з описом українською мовою та статусом `processed: false`.
- [x] Вивантажити оновлену базу (273 записи) назад у GitHub Gist через `sync_gist_state.py upload`.
- [x] Верифікувати успішність збереження та злиття на Gist повторним завантаженням.
- [x] Прогнати тести у паралельному режимі (`pytest -n auto`: 106 passed).
