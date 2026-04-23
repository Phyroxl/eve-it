@echo off
echo ========================================
echo   EVE iT - Sincronizacion con GitHub
echo ========================================
echo.

cd /d "%~dp0"

echo Verificando repositorio git...
git status >nul 2>&1
if errorlevel 1 (
    echo ERROR: Esta carpeta no es un repositorio git.
        echo Asegurate de ejecutar este script desde la raiz del proyecto.
            pause
                exit /b 1
                )

                echo Descargando cambios de GitHub...
                git fetch origin main

                echo.
                git log HEAD..origin/main --oneline
                echo.

                echo Aplicando cambios...
                git pull origin main

                echo.
                echo ========================================
                echo   Sincronizacion completada
                echo ========================================
                pause
