"""风控模块测试"""
from datetime import date

import pytest

from risk.position import PositionLimit, PositionManager
from risk.stoploss import StopLossConfig, StopLossManager, StopSignal
from risk.monitor import AlertLevel, RiskMonitor
from strategy.base import Portfolio


@pytest.fixture
def portfolio():
    """初始投资组合"""
    return Portfolio(cash=1_000_000.0)


@pytest.fixture
def prices():
    """股票价格"""
    return {"000001": 10.0, "000002": 20.0, "600519": 1800.0}


# ── 仓位管理测试 ──

class TestPositionManager:
    def test_check_buy_pass(self, portfolio, prices):
        mgr = PositionManager()
        ok, reason = mgr.check_buy("000001", 10.0, 100, portfolio, prices)
        assert ok is True

    def test_check_buy_below_min_volume(self, portfolio, prices):
        mgr = PositionManager()
        ok, reason = mgr.check_buy("000001", 10.0, 50, portfolio, prices)
        assert ok is False
        assert "最小单位" in reason

    def test_check_buy_not_lot_multiple(self, portfolio, prices):
        mgr = PositionManager()
        ok, reason = mgr.check_buy("000001", 10.0, 150, portfolio, prices)
        assert ok is False
        assert "整数倍" in reason

    def test_check_buy_exceeds_single_limit(self, portfolio, prices):
        mgr = PositionManager()
        # 20% of 1M = 200K, at 10/share = 20000 shares = 200 lots
        ok, reason = mgr.check_buy("000001", 10.0, 20100, portfolio, prices)
        assert ok is False
        assert "单票仓位" in reason

    def test_check_buy_with_existing_position(self, portfolio, prices):
        portfolio.positions["000001"] = 10000  # 已持有 10000 股 = 100K
        portfolio.cash = 900_000
        # 总权益 = 900K + 100K = 1M, 20% = 200K, 再买 5000 股 = 50K, 总计 150K = 15%
        mgr = PositionManager()
        ok, reason = mgr.check_buy("000001", 10.0, 5000, portfolio, prices)
        assert ok is True

    def test_check_buy_industry_concentration(self, portfolio, prices):
        industry_map = {"000001": "银行", "000002": "银行"}
        portfolio.positions["000002"] = 15000  # 300K in 银行
        portfolio.cash = 700_000
        mgr = PositionManager()
        # 买 20000 股 000001 = 200K, 银行总计 500K, 总权益 1M, 占比 50% > 40%
        ok, reason = mgr.check_buy("000001", 10.0, 20000, portfolio, prices, industry_map)
        assert ok is False
        assert "行业" in reason

    def test_check_buy_max_positions(self, portfolio, prices):
        limit = PositionLimit(max_total_positions=2)
        mgr = PositionManager(limit)
        portfolio.positions = {"000001": 100, "000002": 100}
        # 第三个新持仓应被拒绝
        ok, reason = mgr.check_buy("600519", 1800.0, 100, portfolio, prices)
        assert ok is False
        assert "持仓数" in reason

    def test_check_buy_existing_position_not_counted(self, portfolio, prices):
        limit = PositionLimit(max_total_positions=2)
        mgr = PositionManager(limit)
        portfolio.positions = {"000001": 100, "000002": 100}
        # 加仓已有持仓，不受持仓数限制
        ok, reason = mgr.check_buy("000001", 10.0, 100, portfolio, prices)
        assert ok is True

    def test_calc_max_volume(self, portfolio, prices):
        mgr = PositionManager()
        max_vol = mgr.calc_max_volume("000001", 10.0, portfolio, prices)
        # 20% of 1M = 200K / 10 = 20000 shares
        assert max_vol == 20000

    def test_calc_max_volume_with_existing(self, portfolio, prices):
        portfolio.positions["000001"] = 10000
        portfolio.cash = 900_000
        mgr = PositionManager()
        max_vol = mgr.calc_max_volume("000001", 10.0, portfolio, prices)
        # 总权益 ~1M, 20% = 200K, 已占 100K, 可买 100K/10 = 10000
        assert max_vol == 10000

    def test_calc_volatility_position(self):
        mgr = PositionManager()
        # ATR=0.5, price=10, equity=1M, risk=1% => risk=10000/0.5=20000
        vol = mgr.calc_volatility_position(10.0, 0.5, 1_000_000, 0.01)
        assert vol == 20000

    def test_calc_volatility_position_zero_atr(self):
        mgr = PositionManager()
        vol = mgr.calc_volatility_position(10.0, 0.0, 1_000_000)
        assert vol == 0


