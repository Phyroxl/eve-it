Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Obtener la ruta de la carpeta donde está el script .vbs
strPath = WScript.ScriptFullName
strFolder = objFSO.GetParentFolderName(strPath)

' Establecer el directorio de trabajo a la carpeta del proyecto
WshShell.CurrentDirectory = strFolder

' Ejecutar pythonw para lanzar la aplicación sin ventana de consola
' Se usa "pythonw" para que no se abra la ventana negra
WshShell.Run "pythonw main.py", 0, False

Set WshShell = Nothing
Set objFSO = Nothing
