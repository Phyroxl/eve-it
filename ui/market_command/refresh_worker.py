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
from core.market_orders_cache import MarketOrdersCache
from core.market_scan_diagnostics import MarketScanDiagnostics
from core.market_candidate_selector import build_economic_candidates, prefilter_candidates, select_final_candidates

logger = logging.getLogger('eve.market.worker')

_TODOS_POOL_SIZE = 500      # Pool global para "Todos" (sin metadata, rápido)
_BROAD_POOL_SIZE = 10000    # Pool amplio para prefetch de metadata en categorías específicas
_CATEGORY_LIMIT_DEFAULT = 2000 # Límite por defecto para categorías
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
            from core.progress_tracker import ProgressTracker
            tracker = ProgressTracker(
                callback=self.emit_progress,
                task_name="MarketScan"
            )
            
            t_start = time.time()
            selected_category = getattr(self.config, 'selected_category', 'Todos')
            self.diagnostics.mode = "Advanced" if "Advanced" in str(self.__class__) else "Simple"
            # ──────────────────────────────────────────────────────────────────
            # FASE 1 — SNAPSHOT RÁPIDO
            # ──────────────────────────────────────────────────────────────────
            self.diagnostics.notes.append("Starting Phase 1 (Initial Data)")

            # Paso 1: Descargar market orders (ESIClient maneja el caché internamente)
            tracker.set_phase("Descargando órdenes de mercado...", 0, 15)
            t0 = time.time()
            orders = self.client.market_orders(self.region_id)
            if not orders:
                self.emit_error("No se pudieron obtener órdenes de mercado.")
                return

            if not self.is_running: return
            
            t_orders = time.time() - t0
            self.diagnostics.market_orders_elapsed = t_orders
            self.diagnostics.raw_orders_count = len(orders) if orders else 0
            
            # Retrieve detailed timings and source from ESIClient
            t_data = self.client.market_orders_timings.get(self.region_id, {})
            self.diagnostics.market_orders_source = t_data.get("source", "esi")
            self.diagnostics.market_orders_cache_hit = t_data.get("cache_hit", False)
            self.diagnostics.market_orders_cache_age_seconds = t_data.get("cache_age_seconds", 0)
            self.diagnostics.market_orders_first_page_elapsed = t_data.get("first_page_elapsed", 0)
            self.diagnostics.market_orders_remaining_pages_elapsed = t_data.get("remaining_pages_elapsed", 0)
            self.diagnostics.market_orders_elapsed = t_data.get("total_elapsed", t_orders)
            self.diagnostics.market_orders_pages_total = t_data.get("pages_total", 0)
            self.diagnostics.market_orders_pages_fetched = t_data.get("pages_fetched", 0)
            self.diagnostics.market_orders_pages_failed = t_data.get("pages_failed", 0)
            self.diagnostics.market_orders_workers = t_data.get("workers", 0)
            self.diagnostics.raw_orders_count = t_data.get("orders_count", len(orders))

            if not orders:
                self.diagnostics.status = "Failed: No orders"
                logger.error("[WORKER DIAG] raw_orders=0 - Failed to fetch market orders.")
                self.emit_error("Failed to fetch market orders.")
                self.diagnostics.finished_at = time.time()
                self.diagnostics_ready.emit(self.diagnostics)
                return
            
            logger.info(f"[WORKER DIAG] raw_orders={len(orders)} source={self.diagnostics.market_orders_source} elapsed={t_orders:.1f}s")

            # Paso 2: Agrupar por type_id
            tracker.set_phase("Agrupando por tipos...", 15, 20)
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

            # Paso 3: Construir pool de candidatos económicos
            tracker.set_phase("Identificando candidatos económicos...", 20, 25)
            t0 = time.time()
            all_cands = build_economic_candidates(temp_grouped, self.config)
            self.diagnostics.economic_candidates_count = len(all_cands)
            
            # Paso 4: Pre-filtro rápido (capital, spread, margin, plex)
            tracker.set_phase("Aplicando pre-filtro de rentabilidad...", 25, 30)
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

            # Paso 5: Selección de candidatos iniciales (Fase 1)
            tracker.set_phase("Seleccionando items iniciales...", 30, 35)
            t0 = time.time()
            if selected_category == "Todos":
                # Seleccionar top N type_ids
                pool_size = max(_TODOS_POOL_SIZE, self.config.max_item_types) if self.config.max_item_types > 0 else _TODOS_POOL_SIZE
                initial_candidates = select_final_candidates(final_pool_cands, pool_size)
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
                if not initial_candidates:
                    tracker.update(50, message=f"Preparando metadata para {selected_category}...")

            self.diagnostics.initial_candidates_count = len(initial_candidates)

            # Excluir PLEX
            plex_id = 44992
            if self.config.exclude_plex and plex_id in initial_candidates:
                initial_candidates.remove(plex_id)

            # Paso 5: Nombres en batch para candidatos iniciales
            tracker.set_phase("Resolviendo nombres iniciales...", 35, 45)
            t0 = time.time()
            names_dict = {}
            if initial_candidates:
                chunk_size = 500
                for i in range(0, len(initial_candidates), chunk_size):
                    chunk = initial_candidates[i:i + chunk_size]
                    names_data = self.client.universe_names(chunk)
                    if names_data:
                        for n in names_data:
                            names_dict[n['id']] = n['name']
                    tracker.update(i + len(chunk), total=len(initial_candidates))
            t_names = time.time() - t0
            self.diagnostics.names_elapsed = t_names

            # Paso 6: Crear oportunidades iniciales SIN historial
            tracker.set_phase("Generando resultados iniciales...", 45, 50)
            t0 = time.time()
            initial_set = set(initial_candidates)
            relevant_orders_initial = [o for o in orders if o['type_id'] in initial_set]
            self.diagnostics.relevant_orders_initial_count = len(relevant_orders_initial)
            
            opps_initial = parse_opportunities(relevant_orders_initial, {}, names_dict, self.config)
            for opp in opps_initial:
                opp.is_enriched = False
                opp.score_breakdown = score_opportunity(opp, self.config)

            self.diagnostics.opps_initial_count = len(opps_initial)

            # Emitir resultados iniciales a la UI
            self.initial_data_ready.emit(opps_initial)

            if not self.is_running: return

            # ──────────────────────────────────────────────────────────────────
            # FASE 2 — ENRIQUECIMIENTO AUTOMÁTICO (historial + metadata completa)
            # ──────────────────────────────────────────────────────────────────

            # Paso 7: Determinar candidatos finales con metadata completa
            tracker.set_phase("Enriqueciendo metadatos...", 50, 65)
            t0 = time.time()
            if selected_category == "Todos":
                pool_size = max(_TODOS_POOL_SIZE, self.config.max_item_types) if self.config.max_item_types > 0 else _TODOS_POOL_SIZE
                final_candidates = select_final_candidates(final_pool_cands, pool_size)
            else:
                # Prefetch metadata paralelo para pool amplio
                broad_ids = [c.type_id for c in final_pool_cands[:_BROAD_POOL_SIZE]]
                tracker.update(10, message=f"Descargando metadatos ({len(broad_ids)} items)...")
                p_stats = ItemResolver.instance().prefetch_type_metadata_parallel(broad_ids, n_clients=4)
                if not self.is_running: return
                
                self.diagnostics.metadata_total = p_stats['total']
                self.diagnostics.metadata_cached = p_stats['cached']
                self.diagnostics.metadata_fetched = p_stats['fetched']
                self.diagnostics.metadata_failed = p_stats['failed']
                
                tracker.update(80, message=f"Filtrando por categoría '{selected_category}'...")
                category_ids = []
                for c in final_pool_cands[:_BROAD_POOL_SIZE]:
                    t_id = c.type_id
                    cat_id, grp_id, _, _ = ItemResolver.instance().resolve_category_info(t_id, blocking=False)
                    match, _ = is_type_in_category(selected_category, cat_id, grp_id, broad=True)
                    if match:
                        category_ids.append(t_id)

                cat_limit = max(_CATEGORY_LIMIT_DEFAULT, self.config.max_item_types) if self.config.max_item_types > 0 else _CATEGORY_LIMIT_DEFAULT
                final_candidates = category_ids[:cat_limit]

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

            if self.config.exclude_plex and plex_id in final_candidates:
                final_candidates.remove(plex_id)

            # Paso 8: History cache hits
            tracker.set_phase("Comprobando caché de historial...", 65, 70)
            t0 = time.time()
            hist_cache = MarketHistoryCache.instance()
            history_hits = hist_cache.get_many(self.region_id, final_candidates)
            missing_hist = [t for t in final_candidates if t not in history_hits]
            self.diagnostics.history_cache_hits = len(history_hits)
            self.diagnostics.history_cache_misses = len(missing_hist)

            # Paso 9: Descarga concurrente de historial faltante
            tracker.set_phase("Descargando historial de mercado...", 70, 85, total=len(missing_hist))
            fetched_history = {}
            failed_hist = 0
            if missing_hist:
                _workers = min(_HISTORY_WORKERS, len(missing_hist))
                hist_pool = [ESIClient() for _ in range(_workers)]

                def fetch_hist(args):
                    idx, type_id = args
                    client = hist_pool[idx % _workers]
                    try:
                        hist = client.market_history(self.region_id, type_id)
                        return type_id, hist
                    except Exception:
                        return type_id, None

                with ThreadPoolExecutor(max_workers=_workers) as executor:
                    futures_map = {executor.submit(fetch_hist, (i, t)): t
                                   for i, t in enumerate(missing_hist)}
                    done = 0
                    for future in as_completed(futures_map):
                        if not self.is_running: break
                        try:
                            type_id, hist = future.result()
                            if hist: fetched_history[type_id] = hist
                            else: failed_hist += 1
                        except Exception: failed_hist += 1
                        done += 1
                        tracker.update(done, message=f"Historial: {done}/{len(missing_hist)}")

            t_history = time.time() - t0
            self.diagnostics.history_fetched = len(fetched_history)
            self.diagnostics.history_failed = failed_hist
            self.diagnostics.history_elapsed = t_history

            # Actualizar cache de historial en disco
            for t_id, hist in fetched_history.items():
                hist_cache.set(self.region_id, t_id, hist)
            if fetched_history:
                hist_cache.save()

            # Merge historial completo
            history_dict = {**history_hits, **fetched_history}
            self.diagnostics.history_dict_count = len(history_dict)

            # Paso 10: Nombres para nuevos candidatos (Fase 2 puede tener más que Fase 1)
            tracker.set_phase("Resolviendo nombres finales...", 85, 90)
            t0 = time.time()
            new_ids = [t for t in final_candidates if t not in names_dict]
            if new_ids:
                for i in range(0, len(new_ids), 500):
                    chunk = new_ids[i:i + 500]
                    names_data = self.client.universe_names(chunk)
                    if names_data:
                        for n in names_data:
                            names_dict[n['id']] = n['name']
                    tracker.update(i + len(chunk), total=len(new_ids))

            if not self.is_running: return

            # Paso 11: Parsear oportunidades enriquecidas
            tracker.set_phase("Finalizando análisis de mercado...", 90, 100)
            t0 = time.time()
            final_set = set(final_candidates)
            relevant_orders_enriched = [o for o in orders if o['type_id'] in final_set]
            self.diagnostics.relevant_orders_enriched_count = len(relevant_orders_enriched)
            
            # Diagnóstico de entrada a parse
            self.diagnostics.enriched_with_both_count = 0
            self.diagnostics.enriched_with_buy_count = 0
            self.diagnostics.enriched_with_sell_count = 0
            
            temp_parse_map = {}
            for o in relevant_orders_enriched:
                tid = o['type_id']
                if tid not in temp_parse_map: temp_parse_map[tid] = {'buy': 0, 'sell': 0}
                if o.get('is_buy_order'): temp_parse_map[tid]['buy'] += 1
                else: temp_parse_map[tid]['sell'] += 1

            for tid, data in temp_parse_map.items():
                if data['buy'] > 0 and data['sell'] > 0: self.diagnostics.enriched_with_both_count += 1
                elif data['buy'] > 0: self.diagnostics.enriched_with_buy_count += 1
                elif data['sell'] > 0: self.diagnostics.enriched_with_sell_count += 1

            try:
                opps_enriched = parse_opportunities(relevant_orders_enriched, history_dict, names_dict, self.config)
                self.diagnostics.opps_enriched_count = len(opps_enriched)
            except Exception as e:
                logger.exception(f"[WORKER ERROR] Error in parse_opportunities: {e}")
                self.diagnostics.errors.append(f"Error in parse_opportunities: {str(e)}")
                opps_enriched = []

            for opp in opps_enriched:
                opp.is_enriched = True
                opp.score_breakdown = score_opportunity(opp, self.config)

            t_enrich = time.time() - t0
            self.diagnostics.parse_elapsed = t_enrich
            t_total_final = time.time() - t_start
            self.diagnostics.total_elapsed = t_total_final

            if not opps_enriched and opps_initial:
                opps_enriched = opps_initial
                for o in opps_enriched: o.is_enriched = False
                self.diagnostics.fallback_used = True

            self.last_results = opps_enriched
            self.diagnostics.final_emitted_count = len(opps_enriched)
            self.diagnostics.status = "Success"
            tracker.finish(f"Escaneo completo: {len(opps_enriched)} items.")
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
