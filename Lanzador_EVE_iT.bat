@echo off
title EVE iT — Lanzador Estándar
echo [INFO] Iniciando EVE iT Suite...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] La aplicacion se ha cerrado de forma inesperada (Codigo: %errorlevel%).
    echo Asegurate de tener instaladas las dependencias: pip install -r requirements.txt
    pause
)
