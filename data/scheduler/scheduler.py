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

    @staticmethod
    def _feature_enabled(key: str, default: bool = True) -> bool:
        """Read a process-wide safe fallback for scheduler-only features.

        The scheduler currently has no authenticated workspace context. Keep
        the global job opt-out explicit while workspace-scoped runs remain
        controlled by their API/UI settings.
        """
        import os

        raw = os.getenv(key, "")
        if not raw:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

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
        """同步 AI 信号覆盖池并刷新信号缓存。"""
        logger.info("=== 开始同步 AI 信号覆盖池 ===")
        try:
            summary = sync_qlib_daily(
                storage=self._storage,
                adapter=self._provider,
                generate_predictions_cache=True,
                min_success=2,
                status_source="scheduler",
            )
            logger.info(
                "AI 信号覆盖池同步完成: "
                f"成功 {summary.success_count}, 失败 {summary.fail_count}, "
                f"预测 {summary.prediction_total if summary.prediction_total is not None else 0}"
            )
        except Exception as exc:
            logger.error(f"AI 信号覆盖池同步失败: {exc}")

    def run_daily_research(self):
        """Run the optional daily intelligence workflow per workspace.

        Collection and notification remain inside their existing evidence and
        Outbox seams. A provider outage is recorded by the workflow and does
        not stop the ordinary market-data jobs.
        """
        if not self._feature_enabled("DAILY_RESEARCH_ENABLED", True):
            logger.info("每日投研已通过 DAILY_RESEARCH_ENABLED 关闭")
            return None
        try:
            import asyncio
            from agentic.daily_run import DailyResearchRunService
            from agentic.repository import DEFAULT_WORKSPACE_ID, AgenticRepository, normalize_workspace_id
            from config.settings import DB_DIR
            from data.evidence.store import SQLiteEvidenceStore
            from engine.events.outbox import SQLiteOutbox

            list_workspaces = getattr(self._storage, "get_all_watchlist_codes", None)
            if callable(list_workspaces):
                raw_workspaces = list_workspaces()
            else:
                # Keep older storage doubles and pre-workspace deployments
                # usable, but route this compatibility path to the explicit
                # default workspace instead of a shared global repository.
                raw_workspaces = [("", self._storage.get_watchlist())]

            workspace_watchlists: dict[str, list[str]] = {}
            for raw_workspace_id, codes in raw_workspaces or []:
                normalized_workspace_id = normalize_workspace_id(
                    raw_workspace_id or DEFAULT_WORKSPACE_ID
                )
                unique_codes = list(dict.fromkeys(str(code).strip() for code in (codes or []) if str(code).strip()))
                if unique_codes:
                    workspace_watchlists.setdefault(normalized_workspace_id, [])
                    workspace_watchlists[normalized_workspace_id].extend(unique_codes)

            for workspace_id, codes in workspace_watchlists.items():
                workspace_watchlists[workspace_id] = list(dict.fromkeys(codes))

            if not workspace_watchlists:
                logger.info("自选股为空，跳过每日投研")
                return None

            results = []
            for workspace_id, watchlist in sorted(workspace_watchlists.items()):
                service = DailyResearchRunService(
                    SQLiteEvidenceStore(DB_DIR / "evidence.db"),
                    AgenticRepository.for_workspace(workspace_id, base_dir=DB_DIR),
                    SQLiteOutbox(DB_DIR / "events.db"),
                    workspace_id=workspace_id,
                    owner=f"daily-research:{workspace_id}",
                )
                legacy_key = "daily:%s:%s" % (today_beijing_compact(), ",".join(sorted(watchlist)))
                run_key = (
                    legacy_key
                    if workspace_id == DEFAULT_WORKSPACE_ID
                    else f"workspace:{workspace_id}:{legacy_key}"
                )
                try:
                    result = asyncio.run(service.run(watchlist=watchlist, run_key=run_key))
                    results.append(result)
                    logger.info(
                        "每日投研完成: workspace=%s run_key=%s reports=%s",
                        workspace_id,
                        run_key,
                        result.brief.report_count,
                    )
                finally:
                    service.evidence_store.close()
                    service.outbox.close()
            return results
        except Exception as exc:
            logger.error(f"每日投研失败（不影响行情同步）: {exc}")
            return None

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
            name="每日 AI 信号覆盖池同步",
        )
        self._scheduler.add_job(
            self.run_daily_research,
            trigger=CronTrigger(hour=SYNC_HOUR, minute=(SYNC_MINUTE + 20) % 60, day_of_week="mon-fri"),
            id="daily_research",
            name="每日情报投研与日报",
        )
        self._scheduler.start()
        logger.info(f"后台调度器已启动，每个交易日 {SYNC_HOUR}:{SYNC_MINUTE:02d} 同步自选股和 AI 信号覆盖池")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("调度器已停止")
