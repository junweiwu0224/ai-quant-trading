"""Run the isolated Pi Agent task worker without starting the Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from engine.ai_worker import PiAgentWorker, pi_agent_worker_enabled
from engine.worker_signals import install_shutdown_handlers


@click.command()
@click.option("--once", is_flag=True, help="Acquire the lease, process one batch and exit.")
def main(once: bool) -> None:
    """Start only when Pi Agent execution is explicitly enabled."""

    setup_logging()
    if not pi_agent_worker_enabled():
        logger.warning("Pi Agent worker disabled; set PI_AGENT_WORKER_ENABLED=true to run it")
        return
    worker = PiAgentWorker.from_environment()
    install_shutdown_handlers(worker, name="pi-agent")
    if once:
        if not worker.acquire():
            raise click.ClickException("Pi Agent worker lease is already held")
        try:
            worker.tick()
        finally:
            worker.close()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
