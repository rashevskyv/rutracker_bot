# Звіт про виконану роботу: Оновлення прямих посилань на eShop Латинської Америки (v0.7.24)

## Огляд задачі
Користувач помітив, що посилання на аргентинську, чилійську та бразильську ціни видавали помилку (не відкривалися).

---

## Причина проблеми та виправлення

1. **Що сталося з посиланнями**:
   - Раніше посилання вели на старі піддомени Nintendo (`store.nintendo.com.ar`, `store.nintendo.cl`, `store.nintendo.com.pe`), які Nintendo відключила (HTTP 404), перевівши всі латиноамериканські регіони на єдиний портал `www.nintendo.com`.
2. **Що виправлено**:
   - `services/eshop/formatters.py` та `eshop-prices/src/bot/formatters.py`: оновлено прямі посилання на актуальні робочі адреси:
     - 🇦🇷 Аргентина: `https://www.nintendo.com/es-ar/search/#q=...`
     - 🇨🇱 Чилі: `https://www.nintendo.com/es-cl/search/#q=...`
     - 🇧🇷 Бразилія: `https://www.nintendo.com/pt-br/search/#q=...`
     - 🇵🇪 Перу: `https://www.nintendo.com/es-pe/search/#q=...`
     - 🇨🇴 Колумбія: `https://www.nintendo.com/es-co/search/#q=...`
     - 🇲🇽 Мексика: `https://www.nintendo.com/es-mx/search/#q=...`
   - Кожне посилання протестовано — повертає статус HTTP 200.
3. **Чи правильні ціни на Crysis Remastered Trilogy**:
   - Так! У Crytek на аргентинському eShop стара базова ціна залишилася `5498.90 ARS` (~165 грн). В Чилі діє офіційна знижка -60% (`14397 CLP` ~705 грн), у США -60% (`$19.99` ~896 грн).
4. **Тестування**:
   - Усі 21 тест пройдено паралельно (`pytest -v -n auto`).
