@echo off
:: Si no se ha pasado el argumento -silent, se reinicia de forma invisible
if "%~1" neq "-silent" (
    powershell -WindowStyle Hidden -Command "Start-Process '%~f0' -ArgumentList '-silent' -WindowStyle Hidden"
    exit /b
)

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo EVE iT - Iniciando Sistema
echo ========================================

:: 1. Intentar encontrar Python
set PY_CMD=
where pythonw >nul 2>nul && set PY_CMD=pythonw
if not defined PY_CMD (
    where python >nul 2>nul && set PY_CMD=python
)
if not defined PY_CMD (
    where py >nul 2>nul && set PY_CMD=py
)

if not defined PY_CMD (
    echo [ERROR] No se ha encontrado Python en tu sistema.
    echo Por favor, instala Python desde https://www.python.org/downloads/
    echo Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

:: 2. Ejecutar instalador/comprobador
echo Usando: !PY_CMD!
!PY_CMD! "%~dp0boot_installer.py"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] La instalacion o comprobacion ha fallado.
    pause
    exit /b %ERRORLEVEL%
)

:: 3. Lanzar aplicacion (usando el venv si existe)
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "%~dp0main.py"
) else (
    start "" !PY_CMD! "%~dp0main.py"
)

exit /b 0
