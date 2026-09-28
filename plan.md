# План: додавання ручного релізу Need for Speed: Most Wanted (v0.7.55)

## Мета

Витягнути актуальний стан ручних релізів із віддаленого сховища Gist, додати свіжий нативний порт `Need for Speed: Most Wanted (2005)` від StevensND для Nintendo Switch та синхронізувати оновлену базу назад у Gist.

## Реалізація й перевірка

1. [x] Завантажити актуальний `manual_releases.json` із Gist за допомогою `python sync_gist_state.py download manual_releases.json`.
2. [x] Отримати дані про реліз `https://github.com/StevensND/nfsmw-nx` (`v1.0.0`, тег, дату, опис).
3. [x] Додати структурований запис у `data/manual_releases.json` із українським описом, категорією `Switch` і статусом `processed: false`.
4. [x] Вивантажити базу на Gist через `python sync_gist_state.py upload manual_releases.json`.
5. [x] Виконати контрольне завантаження для підтвердження збереження даних (273 записи).
6. [x] Перевірити працездатність тестів (`pytest -n auto`: 106 passed).
