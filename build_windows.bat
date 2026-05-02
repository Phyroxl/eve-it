@echo off
REM build_windows.bat — One-click Windows build for Salva Suite
REM Generates: dist\Salva Suite\Salva Suite.exe
REM Requires:  Python 3.10+  |  pip install -r requirements.txt pyinstaller

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   SALVA SUITE — Windows Build Script
echo ============================================================
echo.

REM ---- Locate Python ----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.10+ and try again.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [INFO] Using %PY_VER%

REM ---- Check PyInstaller ----
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not found — installing...
    python -m pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause & exit /b 1
    )
)

for /f "tokens=*" %%v in ('python -m PyInstaller --version 2^>^&1') do set PYI_VER=%%v
echo [INFO] PyInstaller %PYI_VER%

REM ---- Install / verify dependencies ----
echo [INFO] Verifying runtime dependencies...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [WARN] Some dependencies could not be installed. Build may still succeed.
)

REM ---- Clean previous build ----
echo [INFO] Cleaning previous build artifacts...
if exist "build\Salva Suite" (
    rmdir /s /q "build\Salva Suite"
    echo [INFO]   Removed build\Salva Suite\
)
if exist "dist\Salva Suite" (
    rmdir /s /q "dist\Salva Suite"
    echo [INFO]   Removed dist\Salva Suite\
)

REM ---- Run PyInstaller ----
echo.
echo [BUILD] Starting PyInstaller...
echo.

python -m PyInstaller build_windows.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo [ERROR] Build FAILED. Check output above for details.
    pause & exit /b 1
)

REM ---- Post-build verification ----
set EXE_PATH=dist\Salva Suite\Salva Suite.exe
if not exist "%EXE_PATH%" (
    echo [ERROR] Executable not found at: %EXE_PATH%
    pause & exit /b 1
)

for %%A in ("%EXE_PATH%") do set EXE_SIZE=%%~zA
set /a EXE_MB=!EXE_SIZE! / 1048576

REM ---- Measure total dist size ----
set DIST_DIR=dist\Salva Suite
for /f %%A in ('dir /s /b "%DIST_DIR%" ^| find /c /v ""') do set FILE_COUNT=%%A

echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo ============================================================
echo.
echo   Executable : %EXE_PATH%
echo   EXE size   : %EXE_MB% MB
echo   File count : %FILE_COUNT% files in dist\Salva Suite\
echo.
echo   To test: run  "%EXE_PATH%"
echo   To ship: zip  "dist\Salva Suite\"  and distribute.
echo.
echo ============================================================

pause
