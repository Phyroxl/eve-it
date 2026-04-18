@echo off
echo ========================================
echo EVE iT - Git Push Helper
echo ========================================
echo Preparando subida a GitHub...
del auto_patch.py 2>nul
del server.py 2>nul
del _main_char.json 2>nul
del .main.pid 2>nul
git add .
git commit -m "Auto Update: Optimizacion del HUD, Filtro de Chat, Replicador 2.0 completado y refactor general de UI"
echo.
echo Intentando hacer push...
git push
echo.
echo Proceso finalizado.
pause
