# EVE iT

Desktop utility suite for EVE multiboxing.

## Vision

EVE iT is being developed as a modular desktop suite for EVE Online multiboxing.

Main product modules:
- Tracker
- HUD
- Replicator
- Translator
- Control Center

Main product priority:
- the application must feel as fluid as possible

## Current direction

We are continuing development with:
- Python as the core runtime
- PySide6 as the desktop shell
- Streamlit as the analytics surface

We are **not** migrating to Tauri at this stage.

## 🛠️ Estructura del Proyecto

- **core/**: Lógica de negocio, motores de analítica y gestión de datos.
- **ui/**: Interfaces gráficas (Dashboard, Market Command).
- **tools/**: Herramientas de desarrollo, scripts de depuración y utilidades.
- **data/**: (*Ignorado por Git*) Almacena bases de datos locales y caches de identidad.
- **config/**: Configuraciones por defecto del sistema.

## 💾 Datos Locales e Higiene

Este repositorio sigue una política estricta de higiene. Las bases de datos (`.db`) y archivos de cache de identidad se mantienen exclusivamente en local para proteger la privacidad del usuario y evitar colisiones de datos. El sistema regenerará automáticamente las estructuras necesarias en el primer arranque.

## 🚀 Instalación y Uso

## Roadmap

Project roadmap:
- `docs/roadmap/eve-it-suite-roadmap.md`
