"""Signal handling shared by the standalone Worker entry points."""

from __future__ import annotations

import signal
from typing import Protocol

from loguru import logger


class StoppableWorker(Protocol):
    def request_stop(self) -> None: ...


def install_shutdown_handlers(worker: StoppableWorker, *, name: str) -> None:
    """Turn container termination into cooperative Worker shutdown."""

    def handle(signum: int, _frame: object) -> None:
        logger.info("{} received signal {}; requesting cooperative stop", name, signum)
        worker.request_stop()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)


__all__ = ["StoppableWorker", "install_shutdown_handlers"]
