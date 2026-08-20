"""Run the PaperWorker consumer without starting the Dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.logging import setup_logging
from config.settings import DB_DIR
from engine.paper_worker import PaperWorker, PaperWorkerConfig


@click.command()
@click.option("--operations-db", type=click.Path(path_type=Path), default=DB_DIR / "operations.db")
@click.option("--paper-db", type=click.Path(path_type=Path), default=DB_DIR / "paper_trading.db")
@click.option("--lease-db", type=click.Path(path_type=Path), default=DB_DIR / "worker_leases.db")
@click.option("--poll-interval", type=float, default=2.0)
def main(operations_db: Path, paper_db: Path, lease_db: Path, poll_interval: float) -> None:
    """Start the sole Paper execution owner."""
    setup_logging()
    worker = PaperWorker(PaperWorkerConfig(operations_db=operations_db, paper_db=paper_db, lease_db=lease_db, poll_interval_seconds=poll_interval))
    worker.start()


if __name__ == "__main__":
    main()