# ── 止损止盈测试 ──

class TestStopLossManager:
    def test_max_drawdown_triggered(self):
        mgr = StopLossManager()
        # 设置峰值
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        # 回撤 16% > 15% 阈值
        signal = mgr.check_max_drawdown(840_000)
        assert signal is not None
        assert signal.code == "*"
        assert signal.action == "sell"
        assert "最大回撤" in signal.reason

    def test_max_drawdown_not_triggered(self):
        mgr = StopLossManager()
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        signal = mgr.check_max_drawdown(900_000)
        assert signal is None

    def test_daily_loss_triggered(self):
        mgr = StopLossManager()
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        # 日亏损 4% > 3% 阈值
        signal = mgr.check_daily_loss(960_000)
        assert signal is not None
        assert "日亏损" in signal.reason

    def test_daily_loss_not_triggered(self):
        mgr = StopLossManager()
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        signal = mgr.check_daily_loss(980_000)
        assert signal is None

    def test_atr_stop_triggered(self):
        mgr = StopLossManager()
        # entry=10, atr=0.5, stop=10-2*0.5=9.0, current=8.8
        signal = mgr.check_atr_stop("000001", 10.0, 8.8, 0.5)
        assert signal is not None
        assert signal.code == "000001"
        assert "ATR" in signal.reason

    def test_atr_stop_not_triggered(self):
        mgr = StopLossManager()
        signal = mgr.check_atr_stop("000001", 10.0, 9.5, 0.5)
        assert signal is None

    def test_trailing_stop_triggered(self):
        mgr = StopLossManager()
        # 模拟价格上涨到 12，然后回落到 11（回撤 8.3% > 8%）
        mgr.check_trailing_stop("000001", 10.0, 12.0)  # 记录高点 12
        signal = mgr.check_trailing_stop("000001", 10.0, 11.0)  # 回撤
        assert signal is not None
        assert "追踪止损" in signal.reason

    def test_trailing_stop_not_triggered(self):
        mgr = StopLossManager()
        mgr.check_trailing_stop("000001", 10.0, 12.0)
        signal = mgr.check_trailing_stop("000001", 10.0, 11.5)
        assert signal is None

    def test_trailing_stop_no_signal_when_losing(self):
        mgr = StopLossManager()
        signal = mgr.check_trailing_stop("000001", 10.0, 9.0)
        assert signal is None

    def test_fixed_stop_triggered(self):
        mgr = StopLossManager()
        # 亏损 6% > 5% 阈值
        signal = mgr.check_fixed_stop("000001", 10.0, 9.4)
        assert signal is not None
        assert "固定止损" in signal.reason

    def test_take_profit_triggered(self):
        mgr = StopLossManager()
        # 盈利 25% > 20% 阈值
        signal = mgr.check_take_profit("000001", 10.0, 12.5)
        assert signal is not None
        assert "止盈" in signal.reason

    def test_check_all_returns_sorted_signals(self):
        mgr = StopLossManager()
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        # 触发多个信号：回撤 + 固定止损
        signals = mgr.check_all("000001", 10.0, 9.0, 840_000)
        assert len(signals) >= 2
        # 按 urgency 排序
        for i in range(len(signals) - 1):
            assert signals[i].urgency <= signals[i + 1].urgency

    def test_clear_trailing_high(self):
        mgr = StopLossManager()
        mgr.check_trailing_stop("000001", 10.0, 15.0)
        mgr.clear_trailing_high("000001")
        # 清除后，重新跟踪
        signal = mgr.check_trailing_stop("000001", 10.0, 13.0)
        # 13 成为新高点，不应触发
        assert signal is None

    def test_update_equity_daily_reset(self):
        mgr = StopLossManager(StopLossConfig(daily_loss_limit_pct=0.03))
        mgr.update_equity(date(2024, 1, 1), 1_000_000)
        # 同一天更新，日起始权益不变
        mgr.update_equity(date(2024, 1, 1), 970_000)
        # 日亏损 3% 正好触发
        signal = mgr.check_daily_loss(970_000)
        assert signal is not None
        assert "日亏损" in signal.reason

        # 切换到新一天，日起始权益重置为 970K
        mgr.update_equity(date(2024, 1, 2), 970_000)
        signal = mgr.check_daily_loss(960_000)
        assert signal is None  # 1% < 3%


