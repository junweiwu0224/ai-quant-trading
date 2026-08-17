"""Run the standalone decision worker without starting the Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from engine.decision_worker import DecisionWorker, feature_enabled
from engine.worker_signals import install_shutdown_handlers


@click.command()
@click.option("--once", is_flag=True, help="Acquire the lease, run one tick and exit.")
def main(once: bool) -> None:
    """Start only when DECISION_WORKER_ENABLED is explicitly enabled."""

    setup_logging()
    if not feature_enabled("DECISION_WORKER_ENABLED"):
        logger.warning("Decision worker disabled; set DECISION_WORKER_ENABLED=true to run it")
        return
    worker = DecisionWorker.from_environment()
    install_shutdown_handlers(worker, name="decision-worker")
    if once:
        if not worker.acquire():
            raise click.ClickException("decision worker lease is already held")
        try:
            worker.tick()
        finally:
            worker.close()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
