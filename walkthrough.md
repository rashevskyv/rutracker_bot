# Звіт про виконану роботу: Валідація знижок через Live Price API та усунення «примарних» знижок (v0.7.31)

## Огляд проблеми
Користувач звернув увагу на те, що на картці Hogwarts Legacy відображалася знижка 8.99 EUR (-85%), тоді як на офіційному сайті Nintendo (50 фунтів) та на eShop-Prices.com знижки немає.

---

## Причина проблеми

1. **Застарілий кеш у Solr**:
   - Пошуковий індекс Nintendo Europe Solr (`searching.nintendo-europe.com/en/select`) містив застарілі поля минулого розпродажу Warner Bros: `price_has_discount_b: true`, `price_discounted_f: 8.99`.
2. **Невідповідність із живим Price API**:
   - Офіційний live Price API Nintendo (`api.ec.nintendo.com/v1/price`), який обслуговує реальний eShop та eShop-Prices.com, показує `discount: None` (тобто акція вже закінчилася).

---

## Що виправлено

1. **Інтеграція `validate_live_prices` в `EShopService`**:
   - Додано обов'язкову перевірку кожного кандидата на знижку через офіційний live Price API (`api.ec.nintendo.com/v1/price`).
   - Якщо live Price API повертає `discount_price: None`, гра **автоматично відсіюється** як «примарна» знижка і ніколи не публікується у вітрині чи дайджестах.
2. **Точні ціни**:
   - Якщо знижка підтверджена живим API, бот бере актуальні регулярну та акційну ціни безпосередньо з live Price API.
3. **Тестування**:
   - Hogwarts Legacy успішно визначається як гра без знижки (`pct=0.0%`).
   - Усі 24 тести пройдено успішно (`pytest -v -n auto`).
