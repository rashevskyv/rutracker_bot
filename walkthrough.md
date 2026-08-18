# Звіт про виконану роботу: Ключ Remove для видалення повідомлень вітрини (v0.7.04)

## Огляд задачі
Додати ключ `--remove` / `remove` для `send_eshop_deals.py` та інтерактивну команду `/remove` у боті для видалення вказаної кількості повідомлень (або всіх) із гілки вітрини.

---

## Виконані кроки

1. **CLI-ключ `--remove` у `send_eshop_deals.py`**:
   - `python send_eshop_deals.py --remove 20` (або `remove 20`, `-r 20`) — видаляє 20 повідомлень вітрини з Telegram і оновлює файл стану `data/eshop_active_showcase.json`.
   - `python send_eshop_deals.py --remove all` (або `remove all`) — видаляє всі збережені повідомлення вітрини та повністю очищає стан.

2. **Інтерактивна команда в Telegram (`/remove`)**:
   - `services/eshop/bot_commands.py`: Додано команди `/remove [N|all]` та `/remove_deals [N|all]`.
   - Адміністратор може надіслати `/remove 20` або `/remove all` безпосередньо в топік, і бот видалить ці повідомлення з чату та повідомить про результат.

3. **Тестування**:
   - Усі 17 тестів пройшли успішно (`pytest -v -n auto`).
