"""定时数据同步调度"""
import asyncio

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.datetime_utils import today_beijing_compact
from config.settings import SYNC_HOUR, SYNC_MINUTE
from data.collector import StockCollector
from data.collector.data_source import DataSource
from data.providers.astock_data_adapter import AStockDataAdapter
from data.qlib.daily_sync import sync_qlib_daily
from data.storage import DataStorage
from data.sync.full_stock_daily import sync_full_stock_daily


class DataScheduler:
    """数据同步调度器（后台线程运行）"""

    def __init__(
        self,
        storage: DataStorage | None = None,
        collector: StockCollector | None = None,
        provider: DataSource | None = None,
    ):
        self._storage = storage or DataStorage()
        self._collector = collector or StockCollector()
        self._provider = provider or AStockDataAdapter()
        self._scheduler = BackgroundScheduler()

    def _fetch_daily(self, code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        try:
            df = asyncio.run(self._provider.get_kline(code, frequency=9, start=0, offset=800))
            if df is not None and not df.empty:
                out = df.copy()
                if "date" not in out.columns and "datetime" in out.columns:
                    out = out.rename(columns={"datetime": "date"})
                out["date"] = pd.to_datetime(out["date"])
                if start_date:
                    out = out[out["date"] >= pd.Timestamp(start_date)]
                if end_date:
                    out = out[out["date"] <= pd.Timestamp(end_date)]
                for col in ("open", "high", "low", "close", "volume", "amount"):
                    if col not in out.columns:
                        out[col] = 0
                if "adj_factor" not in out.columns:
                    out["adj_factor"] = 1.0
                return out[["date", "open", "high", "low", "close", "volume", "amount", "adj_factor"]]
        except Exception as exc:
            logger.debug(f"[{code}] provider 日K同步失败，回退 StockCollector: {exc}")

        if end_date is not None:
            return self._collector.get_stock_daily(code, start_date=start_date or "20200101", end_date=end_date)
        return self._collector.get_stock_daily(code, start_date=start_date)

    def sync_watchlist(self):
        """只同步自选股的日K数据"""
        workspace_watchlists = self._storage.get_all_watchlist_codes()
        if not workspace_watchlists:
            logger.info("自选股为空，跳过同步")
            return

        total_codes = sum(len(codes) for _, codes in workspace_watchlists)
        logger.info(f"=== 开始同步自选股（{total_codes} 只，{len(workspace_watchlists)} 个工作区）===")
        success, fail = 0, 0
        for workspace_id, codes in workspace_watchlists:
            for code in codes:
                try:
                    latest = self._storage.get_latest_date(code)
                    start = latest.strftime("%Y%m%d") if latest else "20200101"
                    end = today_beijing_compact()
                    df = self._fetch_daily(code, start_date=start, end_date=end)
                    if not df.empty:
                        self._storage.save_stock_daily(code, df)
                    success += 1
                except Exception as e:
                    logger.error(f"[{workspace_id or 'default'}:{code}] 同步失败: {e}")
                    fail += 1

        logger.info(f"自选股同步完成: 成功 {success}, 失败 {fail}, 共 {total_codes}")

    def sync_all(self):
        """同步所有已知股票的日K数据（手动触发用）"""
        logger.info("=== 开始全量数据同步 ===")
        summary = sync_full_stock_daily(storage=self._storage)
        logger.info(
            "全量同步完成: "
            f"成功 {summary.success_count}, 失败 {summary.fail_count}, 共 {summary.target_count}, "
            f"覆盖 {summary.coverage.get('daily_covered')}/{summary.coverage.get('stock_count')}"
        )
        return summary

    def sync_qlib_coverage(self):
        """同步 Qlib 覆盖池并刷新预测缓存。"""
        logger.info("=== 开始同步 Qlib 覆盖池 ===")
        try:
            summary = sync_qlib_daily(
                storage=self._storage,
                adapter=self._provider,
                generate_predictions_cache=True,
                min_success=2,
                status_source="scheduler",
            )
            logger.info(
                "Qlib 覆盖池同步完成: "
                f"成功 {summary.success_count}, 失败 {summary.fail_count}, "
                f"预测 {summary.prediction_total if summary.prediction_total is not None else 0}"
            )
        except Exception as exc:
            logger.error(f"Qlib 覆盖池同步失败: {exc}")

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
        self._scheduler.add_job(
            self.sync_qlib_coverage,
            trigger=CronTrigger(hour=SYNC_HOUR, minute=(SYNC_MINUTE + 10) % 60, day_of_week="mon-fri"),
            id="qlib_daily_sync",
            name="每日 Qlib 覆盖池同步",
        )
        self._scheduler.start()
        logger.info(f"后台调度器已启动，每个交易日 {SYNC_HOUR}:{SYNC_MINUTE:02d} 同步自选股和 Qlib 覆盖池")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("调度器已停止")
