"""Run the independent AI task worker without starting the Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from engine.ai_worker import AIWorker, ai_worker_enabled
from engine.worker_signals import install_shutdown_handlers


@click.command()
@click.option("--once", is_flag=True, help="Acquire the lease, process one batch and exit.")
def main(once: bool) -> None:
    """Start only when AI_WORKER_ENABLED is explicitly enabled."""

    setup_logging()
    if not ai_worker_enabled():
        logger.warning("AI worker disabled; set AI_WORKER_ENABLED=true to run it")
        return
    worker = AIWorker.from_environment()
    install_shutdown_handlers(worker, name="ai-worker")
    if once:
        if not worker.acquire():
            raise click.ClickException("AI worker lease is already held")
        try:
            worker.tick()
        finally:
            worker.close()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
