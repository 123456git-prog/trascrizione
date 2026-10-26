' Avvia il server senza finestra (usato dall'avvio automatico di Windows).
' Il registro degli eventi si trova in data\server.log
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
sh.Run """" & dir & "\.venv\Scripts\pythonw.exe"" -m app.server", 0, False
