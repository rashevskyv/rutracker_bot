# Завдання: Виправлення помилки парсингу сторінки трекера ("Cannot replace one element with another when the element to be replaced is not part of a tree")

## Виконані завдання
- [x] **Діагностика та локалізація**:
  - [x] Відтворено помилку `ValueError: Cannot replace one element with another when the element to be replaced is not part of a tree` на вкладених цитатах та спойлерах.
  - [x] Визначено проблемні місця в `utils/html_utils.py` (`clean_description_html`, `sanitize_html_for_telegram`) та `parsers/tracker_parser.py`.
- [x] **Виправлення та захист DOM-операцій**:
  - [x] Додано захисні перевірки `element.parent is not None` перед викликами `replace_with()` та `unwrap()` для спойлерів (`sp-wrap`), цитат (`q-wrap`), блоків коду (`c-wrap`), списків (`li`, `ul`, `ol`), розривів (`hr`, `br`).
  - [x] Забезпечено коректну обробку вкладених спойлерів (зокрема при декомпозиції зовнішнього спойлера на зразок "Скриншоты").
  - [x] Забезпечено коректну обробку вкладених цитат при їх розгортанні (unwrap), пропускаючи від'єднані елементи на наступних ітераціях.
  - [x] Додано підтримку англомовних заголовків цитат "wrote:" та очищення повторних двокрапок.
  - [x] Ізольовано копіювання тіла поста через `BeautifulSoup(str(post_body_div), 'html.parser')` у `parsers/tracker_parser.py`.
- [x] **Тестування**:
  - [x] Створено новий тестовий модуль `test_html_cleaner.py` із 6 комплексними тестами на вкладені цитати, вкладені спойлери, блоки коду, списки та глибокі теги.
  - [x] Усі 88 тестів успішно пройшли у паралельному режимі (`pytest -n auto`).
- [x] **Документація та версіонування**:
  - [x] Ітеровано версію програми до `v0.7.50`.
  - [x] Оновлено `CHANGELOG.md`, `README.md`, `walkthrough.md`, `plan.md` та `task.md`.