# ── 风险监控测试 ──

class TestRiskMonitor:
    def test_snapshot_basic(self, portfolio, prices):
        monitor = RiskMonitor()
        metrics = monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        assert metrics.total_equity == 1_000_000
        assert metrics.cash == 1_000_000
        assert metrics.market_value == 0
        assert metrics.position_count == 0
        assert metrics.max_single_pct == 0
        assert metrics.cash_pct == 1.0

    def test_snapshot_with_positions(self, portfolio, prices):
        portfolio.positions = {"000001": 5000}
        portfolio.cash = 950_000
        monitor = RiskMonitor()
        metrics = monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        assert metrics.position_count == 1
        assert metrics.max_single_pct == pytest.approx(0.05, abs=0.01)
        assert metrics.market_value == 50_000

    def test_snapshot_drawdown(self, portfolio, prices):
        monitor = RiskMonitor()
        # Day 1: 1M
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)
        # Day 2: 900K
        portfolio.cash = 900_000
        metrics = monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        assert metrics.drawdown_pct == pytest.approx(0.10, abs=0.01)

    def test_snapshot_industry_concentration(self, portfolio, prices):
        # 000001: 5000*10=50K, 000002: 5000*20=100K, total mv=150K
        # total equity = 900K + 150K = 1050K
        # 银行占比 = 150K / 1050K ≈ 14.3%
        portfolio.positions = {"000001": 5000, "000002": 5000}
        portfolio.cash = 900_000
        industry_map = {"000001": "银行", "000002": "银行"}
        monitor = RiskMonitor()
        metrics = monitor.snapshot(date(2024, 1, 2), portfolio, prices, industry_map)

        assert "银行" in metrics.industry_concentration
        assert metrics.industry_concentration["银行"] == pytest.approx(150_000 / 1_050_000, abs=0.01)

    def test_alert_drawdown_warning(self, portfolio, prices):
        monitor = RiskMonitor(drawdown_warn_pct=0.10)
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)
        portfolio.cash = 890_000
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        alerts = monitor.alerts
        assert any(a.category == "回撤" for a in alerts)

    def test_alert_daily_loss_warning(self, portfolio, prices):
        monitor = RiskMonitor(daily_loss_warn_pct=0.02)
        # 同一天内：日起始 1M，当前 970K = 日亏损 3%
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)
        portfolio.cash = 970_000
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)

        alerts = monitor.alerts
        assert any(a.category == "日亏损" for a in alerts)

    def test_alert_single_position_warning(self, portfolio, prices):
        portfolio.positions = {"600519": 100}  # 180K
        portfolio.cash = 820_000
        monitor = RiskMonitor(single_position_warn_pct=0.15)
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        alerts = monitor.alerts
        assert any(a.category == "单票集中" for a in alerts)

    def test_alert_cash_warning(self, portfolio, prices):
        portfolio.positions = {"600519": 50}  # 90K
        portfolio.cash = 90_000  # Only 9% cash of ~1M... wait total=90K+90K=180K?
        # Let me recalculate: 50*1800=90K + 90K cash = 180K total, cash=90K/180K=50%
        # That's not right. Let me use bigger position
        portfolio.positions = {"600519": 500}  # 900K
        portfolio.cash = 90_000  # 90K cash, total = 990K, cash% = 9.1%
        monitor = RiskMonitor(cash_warn_pct=0.10)
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)

        alerts = monitor.alerts
        assert any(a.category == "现金不足" for a in alerts)

    def test_alert_dedup(self, portfolio, prices):
        monitor = RiskMonitor(drawdown_warn_pct=0.10)
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)
        portfolio.cash = 890_000
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)  # 同日重复

        drawdown_alerts = [a for a in monitor.alerts if a.category == "回撤"]
        assert len(drawdown_alerts) == 1

    def test_clear_alerts(self, portfolio, prices):
        monitor = RiskMonitor(drawdown_warn_pct=0.10)
        monitor.snapshot(date(2024, 1, 1), portfolio, prices)
        portfolio.cash = 890_000
        monitor.snapshot(date(2024, 1, 2), portfolio, prices)
        assert len(monitor.alerts) > 0

        monitor.clear_alerts()
        assert len(monitor.alerts) == 0
