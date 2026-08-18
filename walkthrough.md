# Звіт про виконану роботу: Виправлення помилки 400 Bad Request при відповідях (v0.6.92)

## Огляд задачі
Під час запуску `bot_interactive.py` виникла помилка:
`400 Bad Request: message to be replied not found`.
Це стається, коли користувацьке повідомлення видалено, переміщено, або коли бот стартує і обробляє чергу старих повідомлень через `reply_to_message_id`.

---

## Виконані кроки

1. **Безпечні методи відправки (`safe_reply`, `safe_send_card`)**:
   - Реалізовано `safe_reply()` та `safe_send_card()` у `services/eshop/bot_commands.py`.
   - Додано прапорець `allow_sending_without_reply=True` до всіх викликів Telegram API.
   - Додано автоматичний retry-fallback без `reply_to_message_id` у випадку помилки видаленого повідомлення.

2. **Оновлення всіх обробників**:
   - Усі команди (`/deals`, `/search`, `/wishlist`, `/subscriptions`, `/sub`, `/unsub`, `/help`) переведені на `safe_reply()` та `safe_send_card()`.

3. **Тестування**:
   - Усі 13 тестів проходять паралельно (`pytest -v -n auto`).
