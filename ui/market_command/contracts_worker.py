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


class ContractsScanWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    batch_ready = Signal(object)   # emite un ContractArbitrageResult en tiempo real
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, config: ContractsFilterConfig):
        super().__init__()
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            client = ESIClient()
            all_results: List[ContractArbitrageResult] = []

            self.status.emit("Obteniendo contratos públicos...")
            self.progress.emit(5)
            contracts_raw = client.public_contracts(self.config.region_id)
            if not contracts_raw:
                self.status.emit("No se obtuvieron contratos.")
                self.finished.emit([])
                return

            self.progress.emit(10)
            candidates = self._prefilter(contracts_raw)
            self.status.emit(f"{len(contracts_raw)} contratos — {len(candidates)} candidatos.")
            if not candidates:
                self.finished.emit([])
                return

            self.progress.emit(15)
            self.status.emit("Cargando precios de mercado Jita...")
            market_orders = client.market_orders(self.config.region_id)
            price_index = build_price_index(market_orders)
            self.progress.emit(20)

            name_map: dict = {}
            for i, contract in enumerate(candidates):
                if self._cancelled:
                    break
                pct = 20 + int((i / len(candidates)) * 75)
                self.progress.emit(pct)
                self.status.emit(
                    f"Analizando contrato {i + 1}/{len(candidates)} — "
                    f"{len(all_results)} oportunidades encontradas"
                )
                items_raw = client.contract_items(contract['contract_id'])
                if not items_raw:
                    continue
                new_ids = [r['type_id'] for r in items_raw if r.get('type_id') not in name_map]
                if new_ids:
                    try:
                        for n in client.universe_names(new_ids[:500]):
                            name_map[n['id']] = n['name']
                    except Exception:
                        pass
                items = analyze_contract_items(items_raw, price_index, name_map, self.config)
                result = calculate_contract_metrics(contract, items, self.config)
                result.score = score_contract(result)
                if result.net_profit > 0:
                    all_results.append(result)
                    self.batch_ready.emit(result)

            self.progress.emit(95)
            self.status.emit("Ordenando resultados...")
            final = apply_contracts_filters(all_results, self.config)
            self.progress.emit(100)
            self.finished.emit(final)

        except Exception as e:
            self.error.emit(str(e))

    def _prefilter(self, contracts_raw: list) -> list:
        now = datetime.now(timezone.utc)
        result = []
        for c in contracts_raw:
            price = c.get('price', 0.0)
            if price < self.config.capital_min_isk or price > self.config.capital_max_isk:
                continue
            try:
                exp = datetime.fromisoformat(c['date_expired'].replace('Z', '+00:00'))
                if (exp - now).total_seconds() < 3600:
                    continue
            except Exception:
                continue
            result.append(c)
        result.sort(key=lambda x: x.get('price', 0.0), reverse=True)
        return result[:self.config.max_contracts_to_scan]
