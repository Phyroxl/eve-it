"""
debug_db.py — Diagnóstico completo de market_performance.db
Ejecutar desde terminal: python debug_db.py
"""
import sqlite3
import os
from datetime import datetime, timezone

def debug_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "data", "market_performance.db")

    print(f"\n{'='*60}")
    print(f"  DIAGNÓSTICO: market_performance.db")
    print(f"  Ruta: {db_path}")
    print(f"  Hora: {datetime.now(timezone.utc).isoformat()} UTC")
    print(f"{'='*60}")

    if not os.path.exists(db_path):
        print(f"\n  ERROR: El archivo NO existe.")
        print(f"  → La sync nunca se ha ejecutado o la ruta es incorrecta.")
        return

    size_kb = os.path.getsize(db_path) / 1024
    print(f"\n  Tamaño del archivo: {size_kb:.1f} KB")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # ── 1. SNAPSHOTS ─────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  [wallet_snapshots] — Balance por personaje")
    print(f"{'─'*60}")
    c.execute("SELECT character_id, balance, date FROM wallet_snapshots ORDER BY date DESC")
    rows = c.fetchall()
    if not rows:
        print("  (vacío — sync nunca ejecutada o token inválido en el paso de balance)")
    for r in rows:
        print(f"  char_id={r[0]}  balance={r[1]:,.0f} ISK  fecha={r[2]}")

    # ── 2. TRANSACCIONES ─────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  [wallet_transactions] — Agrupado por personaje")
    print(f"{'─'*60}")
    c.execute("""
        SELECT character_id, COUNT(*),
               MIN(substr(date,1,10)), MAX(substr(date,1,10))
        FROM wallet_transactions
        GROUP BY character_id
    """)
    rows = c.fetchall()
    if not rows:
        print("  (vacío — ESI devolvió 0 transacciones o el guardado falló)")
    for r in rows:
        print(f"  char_id={r[0]}  count={r[1]}  desde={r[2]}  hasta={r[3]}")

    # ── 3. TRANSACCIONES — Últimas 10 ────────────────────────────
    print(f"\n{'─'*60}")
    print("  [wallet_transactions] — Últimas 10 filas (todas las columnas clave)")
    print(f"{'─'*60}")
    c.execute("""
        SELECT transaction_id, character_id, substr(date,1,10), item_name, quantity, unit_price, is_buy
        FROM wallet_transactions
        ORDER BY date DESC LIMIT 10
    """)
    rows = c.fetchall()
    if not rows:
        print("  (sin datos)")
    for r in rows:
        tipo = "COMPRA" if r[6] == 1 else "VENTA"
        print(f"  tx={r[0]}  char={r[1]}  {r[2]}  {r[4]}x {r[3] or '?'}  @{r[5]:,.0f}  {tipo}")

    # ── 4. JOURNAL ────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  [wallet_journal] — Agrupado por personaje y tipo")
    print(f"{'─'*60}")
    c.execute("""
        SELECT character_id, ref_type, COUNT(*)
        FROM wallet_journal
        GROUP BY character_id, ref_type
    """)
    rows = c.fetchall()
    if not rows:
        print("  (vacío)")
    for r in rows:
        print(f"  char_id={r[0]}  ref_type={r[1]}  count={r[2]}")

    # ── 5. RESUMEN / DIAGNÓSTICO FINAL ───────────────────────────
    print(f"\n{'='*60}")
    print("  DIAGNÓSTICO FINAL")
    print(f"{'='*60}")

    c.execute("SELECT COUNT(DISTINCT character_id) FROM wallet_snapshots")
    n_chars_snap = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT character_id) FROM wallet_transactions")
    n_chars_trans = c.fetchone()[0]

    if n_chars_snap == 0:
        print("  ❌ Sin snapshots → la sync no llegó al paso de balance.")
        print("     Causa probable: token inválido, scope incorrecto o error de red.")
    elif n_chars_trans == 0:
        print("  ⚠️  Hay snapshots pero 0 transacciones.")
        print("     Causa probable: ESI /wallet/transactions/ devolvió [].")
        print("     → Personaje sin historial de trading reciente (últimos 30d)")
        print("     → O el scope esi-wallet.read_character_wallet.v1 falló solo para ese endpoint.")
        print("     → Comprueba el log de la app: busca '[POLL] Transacciones: 0 recibidas'")
    else:
        print("  ✅ Hay snapshots Y transacciones en DB.")
        print("     Si la UI sigue a 0, el problema está en el filtro de fecha o el char_id del combo.")
        # Verificar si los char_ids coinciden
        c.execute("SELECT DISTINCT character_id FROM wallet_snapshots")
        snap_ids = set(r[0] for r in c.fetchall())
        c.execute("SELECT DISTINCT character_id FROM wallet_transactions")
        trans_ids = set(r[0] for r in c.fetchall())
        if snap_ids != trans_ids:
            print(f"\n  ❌ DESALINEACIÓN DE char_id:")
            print(f"     snapshots tienen: {snap_ids}")
            print(f"     transactions tienen: {trans_ids}")
            print(f"     → Los datos se guardaron con IDs distintos. Esto es el bug.")
        else:
            print(f"\n  IDs consistentes: {snap_ids}")
            print(f"  → El combo de la UI debe usar uno de estos IDs.")

    conn.close()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    debug_db()
