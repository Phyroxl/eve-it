import copy
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QThread, Signal
from core.esi_client import ESIClient
from core.market_engine import parse_opportunities, score_opportunity
from core.market_models import FilterConfig
from core.item_resolver import ItemResolver
from core.item_categories import is_type_in_category
from core.market_history_cache import MarketHistoryCache
from core.market_scan_diagnostics import MarketScanDiagnostics
from core.market_candidate_selector import build_economic_candidates, prefilter_candidates, select_final_candidates

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
    diagnostics_ready = Signal(object) # NEW

    def __init__(self, region_id=10000002, config=None):
        super().__init__()
        self.region_id = region_id
        self.client = ESIClient()
        # Worker config is an immutable snapshot for this scan.
        # UI may change filters while enrichment continues — that's intentional.
        self.config = copy.deepcopy(config) if config else FilterConfig()
        self.is_running = True
        self.last_results = []
        
        # Initialize diagnostics
        self.diagnostics = MarketScanDiagnostics(
            scan_id=str(uuid.uuid4())[:8],
            started_at=time.time(),
            region_id=self.region_id,
            selected_category_worker=self.config.selected_category,
            worker_config_snapshot=self.config.__dict__.copy() if hasattr(self.config, '__dict__') else {}
        )

    def stop(self):
        self.is_running = False

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────────────────────────────────
    def run(self):
        try:
            t_start = time.time()
            selected_category = getattr(self.config, 'selected_category', 'Todos')
            self.diagnostics.mode = "Advanced" if "Advanced" in str(self.__class__) else "Simple"

            # ──────────────────────────────────────────────────────────────────
            # FASE 1 — SNAPSHOT RÁPIDO (objetivo: < 15 segundos)
            # ──────────────────────────────────────────────────────────────────
            self.diagnostics.notes.append("Starting Phase 1 (Initial Data)")

            # Paso 1: Descargar market orders
            t0 = time.time()
            self.emit_progress(5, "Fetching market orders...")
            logger.info(f"[WORKER DIAG] selected_category={selected_category} region_id={self.region_id}")
            
            orders = self.client.market_orders(self.region_id)
            if not self.is_running: return
            
            t_orders = time.time() - t0
            self.diagnostics.market_orders_elapsed = t_orders
            self.diagnostics.raw_orders_count = len(orders) if orders else 0

            if not orders:
                self.diagnostics.status = "Failed: No orders"
                logger.error("[WORKER DIAG] raw_orders=0 - Failed to fetch market orders.")
                self.emit_error("Failed to fetch market orders.")
                self.diagnostics.finished_at = time.time()
                self.diagnostics_ready.emit(self.diagnostics)
                return
            logger.info(f"[WORKER DIAG] raw_orders={len(orders)} elapsed={t_orders:.1f}s")

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
            t_group = time.time()-t0
            self.diagnostics.grouping_elapsed = t_group
            self.diagnostics.grouped_type_ids_count = len(temp_grouped)
            logger.info(f"[WORKER DIAG] grouped_type_ids={len(temp_grouped)} elapsed={t_group:.2f}s")

            # Paso 3: Construir pool de candidatos económicos
            t0 = time.time()
            all_cands = build_economic_candidates(temp_grouped, self.config)
            self.diagnostics.economic_candidates_count = len(all_cands)
            
            # Paso 4: Pre-filtro rápido (capital, spread, margin, plex)
            viable_cands, pre_stats = prefilter_candidates(all_cands, self.config)
            
            self.diagnostics.viable_candidates_count = len(viable_cands)
            self.diagnostics.prefilter_removed_capital = pre_stats.get("capital", 0)
            self.diagnostics.prefilter_removed_margin = pre_stats.get("margin", 0)
            self.diagnostics.prefilter_removed_spread = pre_stats.get("spread", 0)
            self.diagnostics.prefilter_removed_profit = pre_stats.get("profit", 0)
            self.diagnostics.prefilter_removed_plex = pre_stats.get("plex", 0)
            
            # Estadísticas de distribución de spread
            if all_cands:
                all_spreads = [c.spread_pct for c in all_cands]
                self.diagnostics.candidate_top_spread_min = min(all_spreads)
                self.diagnostics.candidate_top_spread_max = max(all_spreads)
                self.diagnostics.candidate_top_spread_avg = sum(all_spreads) / len(all_spreads)
            
            # Si no hay candidatos viables, fallback a los económicos pero con aviso
            final_pool_cands = viable_cands if viable_cands else all_cands
            if not viable_cands and all_cands:
                self.diagnostics.warnings.append("No viable candidates after pre-filter. Using raw economic candidates as fallback.")
            
            t_candidates = time.time() - t0
            self.diagnostics.candidate_selection_elapsed = t_candidates
            
            # Ordenar pool final por score una sola vez
            final_pool_cands = sorted(final_pool_cands, key=lambda x: x.score, reverse=True)
            
            logger.info(f"[WORKER DIAG] economic_cands={len(all_cands)} viable={len(viable_cands)} sorted_pool={len(final_pool_cands)} elapsed={t_candidates:.2f}s")
            self.emit_progress(18, f"Found {len(viable_cands)} viable candidates.")

            # Paso 5: Selección de candidatos iniciales (Fase 1)
            t0 = time.time()
            if selected_category == "Todos":
                # Seleccionar top N type_ids
                initial_candidates = select_final_candidates(final_pool_cands, _TODOS_POOL_SIZE)
                self.diagnostics.notes.append(f"Phase 1 using top {len(initial_candidates)} from final_pool")
            else:
                # Solo items con metadata ya en caché
                resolver = ItemResolver.instance()
                # Usamos el pool ya ordenado
                broad_stats = final_pool_cands[:_BROAD_POOL_SIZE]
                initial_candidates = []
                for c in broad_stats:
                    t_id = c.type_id
                    cat_id, grp_id, _, _ = resolver.resolve_category_info(t_id, blocking=False)
                    if cat_id is not None and grp_id is not None:
                        match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                        if match:
                            initial_candidates.append(t_id)
                self.diagnostics.notes.append(f"Phase 1 found {len(initial_candidates)} candidates for {selected_category}")
                logger.info(f"[WORKER DIAG] Phase1 category={selected_category} initial_candidates={len(initial_candidates)}")
                if not initial_candidates:
                    logger.warning(f"[WORKER DIAG] Phase1 category={selected_category} initial_candidates=0. metadata_cache_miss likely.")
                    self.emit_progress(40, f"Preparando metadata para {selected_category}...")

            self.diagnostics.initial_candidates_count = len(initial_candidates)

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
            t_names = time.time() - t0
            self.diagnostics.names_elapsed = t_names
            logger.info(f"[WORKER DIAG] names_dict={len(names_dict)} elapsed={t_names:.2f}s")

            # Paso 6: Crear oportunidades iniciales SIN historial
            t0 = time.time()
            self.emit_progress(35, "Creating initial opportunities...")
            initial_set = set(initial_candidates)
            relevant_orders_initial = [o for o in orders if o['type_id'] in initial_set]
            self.diagnostics.relevant_orders_initial_count = len(relevant_orders_initial)
            logger.info(f"[WORKER DIAG] relevant_orders_initial={len(relevant_orders_initial)}")
            
            opps_initial = parse_opportunities(relevant_orders_initial, {}, names_dict, self.config)
            for opp in opps_initial:
                opp.is_enriched = False
                opp.score_breakdown = score_opportunity(opp, self.config)

            t_initial_emit = time.time() - t0
            self.diagnostics.opps_initial_count = len(opps_initial)
            logger.info(f"[WORKER DIAG] opps_initial={len(opps_initial)} elapsed={t_initial_emit:.2f}s")

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
                final_candidates = select_final_candidates(final_pool_cands, _TODOS_POOL_SIZE)
                logger.info(f"[WORKER DIAG] Phase2 mode=Todos final_candidates={len(final_candidates)}")
            else:
                # Prefetch metadata paralelo para pool amplio
                broad_ids = [c.type_id for c in final_pool_cands[:_BROAD_POOL_SIZE]]
                self.emit_progress(54, f"Prefetching metadata for {len(broad_ids)} items (parallel)...")
                p_stats = ItemResolver.instance().prefetch_type_metadata_parallel(broad_ids, n_clients=4)
                if not self.is_running: return
                
                self.diagnostics.metadata_total = p_stats['total']
                self.diagnostics.metadata_cached = p_stats['cached']
                self.diagnostics.metadata_fetched = p_stats['fetched']
                self.diagnostics.metadata_failed = p_stats['failed']
                
                logger.info(
                    f"[WORKER DIAG] metadata total={p_stats['total']} "
                    f"cached={p_stats['cached']} fetched={p_stats['fetched']} failed={p_stats['failed']}"
                )

                self.emit_progress(65, f"Filtering by category '{selected_category}'...")
                category_ids = []
                for c in final_pool_cands[:_BROAD_POOL_SIZE]:
                    t_id = c.type_id
                    cat_id, grp_id, _, _ = ItemResolver.instance().resolve_category_info(t_id, blocking=False)
                    match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                    if match:
                        category_ids.append(t_id)

                logger.info(f"[WORKER DIAG] Phase2 category_ids={len(category_ids)} for category={selected_category}")
                final_candidates = category_ids[:_CATEGORY_LIMIT]

            # Estadísticas de distribución final
            if final_candidates:
                # Buscar stats de los elegidos
                final_stats = [c for c in final_pool_cands if c.type_id in set(final_candidates)]
                if final_stats:
                    spreads = [c.spread_pct for c in final_stats]
                    margins = [c.margin_pct for c in final_stats]
                    self.diagnostics.final_candidates_spread_min = min(spreads)
                    self.diagnostics.final_candidates_spread_max = max(spreads)
                    self.diagnostics.final_candidates_spread_avg = sum(spreads) / len(spreads)
                    self.diagnostics.final_candidates_margin_min = min(margins)
                    self.diagnostics.final_candidates_margin_max = max(margins)
                    self.diagnostics.final_candidates_margin_avg = sum(margins) / len(margins)
            
            self.diagnostics.final_candidates_count = len(final_candidates)

            t_metadata = time.time() - t0
            self.diagnostics.metadata_elapsed = t_metadata
            logger.info(f"[WORKER DIAG] metadata_elapsed={t_metadata:.1f}s final_candidates={len(final_candidates)}")

            if self.config.exclude_plex and plex_id in final_candidates:
                final_candidates.remove(plex_id)

            # Paso 8: History cache hits
            t0 = time.time()
            self.emit_progress(68, "Checking history cache...")
            hist_cache = MarketHistoryCache.instance()
            history_hits = hist_cache.get_many(self.region_id, final_candidates)
            missing_hist = [t for t in final_candidates if t not in history_hits]
            self.diagnostics.history_cache_hits = len(history_hits)
            self.diagnostics.history_cache_misses = len(missing_hist)
            logger.info(f"[WORKER DIAG] history_hits={len(history_hits)} history_misses={len(missing_hist)}")

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
            self.diagnostics.history_fetched = len(fetched_history)
            self.diagnostics.history_failed = failed_hist
            self.diagnostics.history_elapsed = t_history
            logger.info(f"[WORKER DIAG] fetched_history={len(fetched_history)} failed_hist={failed_hist} elapsed={t_history:.1f}s")

            # Actualizar cache de historial en disco
            for t_id, hist in fetched_history.items():
                hist_cache.set(self.region_id, t_id, hist)
            if fetched_history:
                hist_cache.save()

            # Merge historial completo
            history_dict = {**history_hits, **fetched_history}
            self.diagnostics.history_dict_count = len(history_dict)
            logger.info(f"[WORKER DIAG] total_history_dict={len(history_dict)}")

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
            logger.info(f"[WORKER DIAG] names_dict_total={len(names_dict)} elapsed={time.time()-t0:.2f}s")

            if not self.is_running: return

            # Paso 11: Parsear oportunidades enriquecidas
            t0 = time.time()
            self.emit_progress(90, "Parsing enriched opportunities...")
            final_set = set(final_candidates)
            relevant_orders_enriched = [o for o in orders if o['type_id'] in final_set]
            self.diagnostics.relevant_orders_enriched_count = len(relevant_orders_enriched)
            logger.info(f"[WORKER DIAG] relevant_orders_enriched={len(relevant_orders_enriched)}")
            
            # Diagnóstico de entrada a parse
            self.diagnostics.enriched_with_both_count = 0
            self.diagnostics.enriched_with_buy_count = 0
            self.diagnostics.enriched_with_sell_count = 0
            self.diagnostics.enriched_parse_input_sample = []
            
            # Análisis rápido de qué estamos mandando a parse
            temp_parse_map = {}
            for o in relevant_orders_enriched:
                tid = o['type_id']
                if tid not in temp_parse_map: temp_parse_map[tid] = {'buy': 0, 'sell': 0, 'prices': []}
                if o.get('is_buy_order'): temp_parse_map[tid]['buy'] += 1
                else: temp_parse_map[tid]['sell'] += 1
                temp_parse_map[tid]['prices'].append(o['price'])

            for tid, data in temp_parse_map.items():
                if data['buy'] > 0 and data['sell'] > 0: self.diagnostics.enriched_with_both_count += 1
                elif data['buy'] > 0: self.diagnostics.enriched_with_buy_count += 1
                elif data['sell'] > 0: self.diagnostics.enriched_with_sell_count += 1
                
                if len(self.diagnostics.enriched_parse_input_sample) < 10:
                    # Calcular spread rápido para el diagnóstico
                    spr = 0.0
                    try:
                        b = max([o['price'] for o in relevant_orders_enriched if o['type_id'] == tid and o.get('is_buy_order')])
                        s = min([o['price'] for o in relevant_orders_enriched if o['type_id'] == tid and not o.get('is_buy_order')])
                        spr = ((s-b)/b)*100
                    except: pass
                    self.diagnostics.enriched_parse_input_sample.append({
                        'id': tid, 'buy_count': data['buy'], 'sell_count': data['sell'], 
                        'spread': spr, 'has_history': (tid in history_dict)
                    })

            try:
                opps_enriched = parse_opportunities(relevant_orders_enriched, history_dict, names_dict, self.config)
            except Exception as e:
                logger.exception(f"[WORKER ERROR] Error in parse_opportunities: {e}")
                self.diagnostics.errors.append(f"Error in parse_opportunities: {str(e)}")
                opps_enriched = []

            if not opps_enriched and self.diagnostics.enriched_with_both_count > 0:
                msg = f"parse_opportunities returned 0 despite {self.diagnostics.enriched_with_both_count} items with buy/sell orders."
                logger.error(f"[WORKER ERROR] {msg}")
                self.diagnostics.errors.append(msg)

            for opp in opps_enriched:
                opp.is_enriched = True
                opp.score_breakdown = score_opportunity(opp, self.config)

            t_enrich = time.time() - t0
            self.diagnostics.parse_elapsed = t_enrich
            t_total_final = time.time() - t_start
            self.diagnostics.total_elapsed = t_total_final
            logger.info(f"[WORKER DIAG] opps_enriched={len(opps_enriched)} elapsed={t_enrich:.2f}s")

            if not opps_enriched and opps_initial:
                logger.warning(f"[WORKER DIAG] Enriched results EMPTY but initial had {len(opps_initial)}. Falling back to initial data.")
                opps_enriched = opps_initial
                for o in opps_enriched: 
                    o.is_enriched = False  # Keep as False to bypass history filters in UI
                self.diagnostics.fallback_used = True
                self.diagnostics.fallback_reason = "opps_enriched_empty_but_initial_available"
                self.diagnostics.fallback_kept_is_enriched_false = True

            self.last_results = opps_enriched
            self.diagnostics.final_emitted_count = len(opps_enriched)
            self.diagnostics.status = "Success"
            self.emit_progress(100, f"Done. {len(opps_enriched)} items.")
            self.enriched_data_ready.emit(opps_enriched)
            self.finished.emit(opps_enriched)
            self.data_ready.emit(opps_enriched)  # legacy compat
            
            self.diagnostics.finished_at = time.time()
            self.diagnostics_ready.emit(self.diagnostics)

        except Exception as e:
            import traceback
            err_msg = f"Worker Error: {str(e)}"
            logger.error(f"[WORKER ERROR] {e}\n{traceback.format_exc()}")
            self.diagnostics.errors.append(err_msg)
            self.diagnostics.errors.append(traceback.format_exc())
            self.diagnostics.status = f"Error: {str(e)}"
            self.emit_error(str(e))
            self.diagnostics.finished_at = time.time()
            self.diagnostics_ready.emit(self.diagnostics)

    def emit_progress(self, pct, text):
        self.progress.emit(pct)
        self.status.emit(text)
        self.progress_changed.emit(pct, text)

    def emit_error(self, msg):
        self.error.emit(msg)
        self.error_occurred.emit(msg)
