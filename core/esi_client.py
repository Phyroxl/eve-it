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
        res = self.session.get(url, headers=self._headers(token))
        return res.json() if res.status_code == 200 else None

    def character_wallet_journal(self, char_id, token):
        url = f"{self.BASE_URL}/characters/{char_id}/wallet/journal/"
        res = self.session.get(url, headers=self._headers(token))
        return res.json() if res.status_code == 200 else []

    def character_wallet_transactions(self, char_id, token):
        url = f"{self.BASE_URL}/characters/{char_id}/wallet/transactions/"
        res = self.session.get(url, headers=self._headers(token))
        return res.json() if res.status_code == 200 else []

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
