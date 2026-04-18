"""
tick_calculator.py — Cálculo preciso de ciclos de pago ESS (ticks) de EVE Online.

LÓGICA REAL DE LOS TICKS EVE:
  1. Durante ~20 minutos el personaje mata NPCs.
     Cada kill genera UN bounty individual en el log.
     Estos bounties llegan ESPACIADOS (generalmente > 5s entre ellos).

  2. Al final del ciclo ocurre el PAYOUT ESS:
     MUCHOS bounties llegan en RÁFAGA DENSA (< 10s total) con valores más altos.
     Esto es el "tick" real.

  3. Después del payout, el siguiente BOUNTY INDIVIDUAL marca el inicio
     del nuevo ciclo. El siguiente tick = ese inicio + 20min.

DISTINCIÓN BOUNTY INDIVIDUAL vs PAYOUT:
  Un burst de eventos se clasifica como PAYOUT si cumple:
    - Duración total del burst < PAYOUT_MAX_DURATION_SECS  (burst corto y denso)
    - Número de eventos >= PAYOUT_MIN_EVENTS               (muchos eventos juntos)

  Si no cumple esas condiciones al cerrarse, era solo bounties individuales
  del ciclo normal — no un payout.

TIMESTAMPS:
  Todos los cálculos usan processed_at (wall clock del sistema = datetime.now()
  cuando el watcher procesa la línea). Esto es timezone-safe.
"""

from datetime import datetime, timedelta
from typing import Optional


# ── Constantes ────────────────────────────────────────────────────────────────

BURST_GAP_SECS          = 60    # gap sin eventos que cierra un burst
PAYOUT_MAX_DURATION_SECS = 30   # un payout ESS dura < 30s (típicamente < 5s)
PAYOUT_MIN_EVENTS        = 3    # un payout tiene ≥3 líneas de bounty juntas
DEFAULT_CYCLE_SECS       = 1200 # 20 minutos
MIN_CYCLE_SECS           = 300  # 5 minutos mínimo
MAX_CYCLE_SECS           = 2400 # 40 minutos máximo
MAX_TICK_HISTORY         = 20


