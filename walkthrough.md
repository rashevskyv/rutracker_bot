# Результати виконання — Додавання автора delsonazevedo та покращення логіки відстеження (v0.6.59)

У скрипті `collect_custom_releases.py` додано розробника `delsonazevedo` та реалізовано збереження часу останнього запуску (`last_run`) та стану відстеження авторів у файлі `data/custom_releases_state.json`.

---

## Внесені зміни (v0.6.59)

### 1. Додавання автора та збереження стану (`collect_custom_releases.py`)
- До списку відстежуваних авторів `TARGET_USERS` додано `delsonazevedo`.
- Реалізовано збереження та завантаження файлу стану `data/custom_releases_state.json`, який зберігає таймштамп `last_run` та історію авторів `authors`.

### 2. Диференційована часова логіка (Cutoff)
- **Для нових авторів**: якщо автор вперше доданий до стану, збираються його релізи за останні **3 тижні (21 день)**.
- **Для існуючих авторів**: збираються всі нові релізи з моменту останнього запуску (`last_run`).

### 3. Штучний інтелект та перевірка на Nintendo Switch хомбрю
- Оновлено аналізатор `analyze_repo_with_gemini`: додано перевірку `"is_switch_homebrew": true/false`. Репозиторії, які не є іграми, портами чи хомбрю додатками для Nintendo Switch (наприклад, не-Switch навчальні репозиторії), автоматично відсіюються.

### 4. Інтеграція з Gist Sync (`sync_gist_state.py`)
- Файл `custom_releases_state.json` додано до масиву `FILES_TO_SYNC`.
- Реалізовано алгоритм злиття (merge) для збереження найновішого `last_run` та актуального стану авторів.

### 5. Релізи, додані при першому запуску v0.6.59
У `data/manual_releases.json` автоматично додано **4 нові релізи** із прапорцем `"processed": false`:
- **`papersplease (ChanseyIsTheBest)`** (`1.0.0`): Новий реліз Papers, Please для Nintendo Switch (`https://github.com/ChanseyIsTheBest/papersplease_nx`).
- **`Valkyrie Profile Lenneth (delsonazevedo)`** (`1.0.0`): Порт Valkyrie Profile Lenneth для Nintendo Switch (`https://github.com/delsonazevedo/vpl_nx`).
- **`Super Mario World Remastered Plus (delsonazevedo)`** (`1.0.0`): Порт Super Mario World Remastered Plus для Nintendo Switch (`https://github.com/delsonazevedo/Super-Mario-World-Remastered-Plus-Switch`).
- **`nbajam (delsonazevedo)`** (`1.0.0`): Порт NBA Jam для Nintendo Switch (`https://github.com/delsonazevedo/nbajam_nx`).

---

## Перевірка та результат

- Проведено тестові запуски `collect_custom_releases.py`.
- При повторному запуску скрипт чітко розпізнав існуючих авторів, використав `last_run` як відсічення та правильно повідомив `No new releases found since last run.`
- Стан бази даних та файл `custom_releases_state.json` успішно синхронізовано з GitHub Gist (`Gist upload successful!`).
