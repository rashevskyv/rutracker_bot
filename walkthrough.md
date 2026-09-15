# Walkthrough: Виправлення помилки парсингу сторінки трекера ("Cannot replace one element with another when the element to be replaced is not part of a tree") (v0.7.50)

## Огляд змін
У версії `v0.7.50`:
1. **Діагностовано причину збою парсера**:
   - Помилка `ValueError: Cannot replace one element with another when the element to be replaced is not part of a tree` виникала при виклику `replace_with()` або `unwrap()` для елементів BeautifulSoup, якщо їхній батьківський вузол був видалений або розгорнутий (`element.parent is None`).
   - Типові сценарії відтворення:
     1. **Вкладені цитати (`q-wrap` всередині `q-wrap`)**: список `find_all("div", class_="q-wrap")` знаходить і зовнішній, і внутрішній блоки цитат. При обробці зовнішньої цитати внутрішня розгортається (`sq.unwrap()`). Коли черга доходить до внутрішньої цитати в зовнішньому циклі, вона вже від'єднана (`quote.parent is None`), і виклик `quote.replace_with(...)` призводив до помилки.
     2. **Вкладені спойлери у видалених блоках**: якщо зовнішній спойлер має назву "Скриншоты", викликається `target_spoiler.decompose()`. Всі внутрішні спойлери, які були заздалегідь зібрані через `find_all("div", class_="sp-wrap")`, втрачають батьківський вузол (`parent is None`), викликаючи збій на наступних ітераціях.
2. **Впроваджено захист операцій над деревом DOM**:
   - [utils/html_utils.py](file:///d:/git/dev/rutracker_bot/utils/html_utils.py):
     - Додано перевірки `if target_spoiler.parent is None: continue` перед обробкою та заміною спойлерів.
     - Захищено операції над внутрішніми блоками коду (`c_wrap`), цитатами (`q_wrap`), параграфами (`p`), горизонтальними лініями (`hr`) та розривами (`br`).
     - Додано перевірки `if quote.parent is None: continue` для обробки цитат та захищено їхній фінальний `quote.replace_with(...)`.
     - Підтримано англомовні заголовки цитат `wrote:` поруч із російськими `писал(а):` та прибрано здвоєні двокрапки.
     - Захищено операції над списками (`li.unwrap()`, `ul.unwrap()`) та `tag.unwrap()` у `sanitize_html_for_telegram`.
   - [parsers/tracker_parser.py](file:///d:/git/dev/rutracker_bot/parsers/tracker_parser.py):
     - Ізольовано створення копії поста через `BeautifulSoup(str(post_body_div), 'html.parser')`.
     - Додано перевірки `if quote.parent is not None:` перед `quote.decompose()` та `if br.parent is not None:` перед `br.replace_with("\n")` і `br.decompose()`.
3. **Створено модульні тести**:
   - [test_html_cleaner.py](file:///d:/git/dev/rutracker_bot/test_html_cleaner.py): 6 нових тестів, що покривають багаторівневі вкладені цитати, внутрішні спойлери всередині декомпозованих блоків скриншотів, блоки коду, списки та глибокі вкладені теги `span`.
4. **Паралельне тестування**:
   - Усі 88 тестів успішно пройшли в паралельному режимі (`pytest -n auto`).
5. **Документація та версіонування**:
   - Оновлено [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md), [README.md](file:///d:/git/dev/rutracker_bot/README.md), [task.md](file:///d:/git/dev/rutracker_bot/task.md) та [plan.md](file:///d:/git/dev/rutracker_bot/plan.md).

---

## Деталі змін коду

### 1. Захист у `clean_description_html` ([utils/html_utils.py](file:///d:/git/dev/rutracker_bot/utils/html_utils.py))
- Кожен обхід елементів, повернених через `find_all()`, тепер перевіряє `if element.parent is None: continue`.
- Будь-який виклик `replace_with()`, `unwrap()` чи `decompose()` здійснюється лише тоді, коли `element.parent is not None`.

### 2. Захист у `sanitize_html_for_telegram` ([utils/html_utils.py](file:///d:/git/dev/rutracker_bot/utils/html_utils.py))
- Додано перевірку наявності батьківського елемента перед видаленням та розгортанням непідтримуваних тегів.

### 3. Ізоляція тіла поста ([parsers/tracker_parser.py](file:///d:/git/dev/rutracker_bot/parsers/tracker_parser.py))
- Замість shallow copy (`__copy__()`) використовується повна ізоляція через окремий парсинг рядка, захищена перевірками вузлів.

---

## Результати тестування
```powershell
pytest -n auto
# ============================= 88 passed in 14.73s =============================
```
