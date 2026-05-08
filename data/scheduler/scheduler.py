"""定时数据同步调度"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.settings import SYNC_HOUR, SYNC_MINUTE
from data.collector import StockCollector
from data.storage import DataStorage


class DataScheduler:
    """数据同步调度器（后台线程运行）"""

    def __init__(self):
        self._storage = DataStorage()
        self._collector = StockCollector()
        self._scheduler = BackgroundScheduler()

    def sync_watchlist(self):
        """只同步自选股的日K数据"""
        from datetime import datetime
        codes = self._storage.get_watchlist()
        if not codes:
            logger.info("自选股为空，跳过同步")
            return

        logger.info(f"=== 开始同步自选股（{len(codes)} 只）===")
        success, fail = 0, 0
        for code in codes:
            try:
                latest = self._storage.get_latest_date(code)
                start = latest.strftime("%Y%m%d") if latest else "20200101"
                end = today_beijing_compact()
                df = self._collector.get_stock_daily(code, start_date=start, end_date=end)
                if not df.empty:
                    self._storage.save_stock_daily(code, df)
                success += 1
            except Exception as e:
                logger.error(f"[{code}] 同步失败: {e}")
                fail += 1

        logger.info(f"自选股同步完成: 成功 {success}, 失败 {fail}, 共 {len(codes)}")

    def sync_all(self):
        """同步所有已知股票的日K数据（手动触发用）"""
        logger.info("=== 开始全量数据同步 ===")
        codes = self._storage.get_all_stock_codes()
        if not codes:
            logger.warning("数据库中无股票信息，请先运行 init_db 初始化")
            return

        success, fail = 0, 0
        for code in codes:
            try:
                latest = self._storage.get_latest_date(code)
                start = latest.strftime("%Y%m%d") if latest else None
                df = self._collector.get_stock_daily(code, start_date=start)
                if not df.empty:
                    self._storage.save_stock_daily(code, df)
                success += 1
            except Exception as e:
                logger.error(f"[{code}] 同步失败: {e}")
                fail += 1

        logger.info(f"全量同步完成: 成功 {success}, 失败 {fail}, 共 {len(codes)}")

    def start(self):
        """启动后台定时调度（非阻塞）"""
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self.sync_watchlist,
            trigger=CronTrigger(hour=SYNC_HOUR, minute=SYNC_MINUTE, day_of_week="mon-fri"),
            id="daily_sync",
            name="每日自选股同步",
        )
        self._scheduler.start()
        logger.info(f"后台调度器已启动，每个交易日 {SYNC_HOUR}:{SYNC_MINUTE:02d} 同步自选股")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("调度器已停止")
