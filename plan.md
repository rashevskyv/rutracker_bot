# План рефакторингу колектора репозиторіїв та додавання автора ChanseyIsTheBest (v0.6.46)

Цей план описує процес розширення колектора репозиторіїв для підтримки кількох авторів (`NaGaa95`, `ChanseyIsTheBest`), перейменування скриптів та автоматичного збору релізів.

## Пропоновані зміни

### 1. Рефакторинг скрипту збору та batch-файлу
- [x] Перейменувати `collect_nagaa_releases.py` на `collect_custom_releases.py` та додати список авторів `TARGET_USERS = ["NaGaa95", "ChanseyIsTheBest"]`.
- [x] Перейменувати `run_nagaa_collector.bat` на `run_custom_collector.bat` та оновити запуск `python collect_custom_releases.py`.
- [x] Протестувати автоматичний збір нових портів для автора `ChanseyIsTheBest` (зокрема `colorsheep_nx`, `angrybirdsclassic_nx`, `burgershop_nx`, `btd5_nx`, `burgershop2_nx`).
- [x] Автоматично вивантажити оновлену базу ручних релізів у хмару Gist.

### 2. Версіонування та документація
- [x] Оновити `CHANGELOG.md` (англійською мовою), зафіксувавши версію `v0.6.46`.
- [x] Оновити `task.md`, `walkthrough.md` та `plan.md` (українською мовою).
- [x] Виконати git commit та створити новий тег `v0.6.46`.
