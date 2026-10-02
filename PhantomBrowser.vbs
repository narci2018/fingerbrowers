Set ws = CreateObject("Wscript.Shell")
currentDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ws.CurrentDirectory = currentDir
ws.Run """C:\Users\narci\miniconda3\pythonw.exe"" """ & currentDir & "\app_gui.py""", 0, False
