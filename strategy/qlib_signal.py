"""qlib ML 信号策略

从 qlib 推理服务或本地缓存读取预测分数，生成交易信号。

使用方式（回测）:
    strategy = QlibSignalStrategy(
        predictions={"000001": 0.73, "600519": -0.21},
        buy_threshold=0.5,
        sell_threshold=-0.3,
    )

使用方式（实盘，从 qlib 服务加载）:
    strategy = QlibSignalStrategy.from_service(
        service_url=QLIB_SERVICE_URL,
        buy_threshold=0.5,
    )
"""

import json
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import QLIB_SERVICE_URL
from strategy.base import Bar, BaseStrategy, Direction, Trade


class QlibSignalStrategy(BaseStrategy):
    """基于 qlib ML 预测分数的交易策略

    两种模式:
    1. absolute（默认）: score > buy_threshold → 买入, score < sell_threshold → 卖出
    2. ranking: 每日按分数排名，买入 top_n 只股票，卖出排名跌出的股票

    predictions 格式:
    - 单日: {"000001": 0.73, "600519": -0.21}
    - 多日: {"2026-03-01": {"000001": 0.73}, "2026-03-02": {...}}
    """

    def __init__(
        self,
        predictions: dict[str, float] | dict[str, dict[str, float]] | None = None,
        buy_threshold: float = 0.5,
        sell_threshold: float = -0.3,
        position_pct: float = 0.9,
        score_normalize: bool = True,
        mode: str = "absolute",
        top_n: int = 3,
    ):
        super().__init__()
        predictions = predictions or {}
        # 判断是多日格式还是单日格式
        if predictions and isinstance(next(iter(predictions.values()), None), dict):
            self._daily_predictions = predictions  # {date: {code: score}}
        else:
            self._daily_predictions = {"__single__": predictions}
        self._buy_threshold = buy_threshold
        self._sell_threshold = sell_threshold
        self._position_pct = position_pct
        self._score_normalize = score_normalize
        self._holding = False
        self._mode = mode
        self._top_n = top_n

        # 滚动分位数归一化窗口
        self._score_history: list[float] = []
        self._normalize_window = 60

        # ranking 模式：按日缓存 bar，日期变化时统一处理
        self._pending_bars: dict[str, Bar] = {}  # code → bar
        self._current_date = None

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    @staticmethod
    def _strip_prefix(code: str) -> str:
        """去掉 sh/sz 前缀，统一为纯数字代码"""
        if code[:2] in ("sh", "sz", "SH", "SZ"):
            return code[2:]
        return code

    def _get_score(self, code: str, date) -> float | None:
        """按日期获取预测分数（兼容带前缀和不带前缀的代码）"""
        raw_code = self._strip_prefix(code)
        if "__single__" in self._daily_predictions:
            return self._daily_predictions["__single__"].get(raw_code)
        # 统一转为字符串比较
        date_str = str(date)[:10]
        if date_str in self._daily_predictions:
            return self._daily_predictions[date_str].get(raw_code)
        available = sorted(d for d in self._daily_predictions if d <= date_str)
        if available:
            return self._daily_predictions[available[-1]].get(raw_code)
        return None

    def on_bar(self, bar: Bar):
        if self._mode == "ranking":
            self._on_bar_ranking(bar)
        else:
            self._on_bar_absolute(bar)

    def _on_bar_absolute(self, bar: Bar):
        """绝对阈值模式"""
        raw_score = self._get_score(bar.code, bar.date)
        if raw_score is None:
            return

        # 分位数归一化（可选）
        if self._score_normalize:
            score = self._normalize_score(raw_score)
        else:
            score = raw_score

        if not self._holding and score >= self._buy_threshold:
            volume = int(self.portfolio.cash * self._position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and score <= self._sell_threshold:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)

    def _on_bar_ranking(self, bar: Bar):
        """截面排名模式：积累当日所有 bar，日期变化时统一排名决策"""
        bar_date = str(bar.date)

        # 日期变化 → 处理前一天的排名
        if self._current_date is not None and bar_date != self._current_date:
            self._process_ranking()

        self._current_date = bar_date
        self._pending_bars[bar.code] = bar

    def _process_ranking(self):
        """对积累的 bar 按预测分数排名，执行买入/卖出"""
        if not self._pending_bars:
            return

        # 收集所有有分数的 bar
        scored: list[tuple[str, float, Bar]] = []
        for code, bar in self._pending_bars.items():
            score = self._get_score(bar.code, bar.date)
            if score is not None:
                scored.append((code, score, bar))

        if not scored:
            self._pending_bars.clear()
            return

        # 按分数降序排名
        scored.sort(key=lambda x: x[1], reverse=True)
        top_codes = {code for code, _, _ in scored[: self._top_n]}

        # 卖出：持仓中不在 top_n 的股票
        for code, _, bar in scored:
            pos = self.portfolio.get_position(code)
            if pos > 0 and code not in top_codes:
                self.sell(code, bar.close, pos)

        # 买入：top_n 中未持仓的股票（等权分配）
        held_codes = {code for code, _ in self.portfolio.positions.items() if self.portfolio.get_position(code) > 0}
        to_buy = [item for item in scored[: self._top_n] if item[0] not in held_codes]

        if to_buy:
            budget_per_stock = self.portfolio.cash * self._position_pct / len(to_buy)
            for code, _, bar in to_buy:
                volume = int(budget_per_stock / bar.close / 100) * 100
                if volume >= 100:
                    self.buy(code, bar.close, volume)

        self._pending_bars.clear()

    def flush(self):
        """处理最后一天的排名（回测结束时调用）"""
        if self._mode == "ranking" and self._pending_bars:
            self._process_ranking()

    def _normalize_score(self, raw_score: float) -> float:
        """滚动分位数归一化

        将原始分数转换为滚动窗口内的百分位数 (0-1)
        避免不同市场环境下分数分布偏移导致的误判
        """
        self._score_history.append(raw_score)

        if len(self._score_history) < 10:
            # 样本不足，直接返回原始分数
            return raw_score

        window = self._score_history[-self._normalize_window:]
        sorted_window = sorted(window)
        rank = sum(1 for s in sorted_window if s <= raw_score)
        return rank / len(sorted_window)

    @classmethod
    def from_service(
        cls,
        service_url: str = QLIB_SERVICE_URL,
        date: str = "",
        **kwargs,
    ) -> "QlibSignalStrategy":
        """从 qlib 推理服务加载预测分数

        Args:
            service_url: qlib 微服务地址
            date: 日期，空则取最新
            **kwargs: 传递给 QlibSignalStrategy 的其他参数
        """
        import urllib.request
        import urllib.error

        url = f"{service_url}/predict"
        if date:
            url += f"?date={date}"

        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            predictions = data.get("predictions", {})
            logger.info(f"从 qlib 服务加载 {len(predictions)} 只股票预测")
            return cls(predictions=predictions, **kwargs)
        except urllib.error.URLError as e:
            logger.warning(f"qlib 服务不可用: {e}")
            return cls(predictions={}, **kwargs)

    @classmethod
    def from_cache_file(
        cls,
        cache_path: str | Path,
        date: str = "",
        **kwargs,
    ) -> "QlibSignalStrategy":
        """从本地缓存文件加载预测分数

        Args:
            cache_path: predictions_cache.json 路径
            date: 日期，空则取最新
            **kwargs: 传递给 QlibSignalStrategy 的其他参数
        """
        cache_path = Path(cache_path)
        if not cache_path.exists():
            logger.warning(f"缓存文件不存在: {cache_path}")
            return cls(predictions={}, **kwargs)

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        preds = data.get("predictions", {})

        if date:
            predictions = preds.get(date, {})
        else:
            latest = max(preds.keys()) if preds else ""
            predictions = preds.get(latest, {})

        logger.info(f"从缓存加载 {len(predictions)} 只股票预测 (日期: {latest if not date else date})")
        return cls(predictions=predictions, **kwargs)
