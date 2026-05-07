"""策略持久化管理"""
import json
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import PROJECT_ROOT

STRATEGIES_FILE = PROJECT_ROOT / "data" / "strategies.json"

BUILTIN_STRATEGIES = [
    {
        "name": "dual_ma",
        "label": "双均线策略",
        "type": "趋势",
        "description": "短期均线上穿长期均线买入，下穿卖出。",
        "params": {"short_window": 5, "long_window": 20},
        "builtin": True,
    },
    {
        "name": "bollinger",
        "label": "布林带策略",
        "type": "均值回归",
        "description": "价格触及下轨买入，触及上轨卖出。",
        "params": {"window": 20, "num_std": 2},
        "builtin": True,
    },
    {
        "name": "momentum",
        "label": "动量策略",
        "type": "趋势",
        "description": "基于 N 日收益率动量信号交易。",
        "params": {"lookback": 20, "threshold": 0.05},
        "builtin": True,
    },
]


class StrategyManager:
    """策略管理器：内置策略 + 自定义策略 + 内置策略参数覆盖"""

    def __init__(self, filepath: Optional[Path] = None):
        self._filepath = filepath or STRATEGIES_FILE
        self._custom: list[dict] = []
        self._overrides: dict[str, dict] = {}  # 内置策略参数覆盖 {name: params}
        self._load()

    def _load(self):
        if self._filepath.exists():
            try:
                data = json.loads(self._filepath.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "custom" in data:
                    self._custom = data.get("custom", [])
                    self._overrides = data.get("overrides", {})
                elif isinstance(data, list):
                    self._custom = data
                    self._overrides = {}
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"加载自定义策略失败: {e}")
                self._custom = []
                self._overrides = {}

    def _save(self):
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {"custom": self._custom, "overrides": self._overrides}
        self._filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _merge_builtin(self, s: dict) -> dict:
        """合并内置策略与其参数覆盖"""
        merged = dict(s, builtin=True)
        if s["name"] in self._overrides:
            merged["params"] = {**s.get("params", {}), **self._overrides[s["name"]]}
            merged["has_override"] = True
        return merged

    def list_all(self) -> list[dict]:
        """返回所有策略（内置 + 自定义）"""
        builtin = [self._merge_builtin(s) for s in BUILTIN_STRATEGIES]
        custom = [dict(s, builtin=False) for s in self._custom]
        return builtin + custom

    def get(self, name: str) -> Optional[dict]:
        """按名称获取策略"""
        for s in BUILTIN_STRATEGIES:
            if s["name"] == name:
                return self._merge_builtin(s)
        for s in self._custom:
            if s["name"] == name:
                return dict(s, builtin=False)
        return None

    def add(self, data: dict) -> dict:
        """新增自定义策略"""
        name = data.get("name", "").strip()
        if not name:
            raise ValueError("策略名称不能为空")
        if self.get(name):
            raise ValueError(f"策略 {name} 已存在")
        entry = {
            "name": name,
            "label": data.get("label", name),
            "type": data.get("type", "自定义"),
            "description": data.get("description", ""),
            "params": data.get("params", {}),
        }
        self._custom.append(entry)
        self._save()
        logger.info(f"新增策略: {name}")
        return dict(entry, builtin=False)

    def update(self, name: str, data: dict) -> dict:
        """编辑策略（内置策略只允许修改参数，自定义策略可修改全部）"""
        # 内置策略：只更新参数覆盖
        for s in BUILTIN_STRATEGIES:
            if s["name"] == name:
                if "params" in data and data["params"]:
                    self._overrides[name] = data["params"]
                    self._save()
                    logger.info(f"更新内置策略参数: {name}")
                return self._merge_builtin(s)

        # 自定义策略
        for i, s in enumerate(self._custom):
            if s["name"] == name:
                if "label" in data:
                    s["label"] = data["label"]
                if "type" in data:
                    s["type"] = data["type"]
                if "description" in data:
                    s["description"] = data["description"]
                if "params" in data:
                    s["params"] = data["params"]
                self._custom[i] = s
                self._save()
                logger.info(f"更新策略: {name}")
                return dict(s, builtin=False)
        raise ValueError(f"策略 {name} 不存在")

    def delete(self, name: str) -> bool:
        """删除自定义策略"""
        for i, s in enumerate(self._custom):
            if s["name"] == name:
                self._custom.pop(i)
                self._save()
                logger.info(f"删除策略: {name}")
                return True
        return False
