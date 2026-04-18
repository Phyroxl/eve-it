@echo off
cd /d "%~dp0"
echo Actualizando EVE iT desde GitHub...
git pull origin main
echo.
echo Actualizacion completada. Reiniciando...
timeout /t 2 /nobreak > nul
call "%~dp0INICIAR.bat"
