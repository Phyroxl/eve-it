from __future__ import annotations
from datetime import datetime, timezone
from typing import List

from PySide6.QtCore import QThread, Signal

from core.contracts_models import ContractArbitrageResult, ContractsFilterConfig
from core.contracts_engine import (
    build_price_index, analyze_contract_items,
    calculate_contract_metrics, score_contract, apply_contracts_filters
)
from core.esi_client import ESIClient
import logging

logger = logging.getLogger('eve.contracts_worker')

# VERSION: 1.1.0-STABILITY (Real functional implementation)

class ContractsScanWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    batch_ready = Signal(object)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, config: ContractsFilterConfig, force_refresh: bool = False):
        super().__init__()
        self.config = config
        self.force_refresh = force_refresh
        self._cancelled = False
        self._scanned_count = 0

    def cancel(self):
        """Activación de bandera de cancelación para detención inmediata."""
        self._cancelled = True

    def run(self):
        try:
            client = ESIClient()
            all_results: List[ContractArbitrageResult] = []

            # 1. Inicio
            if self._cancelled: return
            self.status.emit("Conectando con ESI (Public Contracts)...")
            self.progress.emit(5)
            contracts_raw = client.public_contracts(self.config.region_id)
            
            if self._cancelled: return
            if not contracts_raw:
                self.status.emit("No se encontraron contratos públicos.")
                self.finished.emit([])
                return

            # 2. Pre-filtro
            self.progress.emit(10)
            candidates = self._prefilter(contracts_raw)
            if self._cancelled: return
            
            if not candidates:
                self.status.emit("Sin candidatos válidos tras pre-filtro.")
                self.finished.emit([])
                return

            # 3. Precios
            self.progress.emit(15)
            self.status.emit("Obteniendo índices de precios Jita...")
            market_orders = client.market_orders(10000002) # Jita Hardcoded for valuation
            if self._cancelled: return
            
            price_index = build_price_index(market_orders)
            self.progress.emit(20)

            import time
            from concurrent.futures import ThreadPoolExecutor
            from core.contracts_cache import ContractsCache
            from core.item_resolver import ItemResolver
            from dataclasses import asdict

            start_time = time.time()
            cache = ContractsCache.instance()
            item_resolver = ItemResolver.instance()
            name_map: dict = {}
            contract_items_map: dict = {} # contract_id -> items_raw
            
            self.status.emit("Cargando detalles de items en paralelo...")
            
            from threading import Semaphore
            esi_semaphore = Semaphore(10) # Max 10 concurrent ESI calls

            def fetch_items_for_contract(c):
                if self._cancelled: return None
                cid = c['contract_id']
                
                # EARLY FILTERING (Cheap)
                # Si el contrato ya está en cache y sabemos que es un blueprint, 
                # y el usuario quiere excluirlos, lo descartamos ANTES de llamar a ESI.
                if not self.force_refresh and self.config.exclude_blueprints:
                    light = cache.get_light_entry(cid)
                    if light and light.get('has_blueprints'):
                        return None
                
                with esi_semaphore:
                    try:
                        items_raw = client.contract_items(cid)
                        return cid, items_raw
                    except Exception:
                        return cid, []

            # 4. Escaneo Profundo Paralelo
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(fetch_items_for_contract, candidates))
                for res in results:
                    if res:
                        cid, items = res
                        contract_items_map[cid] = items

            fetch_done_time = time.time()
            
            # 5. Deduplicación y Resolución Masiva
            self.status.emit("Resolviendo metadata y precios de mercado...")
            all_type_ids = set()
            for items in contract_items_map.values():
                for it in items:
                    all_type_ids.add(it['type_id'])
            
            all_type_ids = list(all_type_ids)
            
            # Metadata prefetch
            item_resolver.prefetch_type_metadata(all_type_ids)
            metadata_map = {tid: item_resolver.get_type_info(tid, blocking=False) for tid in all_type_ids}
            
            # Nombres prefetch
            new_ids = [tid for tid in all_type_ids if tid not in name_map]
            if new_ids:
                for chunk_idx in range(0, len(new_ids), 500):
                    if self._cancelled: break
                    chunk = new_ids[chunk_idx:chunk_idx+500]
                    try:
                        names_res = client.universe_names(chunk)
                        for n in names_res:
                            name_map[n['id']] = n['name']
                    except Exception: pass

            # Precios prefetch (Ya optimizado en ESIClient si pedimos por region)
            # build_price_index usa el cache regional si ya se bajó.
            
            resolve_done_time = time.time()
            
            # 6. Análisis Final
            self.status.emit("Calculando profit y aplicando filtros...")
            processed_count = 0
            cache_hits = 0
            for i, contract in enumerate(candidates):
                if self._cancelled: break
                
                cid = contract['contract_id']
                items_raw = contract_items_map.get(cid, [])
                if not items_raw: continue
                
                # Cache Check
                cached_analysis = None
                if not self.force_refresh:
                    cached_analysis = cache.get_entry(cid, items_raw, contract['price'])
                
                if cached_analysis:
                    result = ContractArbitrageResult.from_dict(cached_analysis)
                    cache_hits += 1
                else:
                    items = analyze_contract_items(items_raw, price_index, name_map, self.config, metadata_map)
                    result = calculate_contract_metrics(contract, items, self.config)
                    result.score = score_contract(result)
                    # Guardar en cache
                    cache.set_entry(cid, items_raw, contract['price'], asdict(result))
                
                processed_count += 1
                self._scanned_count = processed_count
                
                # Filtros
                filtered_single = apply_contracts_filters([result], self.config)
                if filtered_single:
                    all_results.append(result)
                    self.batch_ready.emit(result)
                
                if i % 10 == 0:
                    self.progress.emit(20 + int((i / len(candidates)) * 75))

            cache.save_cache()
            end_time = time.time()
            
            logger.info(
                f"[PERF] Scan complete: total_time={end_time-start_time:.2f}s | "
                f"fetch_items={fetch_done_time-start_time:.2f}s | "
                f"resolve={resolve_done_time-fetch_done_time:.2f}s | "
                f"cache_hits={cache_hits}/{processed_count}"
            )

            # 7. Finalización
            if self._cancelled:
                self.status.emit("ESCANEO CANCELADO")
                self.finished.emit(all_results)
                return

            self.progress.emit(95)
            self.status.emit("Ordenando por Score...")
            final = apply_contracts_filters(all_results, self.config)
            self.progress.emit(100)
            self.finished.emit(final)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

    def _prefilter(self, contracts_raw: list) -> list:
        """Filtro rápido inicial basado en capital y tiempo para no saturar ESI."""
        now = datetime.now(timezone.utc)
        result = []
        for c in contracts_raw:
            if self._cancelled: break
            
            # Solo intercambios de items
            if c.get('type') != 'item_exchange': continue
            
            price = c.get('price', 0.0)
            if price < self.config.capital_min_isk or price > self.config.capital_max_isk:
                continue
                
            try:
                exp = datetime.fromisoformat(c['date_expired'].replace('Z', '+00:00'))
                if (exp - now).total_seconds() < 3600: # Menos de 1h para expirar
                    continue
            except Exception:
                continue
                
            result.append(c)
            
        # Ordenar por los más recientes primero para mayor probabilidad de éxito
        result.sort(key=lambda x: x.get('date_issued', ''), reverse=True)
        return result[:self.config.max_contracts_to_scan]
