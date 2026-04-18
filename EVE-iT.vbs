Set WshShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' Ejecuta el proceso de forma totalmente invisible (parámetro 0)
WshShell.Run """" & strPath & "\INICIAR.bat" & """ -silent", 0, False
