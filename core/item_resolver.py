import json
import os
import logging
from typing import Dict, Optional, Tuple
from .esi_client import ESIClient

logger = logging.getLogger('eve.item_resolver')

class ItemResolver:
    _instance = None
    _cache_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_metadata_cache.json')
    
    def __init__(self):
        self.cache: Dict[int, Dict] = {}
        self._load_cache()
        self.esi = ESIClient()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_cache(self):
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convertir keys a int
                    self.cache = {int(k): v for k, v in data.items()}
            except Exception as e:
                logger.error(f"Error cargando caché de items: {e}")

    def _save_cache(self):
        os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando caché de items: {e}")

    def get_type_info(self, type_id: int, blocking: bool = True) -> Optional[Dict]:
        if type_id in self.cache:
            return self.cache[type_id]
        
        if not blocking:
            return None

        # Si no está en caché, consultar ESI
        info = self.esi.universe_type(type_id)
        if info:
            group_id = info.get('group_id')
            cat_id, grp_name, cat_name = self._get_detailed_info(group_id)
            
            clean_info = {
                'group_id': group_id,
                'category_id': cat_id,
                'group_name': grp_name,
                'category_name': cat_name
            }
            self.cache[type_id] = clean_info
            # No llamar _save_cache() aquí: este método puede ejecutarse desde
            # múltiples hilos (ThreadPoolExecutor en prefetch_type_metadata).
            # Escribir el archivo desde hilos simultáneos corrompe el JSON.
            # prefetch_type_metadata ya llama _save_cache() una sola vez al final.
            return clean_info
        return None

    def prefetch_type_metadata(self, type_ids: list[int], max_workers=8):
        """Precarga metadata para una lista de items de forma concurrente."""
        from concurrent.futures import ThreadPoolExecutor
        
        # Eliminar duplicados y asegurar ints
        unique_ids = list(set(int(tid) for tid in type_ids))
        missing = [tid for tid in unique_ids if tid not in self.cache]
        
        if not missing:
            return {"total": len(unique_ids), "cached": len(unique_ids), "fetched": 0, "failed": 0, "failed_ids": []}
            
        logger.info(f"[METADATA] total_unique={len(unique_ids)} | cached={len(unique_ids) - len(missing)} | missing={len(missing)}")
        fetched = 0
        failed = 0
        failed_ids = []
        
        def fetch_one(tid):
            try:
                info = self.get_type_info(tid, blocking=True)
                return tid, info, None
            except Exception as e:
                return tid, None, str(e)
            
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(fetch_one, missing))
            
        for tid, info, err in results:
            if info:
                fetched += 1
            else:
                failed += 1
                failed_ids.append(tid)
                if err:
                    logger.debug(f"[METADATA FETCH ERROR] type_id={tid} error={err}")
                
        self._save_cache()
        
        res = {
            "total": len(unique_ids), 
            "cached": len(unique_ids) - len(missing), 
            "fetched": fetched, 
            "failed": failed,
            "failed_ids": failed_ids[:10] # Solo una muestra
        }
        logger.info(f"[METADATA] prefetch_done: fetched={fetched} failed={failed}")
        if failed > 0:
            logger.warning(f"[METADATA] Failed IDs sample: {failed_ids[:10]}")
            
        return res

    def _get_detailed_info(self, group_id: int) -> Tuple[Optional[int], str, str]:
        if not group_id: return None, "Unknown Group", "Unknown Category"
        
        group_info = self.esi._get(f"/universe/groups/{group_id}/", ttl=86400)
        if group_info:
            cat_id = group_info.get('category_id')
            grp_name = group_info.get('name', f"Group {group_id}")
            
            cat_name = "Unknown Category"
            if cat_id:
                cat_info = self.esi._get(f"/universe/categories/{cat_id}/", ttl=86400)
                if cat_info:
                    cat_name = cat_info.get('name', f"Category {cat_id}")
            
            return cat_id, grp_name, cat_name
        return None, "Unknown Group", "Unknown Category"

    def resolve_category_info(self, type_id: int, blocking: bool = False) -> Tuple[Optional[int], Optional[int], str, str]:
        """Retorna (category_id, group_id, group_name, category_name)."""
        info = self.get_type_info(type_id, blocking=blocking)
        if info:
            return (
                info.get('category_id'), 
                info.get('group_id'), 
                info.get('group_name', 'Unknown'), 
                info.get('category_name', 'Unknown')
            )
        return None, None, "Unknown", "Unknown"
