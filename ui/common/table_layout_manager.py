"""Table column layout persistence — save/restore widths, order, hidden state."""
import json
import logging
from pathlib import Path

_log = logging.getLogger("eve.table_layout")
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "table_layouts.json"


def _load_all() -> dict:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _log.warning(f"[TABLE_LAYOUT] Could not load {_CONFIG_PATH}: {e}")
    return {}


def _save_all(data: dict):
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        _log.warning(f"[TABLE_LAYOUT] Could not save {_CONFIG_PATH}: {e}")


def save_table_layout(table, table_id: str):
    """Save column widths, logical order, and hidden state for a QTableWidget or QTableView."""
    try:
        header = table.horizontalHeader()
        col_count = header.count()
        layout = {
            "columns": [
                {
                    "logical": i,
                    "visual": header.visualIndex(i),
                    "width": header.sectionSize(i),
                    "hidden": header.isSectionHidden(i),
                }
                for i in range(col_count)
            ]
        }
        all_layouts = _load_all()
        all_layouts[table_id] = layout
        _save_all(all_layouts)
        _log.debug(f"[TABLE_LAYOUT] Saved layout for '{table_id}' ({col_count} columns)")
    except Exception as e:
        _log.warning(f"[TABLE_LAYOUT] save_table_layout('{table_id}') failed: {e}")


def restore_table_layout(table, table_id: str):
    """Restore column widths, order, and hidden state. Silently skips missing columns."""
    try:
        all_layouts = _load_all()
        layout = all_layouts.get(table_id)
        if not layout:
            return
        header = table.horizontalHeader()
        col_count = header.count()
        cols = layout.get("columns", [])
        for col in cols:
            logical = col.get("logical", -1)
            if logical < 0 or logical >= col_count:
                continue
            w = col.get("width")
            hidden = col.get("hidden", False)
            visual = col.get("visual")
            if w and w > 0:
                header.resizeSection(logical, w)
            if hidden:
                header.hideSection(logical)
            else:
                header.showSection(logical)
            # Restore visual order
            if visual is not None:
                current_visual = header.visualIndex(logical)
                if current_visual != visual:
                    header.moveSection(current_visual, visual)
        _log.debug(f"[TABLE_LAYOUT] Restored layout for '{table_id}'")
    except Exception as e:
        _log.warning(f"[TABLE_LAYOUT] restore_table_layout('{table_id}') failed: {e}")


def connect_table_layout_persistence(table, table_id: str):
    """Wire up sectionResized and sectionMoved signals to auto-save layout."""
    try:
        header = table.horizontalHeader()
        header.sectionResized.connect(lambda *_: save_table_layout(table, table_id))
        header.sectionMoved.connect(lambda *_: save_table_layout(table, table_id))
        _log.debug(f"[TABLE_LAYOUT] Connected persistence for '{table_id}'")
    except Exception as e:
        _log.warning(f"[TABLE_LAYOUT] connect_table_layout_persistence('{table_id}') failed: {e}")
