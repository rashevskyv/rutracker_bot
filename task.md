# Список завдань (Task List)

## Дослідження проблеми з Manual Releases та покращення статистики

- [x] Отримати від користувача вміст `run_checker.sh` та логів крону з сервера
- [x] Проаналізувати лог помилок на сервері (виявлено розсинхронізацію Gist)
- [x] Оновити `send_homebrew_digest.py` для виведення кількості релізів у черзі (pending count) в статистиці
- [x] Оновити `send_daily_digest.py` для виведення кількості релізів у черзі (pending count) в статистиці
- [x] Інтегрувати автоматичну Gist-синхронізацію у `config/run_checker.sh.example`
- [x] Протестувати зміни локально та виконати локальний upload ручних релізів у Gist
- [x] Ітерувати версію програми до v0.6.35 у CHANGELOG.md

## Виправлення помилки відправки щоденного дайджесту (HTML-теги)

- [x] Виправити регулярний вираз для очищення незавершених HTML-тегів при обрізанні опису оновлень у `main.py`
- [x] Очистити файл `data/daily_digest_data.json` від зламаних тегів
- [x] Перевірити роботу та переконатися, що збір дайджесту проходить без помилок
- [x] Оновити `CHANGELOG.md` та ітерувати версію програми до v0.6.36
- [x] Оновити `walkthrough.md` та відобразити нову версію

## Інтеграція безпечного злиття Gist (v0.6.37)

- [x] Реалізувати логіку злиття JSON-файлів у `sync_gist_state.py`
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.37
- [x] Оновити `walkthrough.md`

## Розділення обробки ручних релізів (v0.6.39)

- [x] Додати параметр `release_type` у `process_manual_releases` у `services/manual_releases.py`
- [x] Вказати відповідний тип при виклику у `send_daily_digest.py` та `send_homebrew_digest.py`
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.39
- [x] Закомітити та завантажити зміни до GitHub
- [x] Оновити `walkthrough.md` та виконати безпечну синхронізацію Gist із новими ручними релізами

## Автоматичний збір репозиторіїв NaGaa95 (v0.6.41)

