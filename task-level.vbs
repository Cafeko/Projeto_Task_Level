' Task Level - duplo-clique para abrir SEM nenhuma janela de console.
' (Para diagnostico com console, use task-level-debug.bat)
Option Explicit
Dim sh, fso, root, pyw, cmd
Set sh = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
pyw = root & ".venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw.exe"
cmd = """" & pyw & """ """ & root & "main.py"""
sh.Run cmd, 0, False
