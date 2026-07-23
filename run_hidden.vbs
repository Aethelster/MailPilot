Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

venvPython = appDir & "\.venv\Scripts\python.exe"
If fso.FileExists(venvPython) Then
  shell.Run """" & venvPython & """ main.py --tray", 0, False
Else
  shell.Run "cmd /c where pyw >nul 2>nul && pyw main.py --tray || pythonw main.py --tray", 0, False
End If