class TickCalculator:
    """
    Detecta payouts ESS y calcula el countdown al próximo tick.

    Estado interno:
      _payouts:              lista de datetimes (wall clock) de cada payout detectado
      _current_cycle_start:  wall clock del primer bounty individual post-payout
      _current_cycle_isk:    ISK acumulado del ciclo en curso

    Burst detector (acumula eventos cercanos para clasificarlos):
      _burst_start, _burst_last:  extremos temporales del burst activo
      _burst_isk, _burst_count:   totales del burst
      _awaiting_cycle_start:      True tras un payout, esperando primer bounty
    """

    def __init__(self):
        self._payouts: list[datetime] = []
        self._current_cycle_start: Optional[datetime] = None
        self._current_cycle_isk: int = 0

        self._burst_start: Optional[datetime] = None
        self._burst_last:  Optional[datetime] = None
        self._burst_isk:   int = 0
        self._burst_count: int = 0

        self._awaiting_cycle_start: bool = False

    # ── API pública ───────────────────────────────────────────────────────────

    def record_event(self, processed_at: datetime, isk: int,
                     is_payout: bool = False) -> bool:
        """
        Registra un evento. Retorna True si se detectó un nuevo payout.
        is_payout=True: pago ESS real del Chatlog (máxima precisión, sin heurística).
        """
        new_payout = False

        # PAYOUT EXPLÍCITO desde Chatlog — detección 100% precisa
        if is_payout:
            if self._burst_start is not None:
                self._close_and_classify_burst()   # cierra bounties individuales activos
            self._payouts.append(processed_at)
            if len(self._payouts) > MAX_TICK_HISTORY:
                self._payouts = self._payouts[-MAX_TICK_HISTORY:]
            self._current_cycle_isk    = 0
            self._current_cycle_start  = None
            self._awaiting_cycle_start = True
            self._provisional_cycle_start = None
            self._provisional_cycle_isk   = 0
            return True

        if self._burst_start is None:
            self._open_burst(processed_at, isk)
        else:
            gap = (processed_at - self._burst_last).total_seconds()
            if gap < BURST_GAP_SECS:
                self._extend_burst(processed_at, isk)
            else:
                # Silencio > 60s: cerrar burst anterior y clasificarlo
                new_payout = self._close_and_classify_burst()
                self._open_burst(processed_at, isk)

        # Si esperamos el inicio del nuevo ciclo y no es el inicio de un payout,
        # este evento podría ser el primer bounty del nuevo ciclo.
        # Solo lo marcamos si el burst recién abierto es de 1 evento
        # (no sabemos aún si es un payout o bounty individual).
        # Lo resolveremos cuando el burst se cierre o en get_tick_info.
        if self._awaiting_cycle_start and self._burst_count == 1:
            # Provisionalmente, este puede ser el inicio del ciclo.
            # Se confirmará cuando el burst se cierre como NO-payout.
            self._provisional_cycle_start = processed_at
            self._provisional_cycle_isk   = isk
        elif not self._awaiting_cycle_start and self._current_cycle_start is not None:
            self._current_cycle_isk += isk

        return new_payout

    def get_tick_info(self, now: Optional[datetime] = None) -> dict:
        """
        Devuelve información del ciclo actual. Nunca devuelve NaN.
        """
        now = now or datetime.now()
        n = len(self._payouts)

        if n == 0 and self._current_cycle_start is None:
            # También verificar si hay un provisional
            if not hasattr(self, '_provisional_cycle_start') or self._provisional_cycle_start is None:
                return self._no_data()

        interval = self._calc_interval()
        estimated = (interval == DEFAULT_CYCLE_SECS)

        # Referencia para el próximo tick
        ref = self._current_cycle_start
        if ref is None and hasattr(self, '_provisional_cycle_start'):
            ref = getattr(self, '_provisional_cycle_start', None)
        if ref is None and n > 0:
            ref = self._payouts[-1]
        if ref is None:
            return self._no_data()

        next_ts = ref + timedelta(seconds=interval)
        if next_ts < now:
            elapsed = (now - next_ts).total_seconds()
            skip = int(elapsed / interval) + 1
            next_ts += timedelta(seconds=interval * skip)

        secs = max(0, int((next_ts - now).total_seconds()))
        cycle_isk = self._current_cycle_isk
        if cycle_isk == 0 and hasattr(self, '_provisional_cycle_isk'):
            cycle_isk = getattr(self, '_provisional_cycle_isk', 0)

        return {
            'tick_count':        n,
            'interval_secs':     round(interval),
            'last_payout_at':    self._payouts[-1] if n > 0 else None,
            'last_tick_ts':      self._payouts[-1] if n > 0 else None,  # alias
            'cycle_start':       self._current_cycle_start or getattr(self, '_provisional_cycle_start', None),
            'next_tick_ts':      next_ts,
            'secs_until_next':   secs,
            'countdown_str':     f"{secs // 60:02d}:{secs % 60:02d}",
            'current_cycle_isk': cycle_isk,
            'is_estimated':      estimated,
        }

    def reset(self):
        self._payouts.clear()
        self._current_cycle_start  = None
        self._current_cycle_isk    = 0
        self._burst_start          = None
        self._burst_last           = None
        self._burst_isk            = 0
        self._burst_count          = 0
        self._awaiting_cycle_start = False
        self._provisional_cycle_start = None
        self._provisional_cycle_isk   = 0

    # ── Lógica interna ────────────────────────────────────────────────────────

    def _open_burst(self, ts: datetime, isk: int):
        self._burst_start = ts
        self._burst_last  = ts
        self._burst_isk   = isk
        self._burst_count = 1
        # Si es el primer evento de la sesión (sin payouts previos),
        # usarlo como cycle_start provisional para mostrar estimación 20min
        if not self._payouts and self._current_cycle_start is None and not self._awaiting_cycle_start:
            if not hasattr(self, '_provisional_cycle_start') or self._provisional_cycle_start is None:
                self._provisional_cycle_start = ts
                self._provisional_cycle_isk   = isk

    def _extend_burst(self, ts: datetime, isk: int):
        self._burst_last   = ts
        self._burst_isk   += isk
        self._burst_count += 1

    def _close_and_classify_burst(self) -> bool:
        """
        Cierra el burst activo y decide si era un PAYOUT o bounties individuales.

        Un PAYOUT se caracteriza por:
          - Duración corta (< PAYOUT_MAX_DURATION_SECS)
          - Muchos eventos (>= PAYOUT_MIN_EVENTS)

        Retorna True si se clasificó como payout.
        """
        if self._burst_start is None:
            return False

        duration = (self._burst_last - self._burst_start).total_seconds()
        is_payout = (
            duration <= PAYOUT_MAX_DURATION_SECS and
            self._burst_count >= PAYOUT_MIN_EVENTS
        )

        if is_payout:
            self._payouts.append(self._burst_start)
            if len(self._payouts) > MAX_TICK_HISTORY:
                self._payouts = self._payouts[-MAX_TICK_HISTORY:]
            self._current_cycle_isk    = 0
            self._current_cycle_start  = None
            self._awaiting_cycle_start = True
            # Limpiar provisional si había uno
            self._provisional_cycle_start = None
            self._provisional_cycle_isk   = 0
        else:
            # Bounties individuales del ciclo normal.
            # Si estábamos esperando cycle_start y había un provisional, confirmarlo.
            if self._awaiting_cycle_start and hasattr(self, '_provisional_cycle_start') and self._provisional_cycle_start:
                self._current_cycle_start  = self._provisional_cycle_start
                self._current_cycle_isk    = self._provisional_cycle_isk + self._burst_isk
                self._awaiting_cycle_start = False
                self._provisional_cycle_start = None
                self._provisional_cycle_isk   = 0
            elif self._current_cycle_start is not None:
                self._current_cycle_isk += self._burst_isk

        # Limpiar burst
        self._burst_start = None
        self._burst_last  = None
        self._burst_isk   = 0
        self._burst_count = 0

        return is_payout

    def _calc_interval(self) -> float:
        n = len(self._payouts)
        if n < 2:
            return float(DEFAULT_CYCLE_SECS)
        intervals = [
            (self._payouts[i] - self._payouts[i-1]).total_seconds()
            for i in range(1, n)
        ]
        valid = [iv for iv in intervals if MIN_CYCLE_SECS <= iv <= MAX_CYCLE_SECS]
        if not valid:
            return float(DEFAULT_CYCLE_SECS)
        return sum(valid) / len(valid)

    @staticmethod
    def _no_data() -> dict:
        return {
            'tick_count':        0,
            'interval_secs':     None,
            'last_payout_at':    None,
            'last_tick_ts':      None,
            'cycle_start':       None,
            'next_tick_ts':      None,
            'secs_until_next':   -1,
            'countdown_str':     '--:--',
            'current_cycle_isk': 0,
            'is_estimated':      True,
        }
