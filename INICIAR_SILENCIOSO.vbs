Set WshShell = CreateObject("WScript.Shell")
' Obtener la ruta del directorio del script actual
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' Lanzar el archivo .bat de forma totalmente invisible (flag 0)
WshShell.Run """" & strPath & "\INICIAR.bat" & """", 0, False
