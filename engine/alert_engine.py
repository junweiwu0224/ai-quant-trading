"""预警规则引擎

支持条件：
- 价格突破/跌破
- 涨跌幅阈值
- 放量异动（量比/换手率）
- 振幅阈值

防重复触发：同一规则 + 同一股票，冷却期内不重复触发。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


# ── 规则定义 ──

@dataclass(frozen=True)
class AlertRule:
    """预警规则"""
    id: int
    code: str
    condition: str   # price_above, price_below, change_above, change_below,
                     # volume_ratio_above, turnover_above, amplitude_above
    threshold: float
    enabled: bool = True
    name: str = ""
    cooldown: int = 300  # 冷却秒数，默认 5 分钟


@dataclass
class Alert:
    """触发的预警"""
    rule_id: int
    code: str
    name: str
    condition: str
    threshold: float
    current_value: float
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "code": self.code,
            "name": self.name,
            "condition": self.condition,
            "threshold": self.threshold,
            "current_value": round(self.current_value, 2),
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ── 条件检查器 ──

_CONDITION_MAP = {
    "price_above": lambda val, th: val > th,
    "price_below": lambda val, th: val < th,
    "change_above": lambda val, th: val > th,
    "change_below": lambda val, th: val < th,
    "volume_ratio_above": lambda val, th: val > th,
    "turnover_above": lambda val, th: val > th,
    "amplitude_above": lambda val, th: val > th,
}

_VALUE_EXTRACTORS = {
    "price_above": lambda q: q.price,
    "price_below": lambda q: q.price,
    "change_above": lambda q: q.change_pct,
    "change_below": lambda q: q.change_pct,
    "volume_ratio_above": lambda q: q.volume_ratio,
    "turnover_above": lambda q: q.turnover_rate,
    "amplitude_above": lambda q: q.amplitude,
}

_CONDITION_LABELS = {
    "price_above": "价格突破",
    "price_below": "价格跌破",
    "change_above": "涨幅超过",
    "change_below": "跌幅超过",
    "volume_ratio_above": "量比超过",
    "turnover_above": "换手率超过",
    "amplitude_above": "振幅超过",
}


# ── 预警引擎 ──

class AlertEngine:
    """预警规则引擎"""

    def __init__(self):
        self._rules: list[AlertRule] = []
        self._cooldown_map: dict[str, float] = {}  # "rule_id:code" -> last_trigger_ts
        self._triggered: list[Alert] = []

    def set_rules(self, rules: list[AlertRule]):
        """设置规则列表"""
        self._rules = [r for r in rules if r.enabled]
        logger.info(f"预警规则已更新: {len(self._rules)} 条生效")

    def add_rule(self, rule: AlertRule):
        """添加单条规则"""
        self._rules = [r for r in self._rules if r.id != rule.id]
        if rule.enabled:
            self._rules.append(rule)

    def remove_rule(self, rule_id: int):
        """移除规则"""
        self._rules = [r for r in self._rules if r.id != rule_id]

    def check(self, quotes: dict) -> list[Alert]:
        """检查所有规则，返回触发的预警列表

        Args:
            quotes: {code: QuoteData} 或 {code: dict}
        """
        now = time.time()
        alerts = []

        for rule in self._rules:
            quote = quotes.get(rule.code)
            if quote is None:
                continue

            # 获取当前值
            extractor = _VALUE_EXTRACTORS.get(rule.condition)
            if not extractor:
                continue

            try:
                current_val = extractor(quote)
            except (AttributeError, TypeError):
                continue

            if current_val is None:
                continue

            # 检查条件
            checker = _CONDITION_MAP.get(rule.condition)
            if not checker or not checker(current_val, rule.threshold):
                continue

            # 冷却检查
            cd_key = f"{rule.id}:{rule.code}"
            last_trigger = self._cooldown_map.get(cd_key, 0)
            if now - last_trigger < rule.cooldown:
                continue

            # 触发预警
            self._cooldown_map[cd_key] = now
            label = _CONDITION_LABELS.get(rule.condition, rule.condition)
            name = getattr(quote, "name", "") if hasattr(quote, "name") else ""

            alert = Alert(
                rule_id=rule.id,
                code=rule.code,
                name=name or rule.code,
                condition=rule.condition,
                threshold=rule.threshold,
                current_value=current_val,
                message=f"{name or rule.code} {label} {rule.threshold}，当前 {current_val:.2f}",
            )
            alerts.append(alert)
            self._triggered.append(alert)

        if alerts:
            logger.info(f"触发 {len(alerts)} 条预警")

        return alerts

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """获取最近触发的预警"""
        return [a.to_dict() for a in self._triggered[-limit:]]

    def clear_history(self):
        """清空触发历史"""
        self._triggered.clear()

    @staticmethod
    def get_condition_labels() -> dict[str, str]:
        """获取条件类型映射"""
        return dict(_CONDITION_LABELS)

    @staticmethod
    def get_condition_value_field(condition: str) -> str:
        """获取条件对应的行情字段名"""
        mapping = {
            "price_above": "price",
            "price_below": "price",
            "change_above": "change_pct",
            "change_below": "change_pct",
            "volume_ratio_above": "volume_ratio",
            "turnover_above": "turnover_rate",
            "amplitude_above": "amplitude",
        }
        return mapping.get(condition, "")
