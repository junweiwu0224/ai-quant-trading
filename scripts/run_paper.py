"""
Paper Trading CLI - V2 command-based (enqueue-only)

V2: CLI 不再直接启动 PaperEngine，改为提交命令到 OperationsStore。
实际执行由 PaperWorker 消费命令完成。
"""
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from engine.paper_commands import PaperCommandClient
from config.settings import DB_DIR


def main():
    """Submit a paper_start command instead of running engine directly."""
    # V2: Parse args and enqueue command
    import argparse
    parser = argparse.ArgumentParser(description="Submit Paper trading command (V2)")
    parser.add_argument("--strategy", default="dual_ma", help="Strategy name")
    parser.add_argument("--codes", required=True, help="Comma-separated stock codes")
    parser.add_argument("--interval", type=int, default=30, help="Interval in seconds")
    parser.add_argument("--cash", type=float, default=50_000, help="Initial cash")
    parser.add_argument("--account-id", default="paper-default", help="Account ID")
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    if not codes:
        print("Error: No valid stock codes provided")
        sys.exit(1)

    print(f"V2: Enqueueing paper_start command...")
    print(f"  Account: {args.account_id}")
    print(f"  Strategy: {args.strategy}")
    print(f"  Codes: {codes}")
    print(f"  Interval: {args.interval}s")
    print(f"  Cash: {args.cash}")

    client = PaperCommandClient(DB_DIR / "operations.db")
    try:
        acceptance = client.enqueue_start(
            account_id=args.account_id,
            strategy_name=args.strategy,
            codes=codes,
            interval_seconds=args.interval,
            initial_cash=args.cash,
        )
        print(f"\n✓ Command enqueued:")
        print(f"  Command ID: {acceptance.command.id}")
        print(f"  Task ID: {acceptance.task.id}")
        print(f"  Status: {acceptance.task.status}")
        print(f"\nPaperWorker will consume this command.")
        print(f"Check task status via OperationsStore or Dashboard.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
