@echo off
echo ==================================================
echo Running NaGaa95 Switch Repository Collector...
echo ==================================================
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    call .venv\Scripts\activate.bat 2>nul
)
python collect_nagaa_releases.py
echo ==================================================
echo Done.
pause
