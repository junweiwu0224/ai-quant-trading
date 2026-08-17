from __future__ import annotations

import signal

from engine.worker_signals import install_shutdown_handlers


class _Worker:
    def __init__(self) -> None:
        self.stop_requests = 0

    def request_stop(self) -> None:
        self.stop_requests += 1


def test_install_shutdown_handlers_routes_sigterm_and_sigint_to_worker(monkeypatch) -> None:
    worker = _Worker()
    handlers = {}

    def capture(signum, handler):
        handlers[signum] = handler

    monkeypatch.setattr(signal, "signal", capture)
    install_shutdown_handlers(worker, name="fixture-worker")

    handlers[signal.SIGTERM](signal.SIGTERM, None)
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert worker.stop_requests == 2
