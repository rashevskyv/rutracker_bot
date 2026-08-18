# Звіт про виконану роботу: Виправлення завантажувача конфігурації у remove_showcase_deals (v0.7.06)

## Огляд задачі
Виправлено помилку `NameError: name 'load_settings' is not defined` при виконанні команди `python send_eshop_deals.py remove all`.

---

## Виконані кроки

1. **Виправлення виклику `load_config` (`send_eshop_deals.py`)**:
   - Замінено неіснуючу функцію `load_settings()` на правильний виклик `load_config(local_settings_path) or load_config(default_settings_path)` з модуля `core.settings_loader`.

2. **Тестування**:
   - Усі 17 тестів пройшли успішно (`pytest -v -n auto`).
