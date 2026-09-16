@echo off
REM Task Level - duplo-clique para abrir (nao depende da pasta atual nem do VS Code)
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%main.py" %*
if errorlevel 1 pause