- [x] Розробити скрипт `collect_nagaa_releases.py` з інтеграцією локального Gemini API (на http://localhost:8081/v1)
- [x] Створити Windows batch файл `run_nagaa_collector.bat` для запуску подвійним кліком
- [x] Вирішити проблему з кодуванням консолі Windows (UTF-8)
- [x] Протестувати роботу збору та переконатися, що релізи автоматично синхронізуються з Gist
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.41
- [x] Закомітити та завантажити зміни до GitHub
- [x] Оновити `walkthrough.md`

## Виправлення застрягання last_entry.txt (v0.6.42)

- [x] Виправити логіку обробки не-JSON файлів при `upload` у `sync_gist_state.py`
- [x] Оновити локальний `data/last_entry.txt` найновішим лінком із `posted_links.json`
- [x] Запустити `python sync_gist_state.py upload` та переконатися, що в Gist записано коректне посилання
- [x] Додати інформацію про зміни до `CHANGELOG.md` та оновити `walkthrough.md`
- [x] Закомітити зміни локально з версією v0.6.42

## Виправлення полів processed та збір релізів NaGaa95 (v0.6.43)

- [x] Додати поле `processed: False` при генерації нових релізів у `collect_nagaa_releases.py`
- [x] Написати та запустити скрипт для додавання `processed: false` для всіх існуючих релізів у `manual_releases.json` без цього ключа
- [x] Синхронізувати виправлений локальний `manual_releases.json` з Gist
- [x] Запустити збір релізів NaGaa95 та перевірити успішність їх завантаження в Gist
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.43
- [x] Оновити `walkthrough.md` та `plan.md`
- [x] Закомітити зміни та додати git-тег v0.6.43

## Додавання нового ручного релізу (v0.6.44)

- [x] Завантажити найновіший стан бази даних з Gist за допомогою `python sync_gist_state.py download`
- [x] Додати новий запис для `th06-switch` (автор Swiizyu) у файл `data/manual_releases.json` з прапорцем `"processed": false`
- [x] Завантажити оновлену базу даних в Gist за допомогою `python sync_gist_state.py upload`
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.44
- [x] Оновити `walkthrough.md` та `plan.md`
- [x] Закомітити зміни та додати git-тег v0.6.44

## Додавання нових ручних релізів (v0.6.45)

- [x] Завантажити найновіший стан бази даних з Gist за допомогою `python sync_gist_state.py download`
- [x] Додати нові записи для `zookeeperdx_nx`, `badpiggies_nx` та `pvz_fusion_en_nx` у файл `data/manual_releases.json` з прапорцем `"processed": false`
- [x] Завантажити оновлену базу даних в Gist за допомогою `python sync_gist_state.py upload`
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.45
- [x] Оновити `walkthrough.md` та `plan.md`
- [x] Закомітити зміни та додати git-тег v0.6.45

## Рефакторинг колектора та додавання автора ChanseyIsTheBest (v0.6.46)

- [x] Перейменувати `collect_nagaa_releases.py` в `collect_custom_releases.py` та додати підтримку декількох авторів (`NaGaa95`, `ChanseyIsTheBest`)
- [x] Перейменувати `run_nagaa_collector.bat` в `run_custom_collector.bat` та оновити скрипт запуску
- [x] Запустити новий колектор та перевірити автозбір 5 нових релізів `ChanseyIsTheBest` (`Colorsheep`, `Angry Birds Classic`, `Burger Shop`, `Burger Shop 2`, `Bloons TD 5`)
- [x] Завантажити оновлений `manual_releases.json` у Gist
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.46
- [x] Оновити `walkthrough.md` та `plan.md`
- [x] Закомітити зміни та додати git-тег v0.6.46

## Перевірка оновлень оброблених ручних релізів (v0.6.47)

- [x] Додати завантаження оброблених ручних релізів (`processed: true`) у `load_homebrew_list` у `collect_homebrew_updates.py`
- [x] Встановити прапорець `is_new: false` для оновлень оброблених ручних релізів
- [x] Додати автоматичне оновлення версій та дат у `manual_releases.json` та `hb_state.json` при виявленні нових версій на GitHub
- [x] Протестувати логіку роботи колектора
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.47
- [x] Оновити `walkthrough.md` та `plan.md`
- [x] Закомітити зміни та додати git-тег v0.6.47

## Виправлення обробки помилок мережі у кастомному колекторі (v0.6.48)

- [x] Інтегрувати динамічне завантаження `OPENAI_API_KEY`, `OPENAI_BASE_URL` та моделей з `core.settings_loader` у `collect_custom_releases.py`
- [x] Додати `max_retries=0` та короткі таймаути для запобігання нескінченним спробам підключення при відсутності локального LLM сервера
- [x] Протестувати виконання `collect_custom_releases.py`
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.48
- [x] Оновити `walkthrough.md` та `task.md`

## Інтеграція моделі gemini-3.5-flash-thinking (v0.6.49)

- [x] Налаштувати першочерговий запит до `http://localhost:8081/v1` з моделлю `gemini-3.5-flash-thinking` у `collect_custom_releases.py`
- [x] Налаштувати 3-рівневу систему фолбеків (Gemini Web2API -> OpenAI API -> Ключові слова)
- [x] Протестувати виконання скрипту із запущеним Gemini Web2API
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.49
- [x] Оновити `walkthrough.md` та `task.md`

## Строгий фільтр ігор та свіжості релізів (v0.6.50)

- [x] Додати список виключень системних компонентів/ядер/прошивок (`EXCLUDE_KEYWORDS`)
- [x] Додати фільтрацію за датою релізу (`MAX_RELEASE_AGE_DAYS = 3`) у `collect_custom_releases.py`
- [x] Оновити промпт класифікації для Gemini 3.5 Flash thinking (`is_switch_game`)
- [x] Очистити не-ігрові тести з `manual_releases.json` та синхронізувати стан з Gist
- [x] Оновити `CHANGELOG.md` та ітерувати версію до v0.6.50
- [x] Оновити `walkthrough.md` та `task.md`



