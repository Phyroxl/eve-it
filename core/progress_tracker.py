import time
import logging

logger = logging.getLogger('eve.progress')

class ProgressTracker:
    """
    Helper para gestionar el progreso fluido y por fases en la UI.
    Permite distribuir el 100% total entre distintas fases lógicas.
    """
    def __init__(self, callback=None, task_name="Task"):
        self.callback = callback
        self.task_name = task_name
        self.current_percent = 0.0
        self.phase_name = ""
        self.phase_start_pct = 0.0
        self.phase_end_pct = 0.0
        self.phase_total = 1.0
        self.last_update_time = 0
        self.min_update_interval = 0.05 # 50ms throttling

    def set_phase(self, name, start_pct, end_pct, total=1):
        self.phase_name = name
        self.phase_start_pct = float(start_pct)
        self.phase_end_pct = float(end_pct)
        self.phase_total = float(total) if total and total > 0 else 1.0
        logger.debug(f"[{self.task_name}] Phase: {name} ({start_pct}% -> {end_pct}%) total={total}")
        # Al cambiar de fase, emitimos inmediatamente el inicio de la misma
        self.update(0, message=name, force=True)

    def update(self, current, total=None, message=None, force=False):
        if total and total > 0:
            self.phase_total = float(total)
            
        # Calcular porcentaje dentro de la fase
        progress_in_phase = float(current) / self.phase_total
        progress_in_phase = min(1.0, max(0.0, progress_in_phase))
        
        # Mapear al rango global
        phase_range = self.phase_end_pct - self.phase_start_pct
        new_percent = self.phase_start_pct + (progress_in_phase * phase_range)
        
        # Asegurar que el progreso nunca retrocede
        if new_percent < self.current_percent and not force:
            return
            
        self.current_percent = new_percent
        
        # Throttling para no saturar el hilo de UI
        now = time.time()
        if not force and (now - self.last_update_time < self.min_update_interval):
            return
            
        self.last_update_time = now
        
        if self.callback:
            msg = message if message else self.phase_name
            self.callback(int(self.current_percent), msg)

    def finish(self, message="Completado"):
        self.current_percent = 100.0
        if self.callback:
            self.callback(100, message)
        logger.info(f"[{self.task_name}] Finished: {message}")
