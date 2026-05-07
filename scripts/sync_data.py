"""数据同步入口"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from config.logging import setup_logging
from data.collector import StockCollector
from data.storage import DataStorage


@click.command()
@click.option("--codes", "-c", multiple=True, help="指定股票代码，不指定则同步全部")
@click.option("--start", "-s", default=None, help="起始日期 (YYYYMMDD)")
@click.option("--limit", "-l", default=0, type=int, help="最多同步N只股票（调试用）")
def sync(codes, start, limit):
    """同步日K线数据"""
    setup_logging()
    storage = DataStorage()
    collector = StockCollector()

    if codes:
        target_codes = list(codes)
    else:
        target_codes = storage.get_all_stock_codes()

    if limit > 0:
        target_codes = target_codes[:limit]

    if not target_codes:
        print("无股票可同步，请先运行 scripts/init_db.py")
        return

    print(f"=== 同步 {len(target_codes)} 只股票 ===")
    success = 0
    fail = 0
    for code in target_codes:
        try:
            latest = storage.get_latest_date(code)
            s = latest.strftime("%Y%m%d") if latest else start
            df = collector.get_stock_daily(code, start_date=s)
            if not df.empty:
                storage.save_stock_daily(code, df)
            success += 1
        except Exception as e:
            print(f"[{code}] 失败: {e}")
            fail += 1

    print(f"\n完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    sync()
