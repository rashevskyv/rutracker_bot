# Звіт про виконану роботу: Клікабельні регіональні ціни у картках (v0.7.02)

## Огляд задачі
Зробити всі ціни в картці знижки (базову європейську та всі регіональні) клікабельними посиланнями, які відкривають гру безпосередньо у відповідному регіональному магазині Nintendo eShop.

---

## Виконані кроки

1. **Генератор прямих посилань на регіональні eShop (`get_region_eshop_url`)**:
   - `services/eshop/formatters.py` та `eshop-prices/src/bot/formatters.py`: Реалізовано функцію генерації посилань для кожного регіону:
     - 🇺🇸 США: `https://www.nintendo.com/us/search/#q=...`
     - 🇵🇱 Польща / 🇬🇧 Європа: `https://www.nintendo.com/en-gb/Search/Search-299117.html?q=...`
     - 🇿🇦 ПАР: `https://www.nintendo.co.za/Search/Search-299117.html?q=...`
     - 🇦🇷 Аргентина: `https://store.nintendo.com.ar/catalogsearch/result/?q=...`
     - 🇨🇱 Чилі: `https://store.nintendo.cl/catalogsearch/result/?q=...`
     - 🇵🇪 Перу: `https://store.nintendo.com.pe/catalogsearch/result/?q=...`
     - 🇧🇷 Бразилія: `https://store.nintendo.com.br/catalogsearch/result/?q=...`
     - 🇲🇽 Мексика: `https://www.nintendo.com/es-mx/search/#q=...`
     - 🇦🇺 / 🇳🇿 Австралія та Нова Зеландія: `https://www.nintendo.com/au/search/#q=...`
     - 🇯🇵 Японія: `https://store-jp.nintendo.com/search/?q=...`

2. **Клікабельність цін**:
   - Кожна ціна в блоці `🌍 Ціни в регіонах eShop:` та базова ціна тепер обгорнуті в гіперпосилання. При натисканні на конкретну ціну відкривається магазин саме цієї країни.

3. **Тестування**:
   - Усі 16 тестів пройшли успішно (`pytest -v -n auto`).
