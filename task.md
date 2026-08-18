# Список завдань (Tasks)

## Виконані завдання
- [x] Створити `SubscriptionService` з гранулярним керуванням категоріями (`deals`, `rutracker`, `digests`).
- [x] Встановити значення за замовченням — вимкнено для всіх категорій у приватних повідомленнях.
- [x] Додати команди `/subscriptions`, `/settings`, `/sub`, `/unsub` до `services/eshop/bot_commands.py`.
- [x] Підключити підписників до `send_to_telegram()` у `services/telegram_sender.py`.
- [x] Підключити підписників до `collect_target_groups()` у `digest/runner.py`.
- [x] Підключити підписників до `send_eshop_deals.py`.
- [x] Додати `user_subscriptions.json` до `sync_gist_state.py`.
- [x] Написати юніт-тести та випустити реліз `v0.6.91`.
