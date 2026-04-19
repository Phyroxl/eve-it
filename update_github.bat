@echo off
title GitHub Uploader - EVE Replicator
echo.
echo  =========================================
echo    EVE REPLICATOR - ACTUALIZAR GITHUB
echo  =========================================
echo.

:: Comprobar si git está instalado
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git no esta instalado o no esta en el PATH.
    pause
    exit /b
)

echo [+] Añadiendo cambios...
git add .

echo.
set "commit_msg="
set /p commit_msg="Introduce un mensaje para los cambios (o pulsa ENTER para usar uno por defecto): "

if "%commit_msg%"=="" (
    set commit_msg=Actualizacion de mantenimiento y mejoras de estabilidad
)

echo [+] Confirmando cambios...
:: Usamos comillas solo aqui para evitar el error de pathspec
git commit -m "%commit_msg%"

echo.
echo [+] Subiendo a GitHub (Push)...
git push

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Hubo un problema al subir los cambios. 
    echo Revisa si tienes conexion o si necesitas hacer un 'git pull' primero.
) else (
    echo.
    echo  =========================================
    echo    ¡EXITO! Cambios subidos correctamente.
    echo  =========================================
)

echo.
pause
