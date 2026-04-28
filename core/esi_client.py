import json
import logging
import time
import requests
from threading import Lock

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
    
    def __init__(self):
        self.cache = ESICache()
        self.session = requests.Session()
        self.last_request_time = 0
        self.rate_limit_lock = Lock()
        
    def _rate_limit(self):
        with self.rate_limit_lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < 0.1: # Max 10 req/s -> 100ms per req
                time.sleep(0.1 - elapsed)
            self.last_request_time = time.time()
            
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
                    logger.warning(f"ESI rate limit en {endpoint}, esperando {retry_after}s")
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

    def market_orders(self, region_id: int):
        cache_key = f"market_orders_{region_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        all_orders = []
        page = 1
        while True:
            self._rate_limit()
            try:
                params = {'page': page, 'order_type': 'all'}
                response = self.session.get(f"{self.BASE_URL}/markets/{region_id}/orders/", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    all_orders.extend(data)
                    pages = int(response.headers.get('X-Pages', 1))
                    if page >= pages:
                        break
                    page += 1
                elif response.status_code >= 500:
                    time.sleep(1)
                    continue
                else:
                    break
            except Exception as e:
                logger.warning(f"ESI market_orders error (region {region_id}): {e}")
                time.sleep(1)
                break

        if all_orders:
            self.cache.set(cache_key, all_orders, 300) # Cache 5 mins
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

    def _headers(self, token):
        return {'Authorization': f'Bearer {token}'}

    def character_wallet(self, char_id, token):
        url = f"{self.BASE_URL}/characters/{char_id}/wallet/"
        try:
            res = self.session.get(url, headers=self._headers(token), timeout=15)
            if res.status_code == 200:
                return res.json()
            logger.warning(f"ESI character_wallet char={char_id} → HTTP {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.error(f"ESI character_wallet char={char_id} excepción: {e}")
        return None

    def character_wallet_journal(self, char_id, token):
        all_data = []
        page = 1
        while True:
            url = f"{self.BASE_URL}/characters/{char_id}/wallet/journal/"
            params = {'page': page}
            try:
                self._rate_limit()
                res = self.session.get(url, headers=self._headers(token), params=params, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    if not data: break
                    all_data.extend(data)
                    pages = int(res.headers.get('X-Pages', 1))
                    if page >= pages: break
                    page += 1
                else:
                    logger.warning(f"ESI wallet_journal char={char_id} page={page} → HTTP {res.status_code}")
                    break
            except Exception as e:
                logger.error(f"ESI wallet_journal char={char_id} page={page} excepción: {e}")
                break
        
        logger.info(f"ESI wallet_journal char={char_id} → {len(all_data)} entradas totales en {page} páginas")
        return all_data

    def character_wallet_transactions(self, char_id, token):
        all_data = []
        page = 1
        # ESI permite hasta 2500 transacciones (50 páginas de 50)
        while page <= 50:
            url = f"{self.BASE_URL}/characters/{char_id}/wallet/transactions/"
            params = {'page': page}
            try:
                self._rate_limit()
                res = self.session.get(url, headers=self._headers(token), params=params, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    if not data: break
                    all_data.extend(data)
                    # El header X-Pages no siempre está presente en este endpoint o es confuso,
                    # paramos si recibimos menos de 50 (fin de datos)
                    if len(data) < 50: break
                    page += 1
                else:
                    logger.warning(f"ESI wallet_transactions char={char_id} page={page} → HTTP {res.status_code}")
                    if res.status_code in (401, 403):
                        return "missing_scope"
                    break
            except Exception as e:
                logger.error(f"ESI wallet_transactions char={char_id} page={page} excepción: {e}")
                break
        
        logger.info(f"ESI wallet_transactions char={char_id} → {len(all_data)} transacciones totales en {page} páginas")
        return all_data

    def character_orders(self, char_id, token):
        url = f"{self.BASE_URL}/characters/{char_id}/orders/"
        try:
            self._rate_limit()
            res = self.session.get(url, headers=self._headers(token), timeout=15)
            if res.status_code == 200:
                data = res.json()
                logger.info(f"ESI character_orders char={char_id} → {len(data)} órdenes")
                return data
            logger.warning(f"ESI character_orders char={char_id} → HTTP {res.status_code}: {res.text[:200]}")
            if res.status_code in (401, 403):
                raise Exception(f"Token expirado o sin permisos (HTTP {res.status_code}).")
            elif res.status_code >= 500:
                raise Exception(f"Servidor ESI caído (HTTP {res.status_code}).")
            else:
                raise Exception(f"Error desconocido (HTTP {res.status_code}).")
        except Exception as e:
            logger.error(f"ESI character_orders char={char_id} excepción: {e}")
            raise e

    def character_assets(self, char_id, token):
        all_assets = []
        page = 1
        while True:
            url = f"{self.BASE_URL}/characters/{char_id}/assets/"
            params = {'page': page}
            try:
                self._rate_limit()
                res = self.session.get(url, headers=self._headers(token), params=params, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    if not data: break
                    all_assets.extend(data)
                    pages = int(res.headers.get('X-Pages', 1))
                    if page >= pages: break
                    page += 1
                else:
                    logger.warning(f"ESI character_assets char={char_id} page={page} → HTTP {res.status_code}")
                    if res.status_code in (401, 403):
                        return "missing_scope"
                    break
            except Exception as e:
                logger.error(f"ESI character_assets char={char_id} page={page} excepción: {e}")
                break
        return all_assets

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
