"""Tests for shutdown helpers — verify fast, idempotent teardown."""
import threading
import time
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestChatWatcherShutdown(unittest.TestCase):
    def test_stop_event_interrupts_sleep(self):
        """ChatWatcher.stop() wakes the sleeping poll immediately."""
        from translator.chat_reader import ChatWatcher

        received = []
        w = ChatWatcher(callback=lambda m: received.append(m), poll_interval=10.0)
        w.start()
        t0 = time.perf_counter()
        w.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, f"stop() took {elapsed:.2f}s — should be <1s")

    def test_stop_idempotent(self):
        """Calling stop() twice must not raise."""
        from translator.chat_reader import ChatWatcher
        w = ChatWatcher(callback=lambda m: None)
        w.start()
        w.stop()
        w.stop()  # second call must not raise

    def test_stop_before_start(self):
        """Calling stop() without start() must not raise."""
        from translator.chat_reader import ChatWatcher
        w = ChatWatcher(callback=lambda m: None)
        w.stop()


class TestIntelAlertServiceShutdown(unittest.TestCase):
    def _make_service(self):
        from core.intel_alert_service import IntelAlertService, IntelAlertConfig
        cfg = IntelAlertConfig()
        cfg.enabled = False  # disable actual scanning
        return IntelAlertService(config=cfg, callback=lambda e: None)

    def test_stop_event_interrupts_sleep(self):
        """IntelAlertService.stop() returns quickly thanks to _stop_event."""
        svc = self._make_service()
        svc.start()
        time.sleep(0.05)  # let thread enter its sleep
        t0 = time.perf_counter()
        svc.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, f"stop() took {elapsed:.2f}s — should be <1s")

    def test_stop_idempotent(self):
        """Calling stop() twice must not raise."""
        svc = self._make_service()
        svc.start()
        svc.stop()
        svc.stop()

    def test_start_stop_restart(self):
        """Service can be restarted after stop."""
        svc = self._make_service()
        svc.start()
        svc.stop()
        svc.start()
        self.assertTrue(svc._running)
        svc.stop()


class TestAppControllerShutdownIdempotent(unittest.TestCase):
    def test_shutdown_flag_prevents_double_run(self):
        """controller.shutdown() sets _shutdown_done; second call is a no-op."""
        import types

        class FakeController:
            _shutdown_done = False
            _lock = threading.Lock()
            calls = []

            def _stop_tracker_internal(self): self.calls.append('tracker')
            def stop_translator(self): self.calls.append('translator')
            def hide_overlay(self): self.calls.append('overlay')
            def stop_replicator(self): self.calls.append('replicator')
            def stop_dashboard(self): self.calls.append('dashboard')

            shutdown = lambda self: None  # replaced below

        # Bind real shutdown to FakeController
        from controller.app_controller import AppController
        FakeController.shutdown = AppController.shutdown

        # Need PROJECT_ROOT for cleanup step
        import types as _types
        import logging
        FakeController.__module__ = 'controller.app_controller'

        fc = FakeController()
        fc.shutdown()
        n_first = len(fc.calls)
        fc.shutdown()  # second call — should be no-op
        self.assertEqual(len(fc.calls), n_first, "Second shutdown() call should be no-op")


if __name__ == '__main__':
    unittest.main()
