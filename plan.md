# План додавання нових ручних релізів (v0.6.45)

Цей план описує процес завантаження ручних релізів з Gist, додавання 3 нових портів від автора `ChanseyIsTheBest` до `manual_releases.json` та вивантаження оновленого стану в Gist.

## Пропоновані зміни

### 1. Актуалізація бази даних ручних релізів
- [x] Завантажити найновіший стан бази даних з Gist за допомогою `python sync_gist_state.py download`.
- [x] Додати нові записи для 3 репозиторіїв `ChanseyIsTheBest` (`zookeeperdx_nx`, `badpiggies_nx`, `pvz_fusion_en_nx`) у файл `data/manual_releases.json` з прапорцем `"processed": false`.
- [x] Завантажити оновлену базу даних в Gist за допомогою `python sync_gist_state.py upload`.

### 2. Версіонування та документація
- [x] Оновити `CHANGELOG.md` (англійською мовою), зафіксувавши версію `v0.6.45`.
- [x] Оновити `task.md`, `walkthrough.md` та `plan.md` (українською мовою).
- [x] Виконати git commit та створити новий тег `v0.6.45`.
