@echo off
REM Task Level - duplo-clique para abrir SEM janela de console (usa pythonw).
REM Zero flash mesmo: de duplo-clique no task-level.vbs.
REM Para diagnostico COM console (erros visiveis), use task-level-debug.bat.
setlocal
set "ROOT=%~dp0"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
if exist "%PYW%" (
    start "" /min "%PYW%" "%ROOT%main.py" %*
) else (
    start "" /min pythonw "%ROOT%main.py" %*
)
