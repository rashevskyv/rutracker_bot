# План: Виправлення помилки парсингу сторінки трекера ("Cannot replace one element with another when the element to be replaced is not part of a tree")

## Мета
Усунути критичну помилку `ValueError: Cannot replace one element with another when the element to be replaced is not part of a tree` при парсингу роздач з RuTracker (як-от топік 6908816). Помилка виникає в бібліотеці BeautifulSoup, коли метод `replace_with()` або `unwrap()` викликається для елемента, який вже був від'єднаний від дерева DOM (наприклад, через декомпозицію батьківського спойлера "Скриншоты" або через розгортання вкладеної цитати).

## Етапи виконання

1. **Діагностика та точне відтворення**
   - [x] Дослідити помилку в `utils/html_utils.py` та `parsers/tracker_parser.py`.
   - [x] Створити репродуктивний тест для вкладених цитат (`q-wrap` всередині `q-wrap`) та видалених спойлерів ("Скриншоты" з внутрішніми `sp-wrap`).

2. **Модифікація `utils/html_utils.py`**
   - [x] У циклі обробки спойлерів (`div.sp-wrap`):
     - Додати перевірку `if target_spoiler.parent is None: continue`.
     - Додати перевірку `if target_spoiler.parent is not None:` перед `target_spoiler.replace_with(...)`.
     - Захистити внутрішні операції над `c_wrap`, `q_wrap`, `p`, `hr`, `br`.
   - [x] У циклі обробки блоків коду (`div.c-wrap`):
     - Додати перевірку `if c_wrap.parent is None: continue`.
     - Перевіряти `if c_wrap.parent is not None:` перед `c_wrap.replace_with(...)`.
   - [x] У циклі обробки цитат (`div.q-wrap`):
     - Додати перевірку `if quote.parent is None: continue`.
     - Захистити декомпозицію `q_head` та внутрішніх `sq` (`if sq.parent is not None: sq.unwrap()`).
     - Перевіряти `if quote.parent is not None:` перед `quote.replace_with(...)`.
     - Підтримати англомовні заголовки цитат `wrote:` та запобігти здвоєним двокрапкам.
   - [x] У спискових операціях та заміні `hr`/`br`:
     - Додати перевірку `if tag.parent is not None` перед `replace_with` або `unwrap`.
   - [x] У функції `sanitize_html_for_telegram`:
     - Захистити `tag.unwrap()` перевіркою `if tag.parent is not None:`.

3. **Модифікація `parsers/tracker_parser.py`**
   - [x] У функції `get_last_post_with_phrase`: перевіряти `if quote.parent is not None:` перед `quote.decompose()` та `if br.parent is not None:` перед `br.replace_with(...)`.
   - [x] Ізолювати копіювання поста через `BeautifulSoup(str(post_body_div), 'html.parser')`.
   - [x] У блоці заголовка: перевіряти `if br.parent is not None:` перед `br.decompose()`.

4. **Тестування та валідація**
   - [x] Додати постійні тести в тестовий набір (`test_html_cleaner.py`).
   - [x] Запустити всі тести паралельно (`pytest -n auto`).
   - [x] Переконатися, що всі тестові сценарії (вкладені цитати, вкладені спойлери, від'єднані вузли) проходять успішно (88/88 passed).

5. **Оновлення документації та реліз**
   - [x] Оновити `CHANGELOG.md` для версії `v0.7.50`.
   - [x] Оновити `README.md` з описом виправлення та захищеного парсингу HTML.
   - [x] Заповнити `walkthrough.md`.
   - [x] Оновити `plan.md` та `task.md`.
