# Walkthrough: Синхронізація та додавання Autorun (danfromtico) у manual_releases.json (v0.7.53)

## Огляд змін
У версії `v0.7.53`:
1. **Синхронізація бази релізів з GitHub Gist**:
   - Виконано завантаження актуального стану `manual_releases.json` із віддаленого Gist-сховища за допомогою [sync_gist_state.py](file:///d:/git/dev/rutracker_bot/sync_gist_state.py) (`python sync_gist_state.py download manual_releases.json`).
   - Механізм злиття автоматично інтегрував нові релізи від серверних колекторів (як-от `Total Party Kill`, `Duke Dashington Remastered`, `Heart Star` від `ChanseyIsTheBest`) та зберіг усі локальні несинхронізовані записи.
2. **Додавання релізу `danfromtico/autorun`**:
   - У файл `data/manual_releases.json` додано новий випуск застосунку `Autorun (danfromtico)` (раніше відомого як Wine-NX):
     - **Версія**: `test-build-3`
     - **Платформа**: `Switch`
     - **Посилання**: [https://github.com/danfromtico/autorun/releases/tag/test-build-3](https://github.com/danfromtico/autorun/releases/tag/test-build-3)
     - **Опис**: *«Додаток для запуску ПК-ігор та програм Windows на Nintendo Switch на базі Wine та транслятора Box64 (раніше Wine-NX). Тестова збірка 3 містить оновлений інтерфейс і брендинг, індивідуальне призначення кнопок для кожної гри, автофорвардер для 32-бітних проєктів та розширену сумісність.»*
     - **Статус**: `processed: false`, очікує включення у найближчий дайджест хоумбрю.
   - Загальна кількість записів у базі зросла до **259**.
3. **Вивантаження оновленої бази на Gist**:
   - Виконано команду `python sync_gist_state.py upload manual_releases.json`.
   - Проведено верифікаційне завантаження, що підтвердило наявність та цілісність усіх 259 записів.
4. **Паралельне тестування**:
   - Усі 93 тести проєкту успішно виконані у паралельному режимі (`pytest -n auto`).
5. **Документація та версіонування**:
   - Ітеровано версію програми до `v0.7.53`.
   - Оновлено [CHANGELOG.md](file:///d:/git/dev/rutracker_bot/CHANGELOG.md), [task.md](file:///d:/git/dev/rutracker_bot/task.md) та [plan.md](file:///d:/git/dev/rutracker_bot/plan.md).

---

## Доданий запис у `data/manual_releases.json`

| Додаток / Гра | Версія | Платформа | Посилання на реліз | Статус |
| :--- | :--- | :--- | :--- | :--- |
| **Autorun (danfromtico)** | `test-build-3` | Switch | [GitHub Release](https://github.com/danfromtico/autorun/releases/tag/test-build-3) | `processed: false` |

---

## Результати тестування
```powershell
pytest -n auto
# ============================= 93 passed in 16.51s =============================
```
