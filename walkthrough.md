# Walkthrough: додавання ручного релізу Need for Speed: Most Wanted (v0.7.55)

У версії `v0.7.55`:
1. **Синхронізація бази релізів з GitHub Gist**:
   - Завантажено актуальний стан `manual_releases.json` із віддаленого сховища GitHub Gist за допомогою [sync_gist_state.py](file:///d:/git/dev/rutracker_bot/sync_gist_state.py) (`python sync_gist_state.py download manual_releases.json`).
   - Автоматичний механізм злиття зберіг усі локальні та віддалені модифікації, довівши базу до 272 записів.

2. **Додавання релізу `StevensND/nfsmw-nx`**:
   - Отримано метадані першого публічного релізу порту культової гри **Need for Speed: Most Wanted (2005)** версії Xbox 360 для Nintendo Switch.
   - Сформовано структурований запис у `data/manual_releases.json`:
     - **Назва**: `Need for Speed: Most Wanted (StevensND)`
     - **Версія**: `v1.0.0`
     - **Платформа**: `Switch`
     - **Тип**: `homebrew`
     - **Посилання**: [https://github.com/StevensND/nfsmw-nx/releases/tag/v1.0.0](https://github.com/StevensND/nfsmw-nx/releases/tag/v1.0.0)
     - **Опис**: *«Перший публічний реліз NFSMW-NX — нативного порту культової перегонової гри Need for Speed: Most Wanted (2005) версії Xbox 360 для Nintendo Switch. Підтримує роздільну здатність 720p у портативі та 1080p у доці, різні регіональні видання гри, нативне керування геймпадами консолі та вебінсталятор для підготовки файлів і шейдерів.»*
     - **Статус**: `processed: false`, `is_new: true` (очікує на відправку в хоумбрю-дайджест).
   - Загальна кількість записів у базі досягла **273**.

3. **Вивантаження оновленої бази на GitHub Gist**:
   - Виконано вивантаження оновленого реєстру через команду `python sync_gist_state.py upload manual_releases.json`.
   - Проведено контрольне завантаження (`python sync_gist_state.py download manual_releases.json`), яке підтвердило наявність та цілісність усіх 273 записів на віддаленому Gist.

4. **Паралельне тестування**:
   - Проведено повний прогін тестів у паралельному режимі (`pytest -n auto`): `106 passed`.

---

## Доданий запис у `data/manual_releases.json`

| Додаток / Гра | Версія | Платформа | Посилання на реліз | Статус |
| :--- | :--- | :--- | :--- | :--- |
| **Need for Speed: Most Wanted (StevensND)** | `v1.0.0` | Switch | [GitHub Release](https://github.com/StevensND/nfsmw-nx/releases/tag/v1.0.0) | `processed: false` |

---

## Результати тестування
```powershell
pytest -n auto
# ============================ 106 passed in 20.82s ============================
```

---

## v0.7.56 — позачергові акції Nintendo (2026-09-28)

- Базові ігри зі списку `NINTENDO_FIRST_PARTY_GAMES` розпізнаються за точною нормалізованою назвою; DLC і пакети не отримують пріоритету.
- Активні Nintendo картки публікуються першими та не займають 30 звичайних місць. Повторний цикл не створює дублікати.
- Живий US Price API визначає стан знижки. Змінена активна ціна редагується в повідомленні зі збереженням прямого посилання; порожня відповідь API або збій Telegram залишає картку для повторної спроби. Підтверджене завершення знижки видаляє лише Nintendo картку та оновлює сповіщення.
- Перевірка: `wsl python.exe -m pytest -q` — 109 пройдено; після ізоляції тестового мока `wsl python.exe -m pytest -q test_eshop_us_deals.py test_eshop_module.py` — 41 пройдено без попереджень. Реальні повідомлення Telegram не надсилалися.
