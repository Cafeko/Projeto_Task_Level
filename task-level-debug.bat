@echo off
REM Task Level - diagnostico COM janela de console (erros ficam visiveis).
REM Uso normal sem console: duplo-clique no task-level.vbs (ou task-level.bat).
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%main.py" %*
if errorlevel 1 pause
