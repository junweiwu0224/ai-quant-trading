"""初始化数据库并采集股票列表"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging import setup_logging
from data.collector import StockCollector
from data.storage import DataStorage


def main():
    setup_logging()
    storage = DataStorage()
    collector = StockCollector()

    print("=== 初始化数据库 ===")
    storage.init_db()

    print("=== 采集 A股股票列表 ===")
    stock_list = collector.get_stock_list()
    count = storage.save_stock_info(stock_list)
    print(f"完成: 写入 {count} 只股票信息")

    codes = storage.get_all_stock_codes()
    print(f"数据库中共有 {len(codes)} 只股票")


if __name__ == "__main__":
    main()
