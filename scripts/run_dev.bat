@echo off
rem 소스에서 바로 실행 (pip install -r requirements.txt 선행)
cd /d "%~dp0\..\src"
start "" pythonw app.py
