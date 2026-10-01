# Walkthrough: додавання ручного релізу Far Cry / NearChuckle NX (v0.7.57)

У версії `v0.7.57`:
1. **Синхронізація бази релізів з GitHub Gist**:
   - Завантажено актуальний стан `manual_releases.json` із віддаленого сховища GitHub Gist за допомогою [sync_gist_state.py](file:///d:/git/dev/rutracker_bot/sync_gist_state.py) (`python sync_gist_state.py download manual_releases.json`).
   - Автоматичний механізм злиття зберіг усі локальні та віддалені модифікації.

2. **Додавання релізу `artslay/NearChuckle_nx`**:
   - Отримано метадані релізу порту гри **Far Cry (2004)** для Nintendo Switch на базі рушія NearChuckle.
   - Сформовано структурований запис у `data/manual_releases.json`:
     - **Назва**: `Far Cry (NearChuckle NX) (artslay)`
     - **Версія**: `1.0.1`
     - **Платформа**: `Switch`
     - **Тип**: `homebrew`
     - **Посилання**: [https://github.com/artslay/NearChuckle_nx/releases/tag/1.0.1](https://github.com/artslay/NearChuckle_nx/releases/tag/1.0.1)
     - **Опис**: *«Порт культового шутера Far Cry (2004) для Nintendo Switch на базі NearChuckle через шар VNX, Mesa та SDL3. Оновлення 1.0.1 додає підтримку russian.pak та виправляє текстури.»*
     - **Статус**: `processed: false`, `is_new: true` (очікує на відправку в хоумбрю-дайджест).
   - Загальна кількість записів у базі досягла **278**.

3. **Вивантаження оновленої бази на GitHub Gist**:
   - Виконано вивантаження оновленого реєстру через команду `python sync_gist_state.py upload manual_releases.json`.
   - Проведено контрольне завантаження (`python sync_gist_state.py download manual_releases.json`), яке підтвердило наявність та цілісність усіх 278 записів на віддаленому Gist.

4. **Паралельне тестування**:
   - Проведено повний прогін тестів у паралельному режимі (`pytest -n auto`): `109 passed`.

---

## Доданий запис у `data/manual_releases.json`

| Додаток / Гра | Версія | Платформа | Посилання на реліз | Статус |
| :--- | :--- | :--- | :--- | :--- |
| **Far Cry (NearChuckle NX) (artslay)** | `1.0.1` | Switch | [GitHub Release](https://github.com/artslay/NearChuckle_nx/releases/tag/1.0.1) | `processed: false` |

---

## Результати тестування
```powershell
pytest -n auto
# ============================ 109 passed in 21.00s ============================
```

---

## v0.7.56 — позачергові акції Nintendo (2026-09-28)

- Базові ігри зі списку `NINTENDO_FIRST_PARTY_GAMES` розпізнаються за точною нормалізованою назвою; DLC і пакети не отримують пріоритету.
- Активні Nintendo картки публікуються першими та не займають 30 звичайних місць. Повторний цикл не створює дублікати.
- Живий US Price API визначає стан знижки. Змінена активна ціна редагується в повідомленні зі збереженням прямого посилання; порожня відповідь API або збій Telegram залишає картку для повторної спроби. Підтверджене завершення знижки видаляє лише Nintendo картку та оновлює сповіщення.
- Перевірка: `pytest -n auto` — 109 пройдено. Реальні повідомлення Telegram не надсилалися.

