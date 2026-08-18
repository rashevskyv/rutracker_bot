# Список завдань (Tasks)

## Виконані завдання
- [x] Додати підтримку `OPENROUTER_API_KEY` та `base_url="https://openrouter.ai/api/v1"` у `settings_loader.py`.
- [x] Встановити `openai/gpt-5.6-luna` як основну модель ($0.10/M) та `deepseek/deepseek-v4-flash-0731` ($0.14/M) як fallback у `services/gpt.py`.
- [x] Перевести переклад `services/translation.py`, валідацію `services/ai_validator.py` та колектори на OpenRouter.
- [x] Оновити `.github/workflows/bot_runner.yml` та `settings.json`.
- [x] Прогнати тести та випустити реліз `v0.6.75`.
