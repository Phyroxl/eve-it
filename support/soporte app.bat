@echo off
title Soporte App - Kill EVE iT Processes
cd /d "%~dp0\.."
echo Ejecutando script de limpieza de emergencia...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0soporte_app_kill_processes.ps1"
echo.
echo Presiona cualquier tecla para cerrar esta ventana.
pause > nul
