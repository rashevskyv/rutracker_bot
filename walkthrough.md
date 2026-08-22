# Звіт про виконану роботу: Детекція жанру Homebrew для роздач RuTracker та відключення скріншотів (v0.7.33)

## Що зроблено

1. **Реалізовано функцію детекції жанру Homebrew (`is_homebrew_genre`)**:
   - У файлі [parsers/tracker_parser.py](file:///d:/git/dev/rutracker_bot/parsers/tracker_parser.py) додано функцію `is_homebrew_genre(genres, description, title)`.
   - Функція ретельно аналізує:
     - Список жанрів `genres` (підтримка англійських `Homebrew`, `#Homebrew`, `home-brew`, `home brew` та кириличних варіантів `Хоумбрю`, `Хомбрю`, `хоум-брю`, `хоумбру` тощо).
     - Тіло та опис роздачі `description` (як у чистому тексті, так і в HTML: `<b>Жанр:</b> Homebrew`, `<b>Genre:</b> #Homebrew` тощо).
     - Прямі хештеги `#homebrew`, `#хоумбрю`, `#хомбрю`.
     - Маркери у назві роздачі `[Homebrew]`, `(Хоумбрю)` тощо.

2. **Відключення скріншотів для Homebrew у головному пайплайні (`main.py`)**:
   - У [main.py](file:///d:/git/dev/rutracker_bot/main.py) інтегровано виклик `is_homebrew_genre`.
   - Якщо роздача визначена як Homebrew, бот пропускає звернення до бази TitleDB та завантаження скріншотів (`local_screenshot_paths = []`), фіксуючи це в логах (`Homebrew release detected ('...'). Skipping screenshot lookup/download.`).
   - Це запобігає завантаженню та відправці невідповідних скріншотів комерційних ігор у Telegram.

3. **Створено тестовий набір (`test_tracker_homebrew.py`)**:
   - Додано юніт-тести, які перевіряють всі комбінації жанрів, описів, хештегів, назв та відсутність хибних спрацьовувань на звичайних іграх.

4. **Паралельне тестування**:
   - Усі 28 тестів виконано успішно (`pytest -v -n auto`).

5. **Оновлення документації та ітерація версії**:
   - Версію підвищено до `v0.7.33`.
   - Оновлено [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md), [README.md](file:///d:/git/dev/rutracker_bot/README.md), [plan.md](file:///d:/git/dev/rutracker_bot/plan.md), [task.md](file:///d:/git/dev/rutracker_bot/task.md).
