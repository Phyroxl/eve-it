import logging
from typing import Dict, List, Optional, Set, Callable
from PySide6.QtCore import QObject, Signal, QUrl, Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QLinearGradient
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

logger = logging.getLogger('eve.ui.icons')

class EveIconService(QObject):
    """
    Centralized service for EVE Online item icons with fallback support and placeholders.
    Endpoints: icon -> render -> bp -> bpc -> placeholder.
    """
    icon_loaded = Signal(int, QPixmap)  # type_id, pixmap
    icon_failed = Signal(int, str)      # type_id, reason
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EveIconService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def instance(cls):
        return cls()

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self.net_manager = QNetworkAccessManager(self)
        self.icon_cache: Dict[int, QPixmap] = {}
        self.failed_ids: Set[int] = set()
        self.pending_requests: Dict[int, List[Callable[[QPixmap], None]]] = {}
        
        # Telemetry
        self.stats = {
            "requests": 0,
            "cache_hits": 0,
            "loaded": 0,
            "failed_total": 0,
            "placeholders": 0,
            "endpoint_icon": 0,
            "endpoint_render": 0,
            "endpoint_bp": 0,
            "endpoint_bpc": 0,
            "last_errors": []
        }
        self._initialized = True

    def get_icon(self, type_id: int, size: int = 32, callback: Optional[Callable[[QPixmap], None]] = None) -> QPixmap:
        """
        Main entry point to get an icon. 
        Returns a placeholder immediately if not cached, and triggers async load.
        """
        self.stats["requests"] += 1
        
        # 1. Check cache
        if type_id in self.icon_cache:
            self.stats["cache_hits"] += 1
            pix = self.icon_cache[type_id]
            if callback:
                callback(pix)
            return pix
        
        # 2. Check failed (already tried all endpoints)
        if type_id in self.failed_ids:
            pix = self._generate_placeholder(type_id, size)
            if callback:
                callback(pix)
            return pix

        # 3. Handle pending or start new
        if type_id in self.pending_requests:
            if callback:
                self.pending_requests[type_id].append(callback)
        else:
            self.pending_requests[type_id] = [callback] if callback else []
            self._start_fetch_chain(type_id, size)
            
        # Return generic placeholder while loading
        return self._generate_placeholder(type_id, size, label="...")

    def _start_fetch_chain(self, type_id: int, size: int):
        """Starts the sequential fetch: icon -> render -> bp -> bpc."""
        self._try_endpoint(type_id, size, "icon")

    def _try_endpoint(self, type_id: int, size: int, endpoint_type: str):
        url = f"https://images.evetech.net/types/{type_id}/{endpoint_type}?size={size}"
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.Attribute.User, endpoint_type)
        
        reply = self.net_manager.get(request)
        reply.finished.connect(lambda: self._on_reply_finished(reply, type_id, size))

    def _on_reply_finished(self, reply: QNetworkReply, type_id: int, size: int):
        endpoint_type = reply.attribute(QNetworkRequest.Attribute.User)
        
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    self._on_success(type_id, pixmap, endpoint_type)
                    reply.deleteLater()
                    return
            
            # If we are here, it failed (404, etc)
            error_str = f"{endpoint_type} failed: {reply.errorString()}"
            self.stats["last_errors"].append(f"ID {type_id}: {error_str}")
            if len(self.stats["last_errors"]) > 20: self.stats["last_errors"].pop(0)
            
            # Fallback chain
            chain = ["icon", "render", "bp", "bpc"]
            if endpoint_type in chain:
                curr_idx = chain.index(endpoint_type)
                if curr_idx < len(chain) - 1:
                    next_endpoint = chain[curr_idx + 1]
                    self._try_endpoint(type_id, size, next_endpoint)
                else:
                    # End of chain, generate placeholder
                    self._on_total_failure(type_id, size)
            else:
                self._on_total_failure(type_id, size)
                
        except Exception as e:
            logger.error(f"Error in icon reply processing for {type_id}: {e}")
            self._on_total_failure(type_id, size)
        finally:
            reply.deleteLater()

    def _on_success(self, type_id: int, pixmap: QPixmap, endpoint_type: str):
        self.icon_cache[type_id] = pixmap
        self.stats["loaded"] += 1
        self.stats[f"endpoint_{endpoint_type}"] += 1
        
        callbacks = self.pending_requests.pop(type_id, [])
        for cb in callbacks:
            if cb: cb(pixmap)
        self.icon_loaded.emit(type_id, pixmap)

    def _on_total_failure(self, type_id: int, size: int):
        logger.debug(f"Total icon failure for ID {type_id}. Generating placeholder.")
        self.stats["failed_total"] += 1
        self.stats["placeholders"] += 1
        self.failed_ids.add(type_id)
        
        pixmap = self._generate_placeholder(type_id, size)
        self.icon_cache[type_id] = pixmap
        
        callbacks = self.pending_requests.pop(type_id, [])
        for cb in callbacks:
            if cb: cb(pixmap)
        self.icon_failed.emit(type_id, "All endpoints failed")

    def _generate_placeholder(self, type_id: int, size: int, label: Optional[str] = None) -> QPixmap:
        """Generates a category-aware or generic placeholder QPixmap."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        grad = QLinearGradient(0, 0, 0, size)
        grad.setColorAt(0, QColor("#1e293b"))
        grad.setColorAt(1, QColor("#0f172a"))
        painter.setBrush(grad)
        painter.setPen(QColor("#334155"))
        painter.drawRoundedRect(1, 1, size-2, size-2, 4, 4)
        
        # Determine label if not provided
        if not label:
            label = self._get_category_label(type_id)
            
        # Draw label
        painter.setPen(QColor("#94a3b8"))
        font = QFont("Arial", 8, QFont.Weight.Bold)
        if size < 32: font.setPointSize(6)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
        
        painter.end()
        return pixmap

    def _get_category_label(self, type_id: int) -> str:
        """Classify item to get a 2-4 letter label."""
        from core.item_resolver import ItemResolver
        cat_id, grp_id, _, _ = ItemResolver.instance().resolve_category_info(type_id, blocking=False)
        
        if cat_id is None: return "?"
        
        # Categories (simplified)
        # Ships: 6
        if cat_id == 6: return "SHIP"
        # Modules: 7, 8, 18, 22, 23, 32, 65, 66...
        if cat_id in (7, 8, 18, 32): return "MOD"
        # Drones: 18 (some)
        if grp_id in (100, 101, 311, 638): return "DRN"
        # Blueprints: 9
        if cat_id == 9: return "BP"
        # SKINS: 91
        if cat_id == 91: return "SKIN"
        # Ore/Minerals: 25, 4, 17
        if cat_id in (25, 4, 17): return "ORE"
        
        return "ITEM"

    def get_diagnostics(self) -> dict:
        d = self.stats.copy()
        d["cache_size"] = len(self.icon_cache)
        d["failed_count"] = len(self.failed_ids)
        return d
