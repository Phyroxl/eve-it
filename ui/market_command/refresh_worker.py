import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QThread, Signal
from core.esi_client import ESIClient
from core.market_engine import parse_opportunities, score_opportunity
from core.market_models import FilterConfig
from core.item_resolver import ItemResolver
from core.item_categories import is_type_in_category
from core.market_history_cache import MarketHistoryCache

logger = logging.getLogger('eve.market.worker')

_TODOS_POOL_SIZE = 200      # Pool global para "Todos" (sin metadata, rápido)
_BROAD_POOL_SIZE = 500      # Pool amplio para prefetch de metadata en categorías específicas
_CATEGORY_LIMIT = 300       # Máximo candidatos por categoría tras filtro
_HISTORY_WORKERS = 8        # Clientes ESI paralelos para descarga de historial


class MarketRefreshWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(list)
    error = Signal(str)

    # Señales progresivas
    initial_data_ready = Signal(list)    # Fase 1: resultados rápidos sin historial
    enriched_data_ready = Signal(list)   # Fase 2: resultados completos con historial

    # Legacy signals para compatibilidad
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

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────────────────────────────────
    def run(self):
        try:
            t_total = time.time()
            selected_category = getattr(self.config, 'selected_category', 'Todos')

            # ──────────────────────────────────────────────────────────────────
            # FASE 1 — SNAPSHOT RÁPIDO (objetivo: < 15 segundos)
            # ──────────────────────────────────────────────────────────────────

            # Paso 1: Descargar market orders
            t0 = time.time()
            self.emit_progress(5, "Fetching market orders...")
            orders = self.client.market_orders(self.region_id)
            if not self.is_running: return
            if not orders:
                self.emit_error("Failed to fetch market orders.")
                return
            t_orders = time.time() - t0
            logger.info(f"[SCAN PERF] market_orders_elapsed={t_orders:.1f}s raw_orders={len(orders)}")

            # Paso 2: Agrupar por type_id
            t0 = time.time()
            temp_grouped = {}
            for o in orders:
                t = o['type_id']
                if t not in temp_grouped:
                    temp_grouped[t] = {'buy': [], 'sell': []}
                if o['is_buy_order']:
                    temp_grouped[t]['buy'].append(o)
                else:
                    temp_grouped[t]['sell'].append(o)
            logger.info(f"[SCAN PERF] grouping_elapsed={time.time()-t0:.2f}s grouped_type_ids={len(temp_grouped)}")

            # Paso 3: Pool económico (sin filtros de capital/margen para red amplia)
            t0 = time.time()
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
                economic_candidates.append({
                    'type_id': t_id,
                    'margin': margin,
                    'orders_count': orders_count,
                    'score': max(0.0, margin) * min(orders_count, 50)
                })
            economic_candidates.sort(key=lambda x: x['score'], reverse=True)
            t_candidates = time.time() - t0
            logger.info(
                f"[SCAN PERF] candidate_selection_elapsed={t_candidates:.2f}s "
                f"economic_candidates={len(economic_candidates)}"
            )
            self.emit_progress(18, f"Found {len(economic_candidates)} economic candidates.")

            # Paso 4: Candidatos iniciales de Fase 1 (solo desde metadata en caché, sin ESI)
            t0 = time.time()
            if selected_category == "Todos":
                initial_candidates = [c['type_id'] for c in economic_candidates[:_TODOS_POOL_SIZE]]
                logger.info(f"[WORKER PIPELINE] Phase1 mode=Todos initial_candidates={len(initial_candidates)}")
            else:
                # Solo items con metadata ya en caché → sin llamadas ESI en Fase 1
                resolver = ItemResolver.instance()
                initial_candidates = []
                for c in economic_candidates[:_BROAD_POOL_SIZE]:
                    t_id = c['type_id']
                    cat_id, grp_id, _, _ = resolver.resolve_category_info(t_id, blocking=False)
                    if cat_id is not None and grp_id is not None:
                        match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                        if match:
                            initial_candidates.append(t_id)
                logger.info(
                    f"[WORKER PIPELINE] Phase1 mode=category={selected_category} "
                    f"initial_candidates_from_cache={len(initial_candidates)}"
                )

            # Excluir PLEX
            plex_id = 44992
            if self.config.exclude_plex and plex_id in initial_candidates:
                initial_candidates.remove(plex_id)

            logger.info(f"[SCAN PERF] Phase1_candidates_elapsed={time.time()-t0:.2f}s")

            # Paso 5: Nombres en batch para candidatos iniciales
            t0 = time.time()
            self.emit_progress(25, f"Fetching names for {len(initial_candidates)} items...")
            names_dict = {}
            if initial_candidates:
                chunk_size = 500
                for i in range(0, len(initial_candidates), chunk_size):
                    chunk = initial_candidates[i:i + chunk_size]
                    names_data = self.client.universe_names(chunk)
                    if names_data:
                        for n in names_data:
                            names_dict[n['id']] = n['name']
            logger.info(f"[SCAN PERF] names_elapsed={time.time()-t0:.2f}s names_loaded={len(names_dict)}")

            # Paso 6: Crear oportunidades iniciales SIN historial
            t0 = time.time()
            self.emit_progress(35, "Creating initial opportunities...")
            initial_set = set(initial_candidates)
            relevant_orders_initial = [o for o in orders if o['type_id'] in initial_set]
            opps_initial = parse_opportunities(relevant_orders_initial, {}, names_dict, self.config)
            for opp in opps_initial:
                opp.is_enriched = False
                opp.score_breakdown = score_opportunity(opp, self.config)

            t_initial_emit = time.time() - t0
            logger.info(
                f"[SCAN PERF] initial_emit_elapsed={t_initial_emit:.2f}s "
                f"initial_opportunities={len(opps_initial)}"
            )

            # Emitir resultados iniciales a la UI
            self.emit_progress(50, f"Initial results: {len(opps_initial)} items. Enriching...")
            self.initial_data_ready.emit(opps_initial)

            if not self.is_running: return

            # ──────────────────────────────────────────────────────────────────
            # FASE 2 — ENRIQUECIMIENTO AUTOMÁTICO (historial + metadata completa)
            # ──────────────────────────────────────────────────────────────────

            t_phase2_start = time.time()
            self.emit_progress(52, "Phase 2: expanding metadata...")

            # Paso 7: Determinar candidatos finales con metadata completa
            t0 = time.time()
            if selected_category == "Todos":
                final_candidates = [c['type_id'] for c in economic_candidates[:_TODOS_POOL_SIZE]]
                logger.info(f"[WORKER PIPELINE] Phase2 mode=Todos final_candidates={len(final_candidates)}")
            else:
                # Prefetch metadata paralelo para pool amplio
                broad_ids = [c['type_id'] for c in economic_candidates[:_BROAD_POOL_SIZE]]
                self.emit_progress(54, f"Prefetching metadata for {len(broad_ids)} items (parallel)...")
                p_stats = ItemResolver.instance().prefetch_type_metadata_parallel(broad_ids, n_clients=4)
                if not self.is_running: return
                logger.info(
                    f"[WORKER PIPELINE] metadata total={p_stats['total']} "
                    f"cached={p_stats['cached']} fetched={p_stats['fetched']} failed={p_stats['failed']}"
                )

                self.emit_progress(65, f"Filtering by category '{selected_category}'...")
                category_ids = []
                for c in economic_candidates[:_BROAD_POOL_SIZE]:
                    t_id = c['type_id']
                    cat_id, grp_id, _, _ = ItemResolver.instance().resolve_category_info(t_id, blocking=False)
                    match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                    if match:
                        category_ids.append(t_id)

                logger.info(
                    f"[WORKER PIPELINE] category_pool={len(category_ids)} "
                    f"category={selected_category} broad_pool={_BROAD_POOL_SIZE}"
                )

                if not category_ids:
                    logger.warning(
                        f"[WORKER PIPELINE] 0 candidates for category={selected_category}. "
                        f"metadata_failed={p_stats['failed']}. "
                        f"Emitting initial results only."
                    )
                    # No hay candidatos → terminar con los resultados iniciales
                    self.emit_progress(100, f"No items found for '{selected_category}'")
                    self.enriched_data_ready.emit(opps_initial)
                    self.finished.emit(opps_initial)
                    self.data_ready.emit(opps_initial)
                    return

                final_candidates = category_ids[:_CATEGORY_LIMIT]
                logger.info(f"[WORKER PIPELINE] Phase2 final_candidates={len(final_candidates)}")

            t_metadata = time.time() - t0
            logger.info(f"[SCAN PERF] metadata_elapsed={t_metadata:.1f}s")

            if self.config.exclude_plex and plex_id in final_candidates:
                final_candidates.remove(plex_id)

            # Paso 8: History cache hits
            t0 = time.time()
            self.emit_progress(68, "Checking history cache...")
            hist_cache = MarketHistoryCache.instance()
            history_hits = hist_cache.get_many(self.region_id, final_candidates)
            missing_hist = [t for t in final_candidates if t not in history_hits]
            logger.info(
                f"[HISTORY CACHE] candidates={len(final_candidates)} "
                f"hits={len(history_hits)} misses={len(missing_hist)}"
            )

            # Paso 9: Descarga concurrente de historial faltante
            fetched_history = {}
            failed_hist = 0
            if missing_hist:
                self.emit_progress(70, f"Fetching history for {len(missing_hist)} items (parallel)...")
                # Pool de ESIClient independientes → cada uno con su propio rate limiter
                _workers = min(_HISTORY_WORKERS, len(missing_hist))
                hist_pool = [ESIClient() for _ in range(_workers)]

                def fetch_hist(args):
                    idx, type_id = args
                    client = hist_pool[idx % _workers]
                    try:
                        hist = client.market_history(self.region_id, type_id)
                        return type_id, hist
                    except Exception as e:
                        logger.debug(f"[HISTORY FETCH] error type_id={type_id}: {e}")
                        return type_id, None

                with ThreadPoolExecutor(max_workers=_workers) as executor:
                    futures_map = {executor.submit(fetch_hist, (i, t)): t
                                   for i, t in enumerate(missing_hist)}
                    done = 0
                    for future in as_completed(futures_map):
                        if not self.is_running:
                            break
                        try:
                            type_id, hist = future.result()
                            if hist:
                                fetched_history[type_id] = hist
                            else:
                                failed_hist += 1
                        except Exception as e:
                            failed_hist += 1
                            logger.debug(f"[HISTORY FETCH] future error: {e}")
                        done += 1
                        if done % 20 == 0:
                            pct = 70 + int((done / max(len(missing_hist), 1)) * 15)
                            self.emit_progress(pct, f"History: {done}/{len(missing_hist)}")

            t_history = time.time() - t0
            logger.info(
                f"[HISTORY FETCH] workers={_HISTORY_WORKERS if missing_hist else 0} "
                f"fetched={len(fetched_history)} failed={failed_hist} "
                f"elapsed={t_history:.1f}s"
            )

            # Actualizar cache de historial en disco
            for t_id, hist in fetched_history.items():
                hist_cache.set(self.region_id, t_id, hist)
            if fetched_history:
                hist_cache.save()

            # Merge historial completo
            history_dict = {**history_hits, **fetched_history}

            # Paso 10: Nombres para nuevos candidatos (Fase 2 puede tener más que Fase 1)
            t0 = time.time()
            new_ids = [t for t in final_candidates if t not in names_dict]
            if new_ids:
                self.emit_progress(87, f"Fetching names for {len(new_ids)} new items...")
                for i in range(0, len(new_ids), 500):
                    chunk = new_ids[i:i + 500]
                    names_data = self.client.universe_names(chunk)
                    if names_data:
                        for n in names_data:
                            names_dict[n['id']] = n['name']
            logger.info(f"[SCAN PERF] names_phase2_elapsed={time.time()-t0:.2f}s total_names={len(names_dict)}")

            if not self.is_running: return

            # Paso 11: Parsear oportunidades enriquecidas
            t0 = time.time()
            self.emit_progress(90, "Parsing enriched opportunities...")
            final_set = set(final_candidates)
            relevant_orders_enriched = [o for o in orders if o['type_id'] in final_set]
            opps_enriched = parse_opportunities(relevant_orders_enriched, history_dict, names_dict, self.config)
            for opp in opps_enriched:
                opp.is_enriched = True
                opp.score_breakdown = score_opportunity(opp, self.config)

            t_enrich = time.time() - t0
            t_total_elapsed = time.time() - t_total
            logger.info(
                f"[SCAN PERF] enriched_emit_elapsed={t_enrich:.2f}s "
                f"enriched_opportunities={len(opps_enriched)}"
            )
            logger.info(
                f"[SCAN PERF] total_elapsed={t_total_elapsed:.1f}s "
                f"phase2_elapsed={time.time()-t_phase2_start:.1f}s"
            )

            self.last_results = opps_enriched
            self.emit_progress(100, f"Done. {len(opps_enriched)} enriched items.")
            self.enriched_data_ready.emit(opps_enriched)
            self.finished.emit(opps_enriched)
            self.data_ready.emit(opps_enriched)  # legacy compat

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
