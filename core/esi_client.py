import json
import logging
import time
import requests
from threading import Lock
from .market_orders_cache import MarketOrdersCache

logger = logging.getLogger('eve.esi')

class ESICache:
    def __init__(self):
        self.cache = {}
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() < entry['expiry']:
                    return entry['data']
                else:
                    del self.cache[key]
            return None

    def set(self, key, data, ttl_seconds):
        with self.lock:
            self.cache[key] = {
                'data': data,
                'expiry': time.time() + ttl_seconds
            }

class ESIClient:
    BASE_URL = "https://esi.evetech.net/latest"
    # Shared ceiling across all instances — prevents burst 429s when using parallel workers.
    # 0.03s = ~33 req/s global max; per-instance limit remains 10 req/s via rate_limit_lock.
    GLOBAL_MIN_REQUEST_INTERVAL = 0.03
    _global_rate_lock = Lock()
    _global_last_request_time = 0.0

    def __init__(self):
        self.cache = ESICache()
        self.session = requests.Session()
        self.last_request_time = 0
        self.rate_limit_lock = Lock()
        self.rate_limit_hits = 0
        self.market_orders_timings = {} # region_id -> timing_data

    def _rate_limit(self):
        with self.rate_limit_lock:
            now = time.time()
            elapsed = now - self.last_request_time
            # 0.02s = 50 req/s per instance; enough for concurrency without hitting 429 too hard
            if elapsed < 0.02:  
                time.sleep(0.02 - elapsed)
            self.last_request_time = time.time()
        with ESIClient._global_rate_lock:
            now = time.time()
            elapsed = now - ESIClient._global_last_request_time
            if elapsed < ESIClient.GLOBAL_MIN_REQUEST_INTERVAL:
                time.sleep(ESIClient.GLOBAL_MIN_REQUEST_INTERVAL - elapsed)
            ESIClient._global_last_request_time = time.time()

    def _get(self, endpoint, ttl=0, params=None):
        cache_key = f"{endpoint}_{json.dumps(params, sort_keys=True) if params else ''}"
        if ttl > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        retries = 3
        while retries > 0:
            self._rate_limit()
            try:
                response = self.session.get(f"{self.BASE_URL}{endpoint}", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if ttl > 0:
                        self.cache.set(cache_key, data, ttl)
                    return data
                elif response.status_code == 429:
                    retry_after = float(response.headers.get('Retry-After', 5))
                    self.rate_limit_hits += 1
                    logger.warning(
                        f"[ESI RATE LIMIT] endpoint={endpoint} "
                        f"retry_after={retry_after}s hits={self.rate_limit_hits}"
                    )
                    time.sleep(retry_after)
                    retries -= 1
                    continue
                elif response.status_code >= 500:
                    retries -= 1
                    time.sleep(1)
                    continue
                else:
                    return None
            except requests.RequestException as e:
                logger.warning(f"ESI request error en {endpoint}: {e}")
                retries -= 1
                time.sleep(1)
        return None

    MARKET_ORDERS_WORKERS = 8

    def _fetch_market_page(self, region_id, page, retries=3):
        """Helper para descargar una página individual con reintentos."""
        while retries > 0:
            self._rate_limit()
            try:
                params = {'page': page, 'order_type': 'all'}
                response = self.session.get(f"{self.BASE_URL}/markets/{region_id}/orders/", params=params, timeout=15)
                if response.status_code == 200:
                    return response.json(), int(response.headers.get('X-Pages', 1))
                elif response.status_code == 429:
                    retry_after = float(response.headers.get('Retry-After', 5))
                    self.rate_limit_hits += 1
                    logger.warning(f"[ESI RATE LIMIT] page={page} retry_after={retry_after}s hits={self.rate_limit_hits}")
                    time.sleep(retry_after)
                    retries -= 1
                    continue
                elif response.status_code >= 500:
                    time.sleep(1)
                    retries -= 1
                    continue
                else:
                    return None, None
            except Exception as e:
                logger.warning(f"ESI market_orders error page {page}: {e}")
                time.sleep(1)
                retries -= 1
        return None, None

    def market_orders(self, region_id: int):
        """
        Descarga todas las órdenes de mercado de una región usando paginación concurrente.
        Utiliza MarketOrdersCache para evitar descargas redundantes.
        """
        t_start = time.time()
        cache = MarketOrdersCache.instance()
        cached = cache.get(region_id)
        
        if cached is not None:
            elapsed = time.time() - t_start
            self.market_orders_timings[region_id] = {
                "source": "memory_cache",
                "cache_hit": True,
                "cache_age_seconds": cache.get_age(region_id),
                "first_page_elapsed": 0,
                "remaining_pages_elapsed": 0,
                "total_elapsed": elapsed,
                "pages_total": 0,
                "pages_fetched": 0,
                "pages_failed": 0,
                "workers": 0,
                "orders_count": len(cached)
            }
            return cached

        # 1. Obtener primera página para conocer el total
        t_p1_start = time.time()
        first_page_data, total_pages = self._fetch_market_page(region_id, 1)
        t_first = time.time() - t_p1_start
        
        if first_page_data is None:
            return []
        
        all_orders = list(first_page_data)
        if total_pages <= 1:
            cache.set(region_id, all_orders)
            self.market_orders_timings[region_id] = {
                "source": "esi",
                "cache_hit": False,
                "cache_age_seconds": 0,
                "first_page_elapsed": t_first,
                "remaining_pages_elapsed": 0,
                "total_elapsed": time.time() - t_start,
                "pages_total": total_pages,
                "pages_fetched": 1,
                "pages_failed": 0,
                "workers": 1,
                "orders_count": len(all_orders)
            }
            return all_orders

        # 2. Descarga concurrente de páginas restantes
        from concurrent.futures import ThreadPoolExecutor, as_completed
        pages_to_fetch = range(2, total_pages + 1)
        pages_failed = 0
        
        logger.info(f"[MARKET ORDERS] Region {region_id}: Downloading {total_pages} pages using {self.MARKET_ORDERS_WORKERS} workers...")
        
        t_batch_start = time.time()
        with ThreadPoolExecutor(max_workers=self.MARKET_ORDERS_WORKERS) as executor:
            future_to_page = {executor.submit(self._fetch_market_page, region_id, p): p for p in pages_to_fetch}
            for future in as_completed(future_to_page):
                p = future_to_page[future]
                try:
                    data, _ = future.result()
                    if data:
                        all_orders.extend(data)
                    else:
                        pages_failed += 1
                        logger.error(f"[MARKET ORDERS] Page {p} failed after retries.")
                except Exception as e:
                    pages_failed += 1
                    logger.error(f"[MARKET ORDERS] Page {p} exception: {e}")
        
        t_batch = time.time() - t_batch_start
        total_elapsed = time.time() - t_start
        
        # Store timings for diagnostics
        self.market_orders_timings[region_id] = {
            "source": "esi",
            "cache_hit": False,
            "cache_age_seconds": 0,
            "first_page_elapsed": t_first,
            "remaining_pages_elapsed": t_batch,
            "total_elapsed": total_elapsed,
            "pages_total": total_pages,
            "pages_fetched": total_pages - pages_failed,
            "pages_failed": pages_failed,
            "workers": self.MARKET_ORDERS_WORKERS,
            "orders_count": len(all_orders)
        }

        logger.info(f"[MARKET ORDERS] Finished in {total_elapsed:.2f}s. Pages: {total_pages}, Orders: {len(all_orders)}, Failed: {pages_failed}")
        
        if all_orders and pages_failed == 0:
            cache.set(region_id, all_orders)
        return all_orders

    def market_history(self, region_id: int, type_id: int):
        # Cache 6h = 21600 seconds
        return self._get(f"/markets/{region_id}/history/", ttl=21600, params={'type_id': type_id})

    def universe_names(self, ids: list[int]):
        """Fetch names for given IDs. Needed to map type_id to item_name."""
        cache_key = f"universe_names_{hash(tuple(sorted(ids)))}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        # Bulk post endpoint for names
        self._rate_limit()
        try:
            response = self.session.post(f"{self.BASE_URL}/universe/names/", json=ids, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Cache for 24h
                self.cache.set(cache_key, data, 86400)
                return data
        except Exception as e:
            logger.warning(f"ESI universe_names error: {e}")
        return []

    def _headers(self, token=None):
        if token is None:
            from .auth_manager import AuthManager
            token = AuthManager.instance().get_valid_access_token()
        return {"Authorization": f"Bearer {token}", "User-Agent": "EVE-iT-Market-Command"}

    def _request_auth(self, method, endpoint, token, params=None, json_data=None, retries=1):
        """Petición autenticada con reintento automático en caso de 401."""
        url = f"{self.BASE_URL}{endpoint}" if endpoint.startswith("/") else endpoint
        try:
            self._rate_limit()
            res = self.session.request(method, url, headers=self._headers(token), params=params, json=json_data, timeout=15)
            if res.status_code == 401 and retries > 0:
                logger.info(f"ESI: 401 en {endpoint}, forzando refresh...")
                from .auth_manager import AuthManager
                new_token = AuthManager.instance().get_valid_access_token()
                if new_token:
                    return self._request_auth(method, endpoint, new_token, params, json_data, retries - 1)
            return res
        except Exception as e:
            logger.error(f"ESI request_auth error en {endpoint}: {e}")
            return None

    def character_wallet(self, char_id, token):
        res = self._request_auth("GET", f"/characters/{char_id}/wallet/", token)
        if res and res.status_code == 200:
            return res.json()
        logger.warning(f"ESI character_wallet char={char_id} → Falló")
        return None

    def wallet_journal(self, char_id, token):
        all_data = []
        page = 1
        while True:
            res = self._request_auth("GET", f"/characters/{char_id}/wallet/journal/", token, params={'page': page})
            if res and res.status_code == 200:
                data = res.json()
                if not data: break
                all_data.extend(data)
                pages = int(res.headers.get('X-Pages', 1))
                if page >= pages: break
                page += 1
            else:
                if res and res.status_code in (401, 403): return "missing_scope"
                break
        return all_data

    def wallet_transactions(self, char_id, token):
        """Obtiene las últimas 2500 transacciones de la wallet. No usa 'page'."""
        res = self._request_auth("GET", f"/characters/{char_id}/wallet/transactions/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            return "missing_scope"
        return []

    def character_orders(self, char_id, token):
        res = self._request_auth("GET", f"/characters/{char_id}/orders/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            raise Exception("Token expirado o sin permisos (Reautorizar).")
        return []

    def character_assets(self, char_id, token):
        all_assets = []
        page = 1
        while True:
            res = self._request_auth("GET", f"/characters/{char_id}/assets/", token, params={'page': page})
            if res and res.status_code == 200:
                data = res.json()
                if not data: break
                all_assets.extend(data)
                pages = int(res.headers.get('X-Pages', 1))
                if page >= pages: break
                page += 1
            else:
                if res and res.status_code in (401, 403): return "missing_scope"
                break
        return all_assets

    def character_skills(self, char_id, token):
        res = self._request_auth("GET", f"/characters/{char_id}/skills/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            return "missing_scope"
        return None

    def open_market_window(self, type_id: int, access_token: str):
        """
        Abre la ventana de mercado regional en el cliente de EVE Online.
        Requiere scope: esi-ui.open_window.v1
        """
        endpoint = f"/ui/openwindow/marketdetails/"
        params = {'type_id': type_id}
        headers = {'Authorization': f'Bearer {access_token}'}
        
        self._rate_limit()
        try:
            # ESI UI endpoints are POST
            response = self.session.post(f"{self.BASE_URL}{endpoint}", params=params, headers=headers, timeout=10)
            return response.status_code == 204 # 204 No Content is success for this endpoint
        except Exception as e:
            logger.error(f"Error opening market window (type_id={type_id}): {e}")
            return False

    def open_contract_window(self, contract_id: int, access_token: str):
        """
        Abre el contrato en el cliente de EVE Online.
        Requiere scope: esi-ui.open_window.v1
        """
        endpoint = f"/ui/openwindow/contract/"
        params = {'contract_id': contract_id}
        headers = {'Authorization': f'Bearer {access_token}'}
        
        self._rate_limit()
        try:
            response = self.session.post(f"{self.BASE_URL}{endpoint}", params=params, headers=headers, timeout=10)
            if response.status_code == 403:
                return "missing_scope"
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Error opening contract window (contract_id={contract_id}): {e}")
            return False

    def public_contracts(self, region_id: int) -> list:
        """
        GET /contracts/public/{region_id}/?page=1
        Obtiene primera página (hasta 1000 contratos).
        Filtra en local: solo type='item_exchange' y status='outstanding'.
        Cache TTL: 300s
        """
        cache_key = f"public_contracts_{region_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        self._rate_limit()
        url = f"{self.BASE_URL}/contracts/public/{region_id}/?datasource=tranquility&page=1"
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                all_contracts = response.json()
                filtered = [
                    c for c in all_contracts
                    if c.get('type') == 'item_exchange'
                    and c.get('status', 'outstanding') == 'outstanding'
                ]
                self.cache.set(cache_key, filtered, 300)
                return filtered
            return []
        except Exception:
            return []

    def contract_items(self, contract_id: int) -> list:
        """
        GET /contracts/public/items/{contract_id}/
        Cache TTL: 3600s
        Retorna [] en 403/404 (contrato ya expirado o privado).
        """
        cache_key = f"contract_items_{contract_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        self._rate_limit()
        url = f"{self.BASE_URL}/contracts/public/items/{contract_id}/?datasource=tranquility"
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                items = response.json()
                self.cache.set(cache_key, items, 3600)
                return items
            elif response.status_code in (403, 404):
                self.cache.set(cache_key, [], 3600)
                return []
            elif response.status_code == 429:
                import time
                retry_after = float(response.headers.get('Retry-After', 5))
                time.sleep(retry_after)
                return self.contract_items(contract_id)
            return []
        except Exception:
            return []

    def character_standings(self, char_id: int, token: str):
        res = self._request_auth("GET", f"/characters/{char_id}/standings/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            return "missing_scope"
        return None

    def universe_stations(self, station_id: int):
        return self._get(f"/universe/stations/{station_id}/", ttl=86400)

    def universe_structures(self, structure_id: int, token: str):
        res = self._request_auth("GET", f"/universe/structures/{structure_id}/", token)
        if res and res.status_code == 200:
            return res.json()
        return None

    def corporation_info(self, corp_id: int):
        return self._get(f"/corporations/{corp_id}/", ttl=86400)

    def character_location(self, char_id: int, token: str):
        res = self._request_auth("GET", f"/characters/{char_id}/location/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            return "missing_scope"
        return None

    def universe_type(self, type_id: int):
        """Obtiene información del tipo (incluye group_id). Cache 24h."""
        return self._get(f"/universe/types/{type_id}/", ttl=86400)
