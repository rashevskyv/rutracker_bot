@echo off
echo ==================================================
echo Running Custom Switch Repositories Collector...
echo (NaGaa95, ChanseyIsTheBest)
echo ==================================================
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    call .venv\Scripts\activate.bat 2>nul
)
python collect_custom_releases.py
echo ==================================================
echo Done.
pause
