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

# VERSION: 1.1.0-STABILITY (Real functional implementation)

class ContractsScanWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    batch_ready = Signal(object)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, config: ContractsFilterConfig):
        super().__init__()
        self.config = config
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

            # 4. Escaneo Profundo
            name_map: dict = {}
            for i, contract in enumerate(candidates):
                # CONTROL DE CANCELACIÓN EN CADA ITERACIÓN
                if self._cancelled:
                    _log_info = "Escaneo detenido por el usuario."
                    break
                
                pct = 20 + int((i / len(candidates)) * 75)
                self.progress.emit(pct)
                self.status.emit(
                    f"Analizando contrato {i + 1}/{len(candidates)} — "
                    f"{len(all_results)} oportunidades"
                )
                
                # Check antes de red: Items
                if self._cancelled: break
                items_raw = client.contract_items(contract['contract_id'])
                
                # Check tras red
                if self._cancelled: break
                if not items_raw: continue
                
                # Resolución de Nombres (en bloques de 500 para ESI)
                new_ids = [r['type_id'] for r in items_raw if r.get('type_id') not in name_map]
                new_ids = list(set(new_ids))
                
                if new_ids:
                    for chunk_idx in range(0, len(new_ids), 500):
                        if self._cancelled: break
                        chunk = new_ids[chunk_idx:chunk_idx+500]
                        try:
                            # Check dentro del loop de resolución
                            names_res = client.universe_names(chunk)
                            if self._cancelled: break
                            for n in names_res:
                                name_map[n['id']] = n['name']
                        except Exception:
                            pass
                
                if self._cancelled: break
                
                # Cálculo de Métricas (CPU Bound)
                items = analyze_contract_items(items_raw, price_index, name_map, self.config)
                result = calculate_contract_metrics(contract, items, self.config)
                result.score = score_contract(result)
                self._scanned_count = i + 1
                
                # Emisión en tiempo real si es rentable
                if result.net_profit > self.config.profit_min_isk and result.roi_pct > self.config.roi_min_pct:
                    all_results.append(result)
                    self.batch_ready.emit(result)

            # 5. Finalización
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
