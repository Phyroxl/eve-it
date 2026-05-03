# Compilación de Salva Suite para Windows

Este documento detalla cómo generar el ejecutable `.exe` para distribuir Salva Suite en sistemas Windows.

## Requisitos Previos

1. **Python 3.10+**: Asegúrate de tener Python instalado y en el PATH.
2. **Dependencias del Proyecto**: Instaladas vía `pip install -r requirements.txt`.
3. **PyInstaller**: Herramienta de empaquetado.
   ```powershell
   pip install pyinstaller
   ```

## Proceso de Compilación

Hemos incluido un script de automatización en PowerShell:

1. Abre una terminal (PowerShell) en la raíz del proyecto.
2. Ejecuta el script:
   ```powershell
   ./build_windows.ps1
   ```

### ¿Qué hace el script?
- Elimina carpetas temporales de compilaciones anteriores (`build/`, `dist/`).
- Empaqueta `main.py` junto con todos los módulos de `controller/`, `core/`, `overlay/`, `ui/` y `utils/`.
- Incluye las carpetas `assets/` (sonidos, iconos, fondos) y `config/` (parámetros base).
- Configura el icono de la aplicación (`assets/icon.png`).
- Genera un ejecutable en modo **Windowed** (sin consola negra de fondo).

## Resultado

Una vez finalizado, encontrarás la aplicación lista en:
`dist/SalvaSuite/SalvaSuite.exe`

> **Nota**: Debes compartir toda la carpeta `dist/SalvaSuite/` (o comprimirla en un .zip) con tu amigo, ya que el modo `--onedir` mantiene las librerías dinámicas fuera del binario principal para mayor estabilidad y velocidad de carga.

## Solución de Problemas

### Error: "No se encuentra assets/icon.png"
Asegúrate de que el archivo existe en la carpeta `assets/`. Si prefieres compilar sin icono, elimina el flag `--icon` en el script `build_windows.ps1`.

### Antivirus bloquea el .exe
Al ser un ejecutable sin firmar digitalmente, algunos antivirus (como Windows Defender) pueden marcarlo como sospechoso. Es necesario añadir una excepción o "Ejecutar de todas formas".

### Error de rutas en ejecución
Si la app crashea al buscar sonidos o imágenes, verifica que `utils/paths.py` esté configurado correctamente con `get_resource_path`.
