import logging
from PySide6.QtCore import QThread, Signal
from core.esi_client import ESIClient
from core.market_engine import parse_opportunities, score_opportunity
from core.market_models import FilterConfig
from core.item_resolver import ItemResolver
from core.item_categories import is_type_in_category

logger = logging.getLogger('eve.market.worker')

# Pool sizes — ajustar si se necesita más cobertura o menor latencia
_TODOS_POOL_SIZE = 200      # Top N global para "Todos" (sin metadata, rápido)
_BROAD_POOL_SIZE = 2000     # Pool amplio para pre-selección de categorías específicas
_CATEGORY_LIMIT = 300       # Máximo de candidatos por categoría después del filtro

class MarketRefreshWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(list)
    error = Signal(str)

    # Legacy signals for compatibility
    progress_changed = Signal(int, str)
    data_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, region_id=10000002, config=None):
        super().__init__()
        self.region_id = region_id
        self.client = ESIClient()
        self.config = config if config else FilterConfig()
        self.is_running = True
        self.last_results = []

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            selected_category = getattr(self.config, 'selected_category', 'Todos')

            # ── Paso 1: Descargar órdenes de mercado ──────────────────────────────
            self.emit_progress(5, "Fetching market orders...")
            orders = self.client.market_orders(self.region_id)
            if not self.is_running: return
            if not orders:
                self.emit_error("Failed to fetch market orders.")
                return

            logger.info(f"[WORKER PIPELINE] selected_category={selected_category} raw_orders={len(orders)}")
            self.emit_progress(12, f"Fetched {len(orders)} orders. Grouping by item...")

            # ── Paso 2: Agrupar por type_id ──────────────────────────────────────
            temp_grouped = {}
            for o in orders:
                t = o['type_id']
                if t not in temp_grouped:
                    temp_grouped[t] = {'buy': [], 'sell': []}
                if o['is_buy_order']:
                    temp_grouped[t]['buy'].append(o)
                else:
                    temp_grouped[t]['sell'].append(o)

            logger.info(f"[WORKER PIPELINE] grouped_type_ids={len(temp_grouped)}")

            # ── Paso 3: Pool económico (sin restricciones de capital/margen) ─────
            # Filtro mínimo: al menos 1 buy Y 1 sell con precios positivos.
            # Sin filtro de capital/margen aquí — apply_filters lo gestiona en la UI.
            b_fee = self.config.broker_fee_pct / 100.0
            s_tax = self.config.sales_tax_pct / 100.0

            economic_candidates = []
            for t_id, group in temp_grouped.items():
                if not group['buy'] or not group['sell']:
                    continue
                best_buy = max(o['price'] for o in group['buy'])
                best_sell = min(o['price'] for o in group['sell'])
                if best_buy <= 0 or best_sell <= 0:
                    continue
                profit = best_sell * (1.0 - s_tax - b_fee) - best_buy * (1.0 + b_fee)
                margin = (profit / best_buy) * 100 if best_buy > 0 else 0
                orders_count = len(group['buy']) + len(group['sell'])
                # score=0 para márgenes negativos; así flotan al fondo sin excluirlos del pool
                economic_candidates.append({
                    'type_id': t_id,
                    'margin': margin,
                    'orders_count': orders_count,
                    'score': max(0.0, margin) * min(orders_count, 50)
                })

            economic_candidates.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"[WORKER PIPELINE] economic_candidates={len(economic_candidates)}")
            self.emit_progress(18, f"Found {len(economic_candidates)} economic candidates.")

            # ── Paso 4: Selección de candidatos según categoría ───────────────────
            if selected_category == "Todos":
                # Ruta rápida: top N global, sin prefetch de metadata
                candidates = [c['type_id'] for c in economic_candidates[:_TODOS_POOL_SIZE]]
                logger.info(f"[WORKER PIPELINE] mode=Todos final_candidates={len(candidates)}")
                self.emit_progress(22, f"Pool 'Todos': {len(candidates)} candidates selected.")

            else:
                # Ruta category-aware: pool amplio → metadata → filtro por categoría
                broad_ids = [c['type_id'] for c in economic_candidates[:_BROAD_POOL_SIZE]]
                logger.info(f"[WORKER PIPELINE] mode=category={selected_category} category_pool_before_meta={len(broad_ids)}")

                self.emit_progress(22, f"Prefetching metadata for {len(broad_ids)} candidates...")
                p_stats = ItemResolver.instance().prefetch_type_metadata(broad_ids, max_workers=8)
                if not self.is_running: return
                logger.info(
                    f"[WORKER PIPELINE] metadata total={p_stats['total']} "
                    f"cached={p_stats['cached']} fetched={p_stats['fetched']} failed={p_stats['failed']}"
                )

                self.emit_progress(42, f"Filtering by category '{selected_category}'...")
                category_ids = []
                for c in economic_candidates[:_BROAD_POOL_SIZE]:
                    t_id = c['type_id']
                    cat_id, grp_id, _, _ = ItemResolver.instance().resolve_category_info(t_id, blocking=False)
                    # broad=True: omite keyword-check (no tenemos nombres aún)
                    match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                    if match:
                        category_ids.append(t_id)

                logger.info(
                    f"[WORKER PIPELINE] category_pool_after={len(category_ids)} "
                    f"category={selected_category} broad_pool={len(broad_ids)}"
                )

                if not category_ids:
                    logger.warning(
                        f"[WORKER PIPELINE] 0 candidates for category={selected_category} "
                        f"in broad_pool={_BROAD_POOL_SIZE}. metadata_failed={p_stats['failed']}. "
                        f"Possible causes: (1) items not in top {_BROAD_POOL_SIZE} economic pool, "
                        f"(2) metadata not cached yet (retry), (3) category genuinely absent in this region."
                    )
                    self.emit_error(
                        f"Sin candidatos para '{selected_category}'. "
                        f"Si es la primera vez, espera a que se descargue la metadata y vuelve a escanear."
                    )
                    return

                # Los IDs ya están ordenados por score económico (heredado de economic_candidates)
                candidates = category_ids[:_CATEGORY_LIMIT]
                logger.info(f"[WORKER PIPELINE] final_candidates={len(candidates)} (limit={_CATEGORY_LIMIT})")
                self.emit_progress(45, f"Category '{selected_category}': {len(candidates)} candidates found.")

            # Excluir PLEX si está configurado
            plex_id = 44992
            if self.config.exclude_plex and plex_id in candidates:
                candidates.remove(plex_id)

            total_candidates = len(candidates)
            candidates_set = set(candidates)

            # ── Paso 5: Descargar historial para el pool de candidatos ─────────────
            self.emit_progress(47, f"Fetching history for {total_candidates} items...")
            history_dict = {}
            for i, cid in enumerate(candidates):
                if not self.is_running: return
                hist = self.client.market_history(self.region_id, cid)
                if hist:
                    history_dict[cid] = hist
                if i % 10 == 0:
                    pct = 47 + int((i / max(total_candidates, 1)) * 35)
                    self.emit_progress(pct, f"History: {i}/{total_candidates}")

            if not self.is_running: return

            # ── Paso 6: Descargar nombres en batch ────────────────────────────────
            self.emit_progress(84, "Fetching item names...")
            names_dict = {}
            chunk_size = 500
            for i in range(0, len(candidates), chunk_size):
                chunk = candidates[i:i + chunk_size]
                names_data = self.client.universe_names(chunk)
                if names_data:
                    for n in names_data:
                        names_dict[n['id']] = n['name']

            # ── Paso 7: Parsear oportunidades solo para candidatos ────────────────
            self.emit_progress(90, "Parsing opportunities...")
            # Filtramos las órdenes al pool de candidatos para no parsear miles de tipos
            relevant_orders = [o for o in orders if o['type_id'] in candidates_set]
            opps = parse_opportunities(relevant_orders, history_dict, names_dict, self.config)

            # ── Paso 8: Scoring ───────────────────────────────────────────────────
            self.emit_progress(96, "Scoring...")
            for opp in opps:
                opp.score_breakdown = score_opportunity(opp, self.config)

            logger.info(f"[WORKER PIPELINE] emitted_opportunities={len(opps)}")

            # IMPORTANTE: NO llamar apply_filters aquí.
            # La vista llama apply_filters() una sola vez sobre all_opportunities.
            self.last_results = opps
            self.emit_progress(100, "Done")
            self.finished.emit(opps)
            self.data_ready.emit(opps)

        except Exception as e:
            import traceback
            logger.error(f"[WORKER ERROR] {e}\n{traceback.format_exc()}")
            self.emit_error(str(e))

    def emit_progress(self, pct, text):
        self.progress.emit(pct)
        self.status.emit(text)
        self.progress_changed.emit(pct, text)

    def emit_error(self, msg):
        self.error.emit(msg)
        self.error_occurred.emit(msg)
