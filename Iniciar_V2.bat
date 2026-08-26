@echo off
cd /d "%~dp0"
if not exist ".venv_build\Scripts\python.exe" (
    echo Ambiente nao encontrado. Execute: py -m venv .venv_build
    echo Depois instale: .venv_build\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
".venv_build\Scripts\python.exe" main.py
exit /b %ERRORLEVEL%
