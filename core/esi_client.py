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
    _shared_cache = ESICache()
    # Shared ceiling across all instances — prevents burst 429s when using parallel workers.
    # 0.03s = ~33 req/s global max; per-instance limit remains 10 req/s via rate_limit_lock.
    GLOBAL_MIN_REQUEST_INTERVAL = 0.03
    _global_rate_lock = Lock()
    _global_last_request_time = 0.0
    _market_orders_timings = {} # region_id -> timing_data (Shared across instances)

    def __init__(self):
        self.cache = ESIClient._shared_cache
        self.session = requests.Session()
        self.last_request_time = 0
        self.rate_limit_lock = Lock()
        self.rate_limit_hits = 0

    @property
    def market_orders_timings(self):
        return ESIClient._market_orders_timings

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

    def market_orders(self, region_id: int, force_refresh: bool = False):
        """
        Descarga todas las órdenes de mercado de una región usando paginación concurrente.
        Utiliza MarketOrdersCache para evitar descargas redundantes.
        """
        t_start = time.time()
        cache = MarketOrdersCache.instance()
        
        if force_refresh:
            cache.invalidate(region_id)
            
        cached = cache.get(region_id)
        
        if cached is not None:
            elapsed = time.time() - t_start
            self.market_orders_timings[region_id] = {
                "source": "memory_cache",
                "cache_hit": True,
                "force_refresh": force_refresh,
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
        source_name = "esi_forced_refresh" if force_refresh else "esi"
        
        if total_pages <= 1:
            cache.set(region_id, all_orders)
            self.market_orders_timings[region_id] = {
                "source": source_name,
                "cache_hit": False,
                "force_refresh": force_refresh,
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
            "source": source_name,
            "cache_hit": False,
            "force_refresh": force_refresh,
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

    def market_orders_for_types(self, region_id: int, type_ids: list[int], max_workers: int = 6) -> list:
        """
        Fetch fresh market orders only for the requested type_ids using get_market_orders_for_type().
        No MarketOrdersCache regional involvement.
        Suitable for My Orders refresh where we only need the character's active order type_ids.
        """
        t_start = time.time()
        dedup_type_ids = sorted(list(set(type_ids)))
        all_orders = []
        type_ids_fetched = 0
        type_ids_failed = 0
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info(f"[MARKET ORDERS FILTERED] Region {region_id}: Fetching {len(dedup_type_ids)} types using {max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_tid = {executor.submit(self.get_market_orders_for_type, region_id, tid): tid for tid in dedup_type_ids}
            for future in as_completed(future_to_tid):
                tid = future_to_tid[future]
                try:
                    data = future.result()
                    if data is not None:
                        all_orders.extend(data)
                        type_ids_fetched += 1
                    else:
                        type_ids_failed += 1
                except Exception as e:
                    type_ids_failed += 1
                    logger.error(f"[MARKET ORDERS FILTERED] Type {tid} exception: {e}")
        
        total_elapsed = time.time() - t_start
        
        # Store timings for diagnostics
        self.market_orders_timings[region_id] = {
            "source": "esi_type_filtered_refresh",
            "cache_hit": False,
            "force_refresh": True,
            "type_ids_count": len(dedup_type_ids),
            "type_ids_fetched": type_ids_fetched,
            "type_ids_failed": type_ids_failed,
            "orders_count": len(all_orders),
            "total_elapsed": total_elapsed
        }
        
        logger.info(f"[MARKET ORDERS FILTERED] Finished in {total_elapsed:.2f}s. Types: {len(dedup_type_ids)}, Orders: {len(all_orders)}, Failed: {type_ids_failed}")
        return all_orders

    def get_market_orders_for_type(self, region_id: int, type_id: int) -> list:
        """
        Fetch current market orders for a specific type in a region.
        Uses the ESI type_id filter for efficiency.
        """
        endpoint = f"/markets/{region_id}/orders/"
        params = {"order_type": "all", "type_id": type_id}
        data = self._get(endpoint, params=params)
        return data if data is not None else []

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
            token = AuthManager.instance().get_valid_access_token()
        
        # Ensure we don't send "Bearer None"
        auth_header = f"Bearer {token}" if token else ""
        headers = {
            "User-Agent": "EVE-iT-Suite/1.2.1 (contact: Phyroxl)",
            "Accept": "application/json",
        }
        if auth_header:
            headers["Authorization"] = auth_header
        return headers

    def _request_auth(self, method, endpoint, token=None, params=None, json_data=None, retries=2):
        """
        Authenticated request with automatic retry on 401.
        If token is None, it fetches one from AuthManager.
        """
        url = f"{self.BASE_URL}{endpoint}" if endpoint.startswith("/") else endpoint
        
        # If no token provided, get current valid one
        current_token = token or AuthManager.instance().get_valid_access_token()
        
        try:
            self._rate_limit()
            res = self.session.request(
                method, 
                url, 
                headers=self._headers(current_token), 
                params=params, 
                json=json_data, 
                timeout=20
            )
            
            # Handle 401 Unauthorized -> Force Refresh
            if res.status_code == 401 and retries > 0:
                logger.info(f"[ESI CLIENT] 401 Unauthorized for {endpoint}. Forcing token refresh (retries left: {retries})...")
                # We force refresh by asking for a valid token again. 
                # AuthManager's get_valid_access_token handles the logic of checking if it actually needs refresh.
                # However, if we got a 401, the token IS expired regardless of what we think.
                
                # Internal hack to force AuthManager to refresh next time or now:
                auth = AuthManager.instance()
                with auth._refresh_lock:
                    # Mark current token as expired so do_refresh is triggered
                    auth.expiry = 0 
                    if auth._do_refresh():
                        new_token = auth.current_token
                        logger.info("[ESI CLIENT] Token refresh successful after 401. Retrying request...")
                        return self._request_auth(method, endpoint, new_token, params, json_data, retries - 1)
                    else:
                        logger.error("[ESI CLIENT] Token refresh failed after 401.")
            
            return res
        except Exception as e:
            logger.error(f"[ESI CLIENT] Request exception for {endpoint}: {e}")
            return None

    def character_location(self, char_id, token=None):
        """Fetches current character location (station/structure/system)."""
        res = self._request_auth("GET", f"/characters/{char_id}/location/", token)
        if res and res.status_code == 200:
            return res.json()
        return None

    def character_wallet(self, char_id, token=None):
        res = self._request_auth("GET", f"/characters/{char_id}/wallet/", token)
        if res and res.status_code == 200:
            return res.json()
        logger.warning(f"[ESI CLIENT] character_wallet char={char_id} failed with {res.status_code if res else 'No Response'}")
        return None

    def wallet_journal(self, char_id, token=None):
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

    def wallet_transactions(self, char_id, token=None, max_days=30):
        """
        Obtiene transacciones de la wallet con paginación hasta cubrir max_days.
        ESI devuelve 2500 por página.
        """
        import datetime as dt_mod
        all_transactions = []
        last_id = None
        now = dt_mod.datetime.now(dt_mod.timezone.utc)
        
        while True:
            params = {}
            if last_id:
                params['from_id'] = last_id
                
            res = self._request_auth("GET", f"/characters/{char_id}/wallet/transactions/", token, params=params)
            if res and res.status_code == 200:
                data = res.json()
                if not data:
                    break
                
                all_transactions.extend(data)
                
                # Check date of oldest transaction in this batch
                oldest_in_batch = data[-1]
                # Date format: "2023-01-01T00:00:00Z"
                dt_str = oldest_in_batch['date'].replace('Z', '')
                try:
                    # ESI dates are UTC
                    oldest_date = dt_mod.datetime.fromisoformat(dt_str).replace(tzinfo=dt_mod.timezone.utc)
                    age = now - oldest_date
                    if age.days >= max_days:
                        logger.info(f"[ESI WALLET] Reached backfill limit: {age.days} days ({oldest_date.isoformat()})")
                        break
                except Exception as e:
                    logger.error(f"[ESI WALLET] Date parse error: {e}")
                    break
                
                last_id = oldest_in_batch['transaction_id']
                # Safety break: 6 pages = 15,000 transactions (enough for most traders)
                if len(all_transactions) >= 15000: 
                    logger.warning(f"[ESI WALLET] Safety limit reached (15k tx). Stopping backfill.")
                    break
            else:
                if res and res.status_code in (401, 403):
                    return "missing_scope"
                break
                
        return all_transactions

    def character_orders(self, char_id, token=None):
        res = self._request_auth("GET", f"/characters/{char_id}/orders/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            logger.error(f"[ESI CLIENT] character_orders failed with {res.status_code} (Unauthorized/Forbidden)")
            return "missing_scope"
        return []

    def character_assets(self, char_id, token=None):
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

    def character_industry_jobs(self, char_id, token=None, include_completed=True):
        res = self._request_auth("GET", f"/characters/{char_id}/industry/jobs/", token, params={'include_completed': include_completed})
        if res and res.status_code == 200:
            return res.json()
        return []

    def get_structure_info(self, structure_id, token=None):
        """Fetch structure info (name, owner, etc). Needs ACL access."""
        res = self._request_auth("GET", f"/universe/structures/{structure_id}/", token)
        if res and res.status_code == 200:
            return res.json()
        return None

    def character_skills(self, char_id, token=None):
        res = self._request_auth("GET", f"/characters/{char_id}/skills/", token)
        if res and res.status_code == 200:
            return res.json()
        if res and res.status_code in (401, 403):
            return "missing_scope"
        return None

    def character_contracts(self, char_id: int, token: str = None):
        """GET /characters/{character_id}/contracts/"""
        res = self._request_auth("GET", f"/characters/{char_id}/contracts/", token)
        if res and res.status_code == 200:
            return res.json()
        return None

    def open_market_window(self, type_id: int, token: str = None):
        """
        Abre la ventana de mercado regional en el cliente de EVE Online.
        Requiere scope: esi-ui.open_window.v1
        """
        endpoint = "/ui/openwindow/marketdetails/"
        params = {'type_id': type_id}
        
        try:
            res = self._request_auth("POST", endpoint, token, params=params)
            if res is None: return False
            if res.status_code == 403: return "missing_scope"
            return res.status_code == 204
        except Exception as e:
            logger.error(f"[ESI CLIENT] Error opening market window (type_id={type_id}): {e}")
            return False

    def open_contract_window(self, contract_id: int, token: str = None):
        """
        Abre el contrato en el cliente de EVE Online.
        Requiere scope: esi-ui.open_window.v1
        """
        endpoint = "/ui/openwindow/contract/"
        params = {'contract_id': contract_id}
        
        try:
            res = self._request_auth("POST", endpoint, token, params=params)
            if res is None: return False
            if res.status_code == 403: return "missing_scope"
            return res.status_code == 204
        except Exception as e:
            logger.error(f"[ESI CLIENT] Error opening contract window (contract_id={contract_id}): {e}")
            return False

    def _fetch_public_contracts_page(self, region_id: int, page: int):
        """Helper para descargar una página de contratos públicos con reintentos."""
        url = f"{self.BASE_URL}/contracts/public/{region_id}/?datasource=tranquility&page={page}"
        retries = 3
        while retries > 0:
            self._rate_limit()
            try:
                response = self.session.get(url, timeout=15)
                if response.status_code == 200:
                    total_pages = int(response.headers.get('X-Pages', 1))
                    return response.json(), total_pages
                elif response.status_code == 429:
                    retry_after = float(response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    retries -= 1
                    continue
                else:
                    return None, None
            except Exception:
                time.sleep(1)
                retries -= 1
        return None, None

    def public_contracts(self, region_id: int, diagnostics=None, force_refresh: bool = False) -> list:
        """
        Fetch ALL public contracts for a region using ESI pagination.
        Filters locally for 'item_exchange' and 'outstanding'.
        """
        cache_key = f"public_contracts_v2_{region_id}"
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                if diagnostics:
                    diagnostics.esi_raw_contracts = len(cached)
                    diagnostics.esi_unique_contracts = len(cached)
                    diagnostics.esi_fetch_stopped_reason = "cache"
                return cached

        # 1. Fetch first page to get total page count
        data_p1, total_pages = self._fetch_public_contracts_page(region_id, 1)
        if data_p1 is None:
            if diagnostics: diagnostics.esi_fetch_stopped_reason = "p1_failed"
            return []

        all_raw_contracts = list(data_p1)
        pages_fetched = 1
        
        if diagnostics:
            diagnostics.esi_total_pages = total_pages
            diagnostics.esi_pages_fetched = 1
            diagnostics.esi_raw_contracts = len(data_p1)

        # 2. Fetch remaining pages in parallel
        if total_pages > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = 10
            pages_to_fetch = range(2, total_pages + 1)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_page = {executor.submit(self._fetch_public_contracts_page, region_id, p): p for p in pages_to_fetch}
                for future in as_completed(future_to_page):
                    page_data, _ = future.result()
                    pages_fetched += 1
                    if page_data:
                        all_raw_contracts.extend(page_data)
                    
                    if diagnostics:
                        diagnostics.esi_pages_fetched = pages_fetched
                        diagnostics.esi_raw_contracts = len(all_raw_contracts)

        # 3. Deduplicate by contract_id
        unique_contracts_map = {c['contract_id']: c for c in all_raw_contracts}
        unique_contracts = list(unique_contracts_map.values())
        
        if diagnostics:
            diagnostics.esi_unique_contracts = len(unique_contracts)
            diagnostics.esi_fetch_stopped_reason = "complete"

        # 4. Filter locally (item_exchange + outstanding)
        # Note: We filter locally to match the legacy behavior but we report raw counts in diagnostics
        filtered = [
            c for c in unique_contracts
            if c.get('type') == 'item_exchange'
            and c.get('status', 'outstanding') == 'outstanding'
        ]
        
        self.cache.set(cache_key, filtered, 600) # Cache for 10 mins
        return filtered

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
