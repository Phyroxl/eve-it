# 🧩 Modules
Aquí residen los módulos independientes de la suite. Cada módulo debe ser lo más autónomo posible.

## Estructura de módulos:
- `tracker/`: Rastreo de actividades y estadísticas.
- `hud/`: Overlays de información en tiempo real.
- `replicator/`: Duplicación y gestión de ventanas (Espejos).
- `translator/`: Traducción inteligente de logs de chat.

## Migración futura:
- El contenido de `translator/` se moverá a `modules/translator/`.
- El contenido de `overlay/` (lógica de replicación) se moverá a `modules/replicator/`.
