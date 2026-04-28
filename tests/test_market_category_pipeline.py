"""
Test del pipeline de categorías sin conexión real a ESI.
Verifica que is_type_in_category funciona correctamente con metadatos conocidos de EVE.

Ejecutar desde la raíz del proyecto:
    python -m tests.test_market_category_pipeline
o:
    python tests/test_market_category_pipeline.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.item_categories import is_type_in_category

# ---------------------------------------------------------------------------
# Metadatos conocidos de EVE (verificados contra ESI)
# Formato: (description, category_id, group_id, item_name,
#            expected_Naves, expected_Drones, expected_Ore, expected_Modulos)
# ---------------------------------------------------------------------------
KNOWN_ITEMS = [
    # Ships — category_id=6
    ("Ares (Interceptor)",          6,   830,  "Ares",                        True,  False, False, False),
    ("Enyo (Assault Frigate)",      6,   324,  "Enyo",                        True,  False, False, False),
    # Drones — category_id=18
    ("Hobgoblin II (Combat Drone)", 18,  100,  "Hobgoblin II",                False, True,  False, False),
    ("Hornet EC-300 (EWAR Drone)",  18,  101,  "Hornet EC-300",               False, True,  False, False),
    # Ore / Ice — category_id=25
    ("Veldspar",                    25,  450,  "Veldspar",                    False, False, True,  False),
    ("Compressed Veldspar",         25,  450,  "Compressed Veldspar",         False, False, True,  False),
    # Modules — category_id=7, group NOT in rig exclusion set
    ("Damage Control II",           7,   60,   "Damage Control II",           False, False, False, True),
    ("Medium Shield Extender II",   7,   38,   "Medium Shield Extender II",   False, False, False, True),
    # Skill — category_id=16 — debe ser EXCLUIDO de Drones
    ("Drone Interfacing (Skill)",   16,  257,  "Drone Interfacing",           False, False, False, False),
    ("Drones (Skill)",              16,  257,  "Drones",                      False, False, False, False),
    # SKINs — category_id=91 — NO deben entrar en Naves
    ("Ares SKIN",                   91,  1950, "Ares Biosecurity SKIN",       False, False, False, False),
    # Rigs — group_id in rig exclusion set -> excluidos de Módulos
    ("Small Core Defense Field Ext II", 7, 773, "Small Core Defense Field Extender II", False, False, False, False),
]

def run_tests():
    passed = 0
    failed = 0
    print("\n=== test_market_category_pipeline ===\n")

    for desc, cat_id, grp_id, name, exp_nave, exp_drone, exp_ore, exp_modulo in KNOWN_ITEMS:
        for cat, expected in [
            ("Naves", exp_nave),
            ("Drones", exp_drone),
            ("Ore / Menas", exp_ore),
            ("Módulos", exp_modulo),
        ]:
            match, reason = is_type_in_category(cat, cat_id, grp_id, name)
            ok = match == expected
            status = "PASS" if ok else "FAIL"
            if not ok:
                failed += 1
                print(f"  [{status}] {desc} | cat_filter={cat} | expected={expected} | got={match} | reason={reason}")
            else:
                passed += 1

    print()

    # ── Casos especiales ──────────────────────────────────────────────────────

    # Strict mode: metadata faltante -> excluir
    match, reason = is_type_in_category("Naves", None, None, "Unknown")
    assert not match, f"Strict mode FAIL: esperaba False para metadata None, obtuve {match}"
    print("  [PASS] Strict mode: metadata=None -> excluido")

    # Todos: siempre pasa
    match, _ = is_type_in_category("Todos", None, None, "Anything")
    assert match, "Todos debería pasar siempre"
    print("  [PASS] Todos: metadata=None -> incluido")

    # Broad mode: Munición avanzada sin nombre -> pasa (para pre-selección en worker)
    match, reason = is_type_in_category("Munición avanzada", 8, 86, "", broad=True)
    assert match, f"Broad match FAIL: esperaba True para cat_id=8, obtuve {match} reason={reason}"
    print("  [PASS] Munición avanzada broad=True: cat_id=8, sin nombre -> incluido")

    # Non-broad: Munición avanzada requiere keyword
    match, _ = is_type_in_category("Munición avanzada", 8, 86, "Void M Ammo")
    assert match, "Void M Ammo debe coincidir con Munición avanzada"
    print("  [PASS] Munición avanzada: 'Void M Ammo' -> incluido")

    match, _ = is_type_in_category("Munición avanzada", 8, 86, "Iron Charge M")
    assert not match, "Iron Charge M no debe coincidir con Munición avanzada"
    print("  [PASS] Munición avanzada: 'Iron Charge M' -> excluido")

    print(f"\nResultados: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
