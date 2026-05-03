# build_windows.ps1 — Script de compilación para Salva Suite
# Este script genera un ejecutable de Windows usando PyInstaller.

Write-Host "--- INICIANDO BUILD DE SALVA SUITE ---" -ForegroundColor Cyan

# 1. Limpieza de builds previos
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# 2. Verificar dependencias
Write-Host "Verificando PyInstaller..."
python -m PyInstaller --version > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: PyInstaller no está disponible como módulo de Python. Ejecuta 'pip install pyinstaller'" -ForegroundColor Red
    exit 1
}

# 3. Ejecutar PyInstaller
Write-Host "Compilando usando SalvaSuite.spec..."
python -m PyInstaller --noconfirm --clean SalvaSuite.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n--- BUILD COMPLETADO EXITOSAMENTE ---" -ForegroundColor Green
    Write-Host "Resultado en: dist/SalvaSuite/SalvaSuite.exe"
} else {
    Write-Host "`n--- ERROR EN EL BUILD ---" -ForegroundColor Red
    exit $LASTEXITCODE
}
