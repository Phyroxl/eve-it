"""
overlay/replicator_input_sequencer.py
Lightweight focus-only input sequencer for the Replicator.

Guarantees exactly-one focus per submitted action and provides structured
logging so timing problems are diagnosable from the perf log.

EULA-safe: only calls focus_eve_window_reliable() — no game input injection.
"""
from __future__ import annotations

import queue
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger('eve.hotkeys')

_ACTION_ID_LOCK = threading.Lock()
_action_id_seq: int = 0


def _next_action_id() -> int:
    global _action_id_seq
    with _ACTION_ID_LOCK:
        _action_id_seq += 1
        return _action_id_seq


class ReplicatorInputSequencer:
    """Single-worker queue that serialises focus requests for EVE windows.

    Usage:
        seq = ReplicatorInputSequencer()
        seq.start()
        action_id = seq.submit_action(hwnd=1234, title='EVE — Alpha')
        seq.stop()

    Each submitted action is identified by an integer action_id.  The
    sequencer logs INPUT_RECEIVED, INPUT_SENT / INPUT_BLOCKED / INPUT_DROPPED
    for each action so the caller can correlate timing issues.

    Thread-safety: submit_action() is safe to call from any thread.
    """

    _SENTINEL = object()

    def __init__(self, deadline_ms: int = 120) -> None:
        self._deadline_ms = deadline_ms
        self._q: queue.Queue = queue.Queue(maxsize=4)
        self._worker: Optional[threading.Thread] = None
        self._running = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(
            target=self._run, daemon=True, name='ReplicatorInputSequencer'
        )
        self._worker.start()
        logger.debug('[SEQUENCER] started deadline_ms=%d', self._deadline_ms)

    def stop(self, timeout_s: float = 1.0) -> None:
        self._running = False
        try:
            self._q.put_nowait(self._SENTINEL)
        except queue.Full:
            pass
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout_s)
        self._worker = None
        logger.debug('[SEQUENCER] stopped')

    # ── Public API ─────────────────────────────────────────────────────────

    def submit_action(
        self,
        hwnd: int,
        title: str,
        deadline_ms: Optional[int] = None,
    ) -> int:
        """Queue a focus request.  Returns action_id for log correlation."""
        action_id = _next_action_id()
        deadline = deadline_ms if deadline_ms is not None else self._deadline_ms
        action = {
            'id': action_id,
            'hwnd': hwnd,
            'title': title,
            'deadline_ms': deadline,
            'submitted_at': time.perf_counter(),
        }
        try:
            self._q.put_nowait(action)
            logger.debug(
                '[INPUT RECEIVED] action_id=%d hwnd=%d title=%r deadline_ms=%d',
                action_id, hwnd, title, deadline,
            )
        except queue.Full:
            logger.debug(
                '[INPUT DROPPED full_queue] action_id=%d hwnd=%d title=%r',
                action_id, hwnd, title,
            )
        return action_id

    # ── Worker ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while self._running:
            try:
                action = self._q.get(timeout=0.5)
            except queue.Empty:
                continue

            if action is self._SENTINEL:
                break

            self._process(action)

    def _process(self, action: dict) -> None:
        action_id = action['id']
        hwnd = action['hwnd']
        title = action['title']
        deadline_ms = action['deadline_ms']
        submitted_at = action['submitted_at']

        age_ms = (time.perf_counter() - submitted_at) * 1000.0
        if age_ms > deadline_ms:
            logger.debug(
                '[INPUT DROPPED stale] action_id=%d hwnd=%d title=%r '
                'age_ms=%.1f deadline_ms=%d',
                action_id, hwnd, title, age_ms, deadline_ms,
            )
            return

        try:
            from overlay.win32_capture import focus_eve_window_reliable, is_hwnd_valid
        except ImportError:
            logger.warning('[SEQUENCER] win32_capture unavailable')
            return

        if not is_hwnd_valid(hwnd):
            logger.debug(
                '[INPUT BLOCKED] action_id=%d hwnd=%d title=%r reason=invalid_hwnd',
                action_id, hwnd, title,
            )
            return

        t0 = time.perf_counter()
        remaining_ms = max(20, deadline_ms - age_ms)
        ok, detail = focus_eve_window_reliable(hwnd, max_total_ms=int(remaining_ms))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if ok:
            logger.debug(
                '[INPUT SENT] action_id=%d hwnd=%d title=%r elapsed_ms=%.1f %s',
                action_id, hwnd, title, elapsed_ms, detail,
            )
        else:
            logger.debug(
                '[INPUT BLOCKED] action_id=%d hwnd=%d title=%r reason=focus_failed '
                'elapsed_ms=%.1f %s',
                action_id, hwnd, title, elapsed_ms, detail,
            )
