from __future__ import annotations
from datetime import datetime, timezone
from typing import List
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
from dataclasses import asdict

from PySide6.QtCore import QThread, Signal

from core.contracts_models import ContractArbitrageResult, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import (
    build_price_index, analyze_contract_items,
    calculate_contract_metrics, score_contract, apply_contracts_filters
)
from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.contracts_cache import ContractsCache
from core.item_resolver import ItemResolver
from core.progress_tracker import ProgressTracker

logger = logging.getLogger('eve.contracts_worker')

# VERSION: 1.3.0-STABILITY (Added as_completed and partial diagnostic updates)

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
        self.current_location_id = None
        self.diag = ScanDiagnostics()

    def cancel(self):
        """Activación de bandera de cancelación para detención inmediata."""
        self._cancelled = True
        logger.info("[CONTRACTS] Cancel requested by user.")

    def run(self):
        try:
            tracker = ProgressTracker(
                callback=lambda p, m: (self.progress.emit(p), self.status.emit(m)),
                task_name="ContractsScan"
            )
            
            client = ESIClient()
            all_results: List[ContractArbitrageResult] = []
            
            # 1. Fetch Location & Availability Setup
            tracker.set_phase("Sincronizando ubicación...", 0, 5)
            self.current_location_id = None
            auth = AuthManager.instance()
            char_id = auth.char_id
            token = auth.get_token()

            if self.config.only_current_station and char_id and token:
                loc_data = client.character_location(char_id, token)
                if loc_data:
                    self.current_location_id = loc_data.get('station_id') or loc_data.get('structure_id')
                    logger.info(f"[CONTRACTS] Character current location: {self.current_location_id}")

            if self._cancelled: return
            
            contracts_raw = []
            
            # 2. Fetch Contracts
            tracker.set_phase("Descargando contratos...", 5, 20)
            
            # PUBLIC FETCH
            if self.config.availability_filter in ("public", "both"):
                tracker.update(0, message="Conectando con ESI (Public)...")
                public_raw = client.public_contracts(self.config.region_id, diagnostics=self.diag, force_refresh=self.force_refresh)
                if public_raw:
                    contracts_raw.extend(public_raw)

            if self._cancelled: return

            # ALLIANCE / PERSONAL FETCH
            if self.config.availability_filter in ("alliance", "both") and char_id and token:
                tracker.update(50, message="Descargando Alianza/Personales...")
                personal_raw = client.character_contracts(char_id, token)
                if personal_raw:
                    valid_personal = [c for c in personal_raw if c.get('type') == 'item_exchange' and c.get('status') == 'outstanding']
                    existing_ids = {c.get('contract_id') for c in contracts_raw}
                    for c in valid_personal:
                        if c.get('contract_id') not in existing_ids:
                            contracts_raw.append(c)
            
            if self._cancelled: return
            if not contracts_raw:
                tracker.finish("No se encontraron contratos.")
                self.finished.emit([])
                return

            # 3. Pre-filtro
            tracker.set_phase("Aplicando pre-filtro...", 20, 25)
            candidates = self._prefilter(contracts_raw)
            if self._cancelled: return
            
            if not candidates:
                tracker.finish("Sin candidatos válidos.")
                self.finished.emit([])
                return

            # 4. Precios
            tracker.set_phase("Obteniendo precios de referencia...", 25, 30)
            market_orders = client.market_orders(10000002) # Jita Hardcoded for valuation
            if self._cancelled: return
            
            price_index = build_price_index(market_orders)

            cache = ContractsCache.instance()
            item_resolver = ItemResolver.instance()
            name_map: dict = {}
            contract_items_map: dict = {} # contract_id -> items_raw
            
            # 5. Escaneo Profundo Paralelo
            tracker.set_phase("Descargando detalles de items...", 30, 60, total=len(candidates))
            
            esi_semaphore = Semaphore(10) # Max 10 concurrent ESI calls

            def fetch_items_for_contract(c):
                if self._cancelled: return None
                cid = c['contract_id']
                
                # EARLY FILTERING (Cheap)
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

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_items_for_contract, c): c for c in candidates}
                done = 0
                for future in as_completed(futures):
                    if self._cancelled: break
                    res = future.result()
                    if res:
                        cid, items = res
                        contract_items_map[cid] = items
                    done += 1
                    if done % 5 == 0 or done == len(candidates):
                        tracker.update(done, message=f"Descargando items {done}/{len(candidates)}")

            if self._cancelled: 
                tracker.finish("Cancelado")
                self.finished.emit(all_results)
                return
            
            # 6. Resolución Masiva
            tracker.set_phase("Resolviendo nombres y metadatos...", 60, 70)
            all_type_ids = set()
            for items in contract_items_map.values():
                for it in items:
                    all_type_ids.add(it['type_id'])
            
            all_type_ids = list(all_type_ids)
            if all_type_ids:
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
                        tracker.update(chunk_idx + len(chunk), total=len(new_ids), message=f"Resolviendo {len(new_ids)} nombres...")
            else:
                metadata_map = {}

            if self._cancelled:
                tracker.finish("Cancelado")
                self.finished.emit(all_results)
                return

            # 7. Análisis Final
            tracker.set_phase("Calculando profit y ROI...", 70, 95, total=len(candidates))
            self.diag.total_scanned = len(candidates)
            processed_count = 0
            cache_hits = 0
            
            for i, contract in enumerate(candidates):
                if self._cancelled: break
                
                cid = contract['contract_id']
                items_raw = contract_items_map.get(cid, [])
                
                # Cache Check
                cached_analysis = None
                if not self.force_refresh:
                    cached_analysis = cache.get_entry(cid, items_raw, contract['price'])
                
                if cached_analysis:
                    result = ContractArbitrageResult.from_dict(cached_analysis)
                    if len(result.items) == 0 and result.item_type_count > 0:
                        cached_analysis = None
                    else:
                        cache_hits += 1
                
                if not cached_analysis:
                    if items_raw:
                        items = analyze_contract_items(items_raw, price_index, name_map, self.config, metadata_map)
                        result = calculate_contract_metrics(contract, items, self.config)
                        result.score = score_contract(result)
                        cache.set_entry(cid, items_raw, contract['price'], asdict(result))
                    else:
                        continue
                
                processed_count += 1
                self._scanned_count = processed_count
                all_results.append(result)
                
                filtered_single = apply_contracts_filters([result], self.config, self.diag, current_location_id=self.current_location_id)
                if filtered_single:
                    self.batch_ready.emit(result)
                
                if i % 10 == 0 or i == len(candidates) - 1:
                    tracker.update(i + 1, message=f"Analizando contrato {i+1}/{len(candidates)}")

            cache.save_cache()
            self.diag.contract_cache_hits = cache_hits
            self.diag.contract_cache_misses = processed_count - cache_hits

            # 8. Finalización
            if self._cancelled:
                tracker.finish("ESCANEO CANCELADO")
                self.finished.emit(all_results)
                return

            tracker.finish("Escaneo completo")
            self.finished.emit(all_results)

        except Exception as e:
            logger.error(f"[CONTRACTS ERR] {e}", exc_info=True)
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
        
        # Aplicar límite si max_contracts_to_scan > 0
        limit = self.config.max_contracts_to_scan
        if limit > 0 and len(result) > limit:
            if self.diag:
                self.diag.esi_limit_hit = True
            return result[:limit]
            
        return result
