"""因子动态更新调度器

按因子类型定时更新：
- 北向资金：交易时段每 15 分钟
- 板块轮动：交易时段每 30 分钟
- 新闻情绪：每 1 小时
- 宏观指标：每日 1 次

交易时段：09:30-11:30, 13:00-15:00
盘后：降低更新频率
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

from loguru import logger


# ── 更新间隔（秒）──

_INTERVALS_TRADING = {
    "northbound": 15 * 60,    # 15 分钟
    "sector": 30 * 60,        # 30 分钟
    "sentiment": 60 * 60,     # 1 小时
    "macro": 24 * 60 * 60,    # 每日
}

_INTERVALS_CLOSED = {
    "northbound": 60 * 60,    # 1 小时
    "sector": 60 * 60,        # 1 小时
    "sentiment": 2 * 60 * 60, # 2 小时
    "macro": 24 * 60 * 60,    # 每日
}


def _is_trading_time() -> bool:
    """判断当前是否为 A 股交易时段"""
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:  # 周末
        return False

    hour, minute = now.hour, now.minute
    t = hour * 100 + minute
    # 09:15-11:30, 13:00-15:00（含集合竞价）
    return (915 <= t <= 1130) or (1300 <= t <= 1500)


class FactorUpdateScheduler:
    """因子动态更新调度器

    使用后台线程按间隔调用各因子更新函数。
    交易时段高频、盘后低频。
    """

    def __init__(self):
        self._tasks: dict[str, Callable] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_update: dict[str, float] = {}

    def register(self, name: str, update_fn: Callable) -> None:
        """注册因子更新任务"""
        self._tasks[name] = update_fn
        self._last_update[name] = 0.0
        logger.info(f"注册因子更新任务: {name}")

    def start(self) -> None:
        """启动后台调度线程"""
        if self._thread and self._thread.is_alive():
            logger.warning("调度器已在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="factor-scheduler")
        self._thread.start()
        logger.info("因子更新调度器已启动")

    def stop(self) -> None:
        """停止调度器"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("因子更新调度器已停止")

    def _run(self) -> None:
        """调度主循环"""
        while not self._stop_event.is_set():
            intervals = _INTERVALS_TRADING if _is_trading_time() else _INTERVALS_CLOSED
            now = time.time()

            for name, update_fn in self._tasks.items():
                interval = intervals.get(name, 3600)
                last = self._last_update.get(name, 0)
                if now - last >= interval:
                    try:
                        update_fn()
                        self._last_update[name] = now
                        logger.debug(f"因子更新完成: {name}")
                    except Exception as e:
                        logger.warning(f"因子更新失败 {name}: {e}")

            # 每 60 秒检查一次
            self._stop_event.wait(timeout=60)

    def get_status(self) -> dict[str, dict]:
        """获取调度器状态"""
        intervals = _INTERVALS_TRADING if _is_trading_time() else _INTERVALS_CLOSED
        now = time.time()
        status = {}
        for name in self._tasks:
            last = self._last_update.get(name, 0)
            interval = intervals.get(name, 3600)
            elapsed = now - last
            status[name] = {
                "interval_seconds": interval,
                "last_update_ago": round(elapsed, 0),
                "next_update_in": max(0, round(interval - elapsed, 0)),
                "is_trading": _is_trading_time(),
            }
        return status


# 全局单例
_scheduler: FactorUpdateScheduler | None = None


def get_factor_scheduler() -> FactorUpdateScheduler:
    """获取全局因子调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = FactorUpdateScheduler()
    return _scheduler
