"""类通达信公式引擎。"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from alpha.factors.technical import TechnicalFactors
from data.storage import DataStorage


@dataclass(frozen=True)
class FormulaEvaluation:
    success: bool
    formula: str
    code: str | None
    latest_value: Any
    series: list[dict[str, Any]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "formula": self.formula,
            "code": self.code,
            "latest_value": self.latest_value,
            "series": self.series,
            "error": self.error,
        }


class FormulaEngine:
    """安全子集公式计算器。"""

    def __init__(self, storage: DataStorage | None = None):
        self._storage = storage or DataStorage()

    def evaluate_code(
        self,
        code: str,
        formula: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FormulaEvaluation:
        df = self._load_data(code, start_date, end_date)
        if df.empty:
            return FormulaEvaluation(
                success=False,
                formula=formula,
                code=code,
                latest_value=None,
                series=[],
                error=f"无可用数据: {code}",
            )

        try:
            result = self._evaluate_formula(df, formula)
            return self._build_result(code, formula, df, result)
        except Exception as exc:  # noqa: BLE001
            return FormulaEvaluation(
                success=False,
                formula=formula,
                code=code,
                latest_value=None,
                series=[],
                error=str(exc),
            )

    def screen_codes(
        self,
        formula: str,
        codes: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        pool = codes or self._storage.get_all_stock_codes()
        matches: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        stock_map = self._load_stock_meta()
        for code in pool:
            evaluation = self.evaluate_code(code, formula, start_date, end_date)
            if not evaluation.success:
                errors.append({"code": code, "error": evaluation.error or "公式执行失败"})
                continue

            if self._is_truthy(evaluation.latest_value):
                meta = stock_map.get(code, {})
                matches.append({
                    "code": code,
                    "name": meta.get("name", ""),
                    "industry": meta.get("industry", ""),
                    "latest_value": evaluation.latest_value,
                })

        return {
            "success": True,
            "total": len(matches),
            "matches": matches,
            "errors": errors[:20],
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "success": True,
            "functions": [
                {"name": "MA", "args": "series, window", "desc": "简单移动平均"},
                {"name": "EMA", "args": "series, window", "desc": "指数移动平均"},
                {"name": "RSI", "args": "close, window=14", "desc": "相对强弱指标"},
                {"name": "ATR", "args": "high, low, close, window=14", "desc": "平均真实波幅"},
                {"name": "HHV", "args": "series, window", "desc": "区间最高值"},
                {"name": "LLV", "args": "series, window", "desc": "区间最低值"},
                {"name": "REF", "args": "series, n=1", "desc": "向前引用"},
                {"name": "CROSS", "args": "a, b", "desc": "上穿判断"},
                {"name": "COUNT", "args": "condition, window", "desc": "窗口内满足次数"},
                {"name": "IF", "args": "condition, true_value, false_value", "desc": "条件分支"},
                {"name": "MAX", "args": "a, b", "desc": "逐项取最大"},
                {"name": "MIN", "args": "a, b", "desc": "逐项取最小"},
                {"name": "ABS", "args": "value", "desc": "绝对值"},
                {"name": "SUM", "args": "series, window", "desc": "窗口求和"},
                {"name": "MACD_DIF", "args": "close, fast=12, slow=26", "desc": "MACD DIF"},
                {"name": "MACD_DEA", "args": "close, fast=12, slow=26, signal=9", "desc": "MACD DEA"},
                {"name": "MACD_HIST", "args": "close, fast=12, slow=26, signal=9", "desc": "MACD 柱"},
            ],
            "fields": [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "ma_5",
                "ma_10",
                "ma_20",
                "ma_60",
                "rsi_14",
                "macd_dif",
                "macd_dea",
                "macd_hist",
                "boll_upper",
                "boll_lower",
                "boll_width",
                "atr_14",
                "volume_ratio_5",
                "ret_1d",
                "ret_5d",
                "ret_10d",
                "ret_20d",
            ],
            "examples": [
                "CLOSE > MA(CLOSE, 20)",
                "CROSS(MA(CLOSE, 5), MA(CLOSE, 20))",
                "RSI(CLOSE, 14) < 30",
            ],
        }

    def _load_data(
        self,
        code: str,
        start_date: date | None,
        end_date: date | None,
    ) -> pd.DataFrame:
        df = self._storage.get_stock_daily(code, start_date, end_date)
        if df.empty:
            return df

        frame = df.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        technical = TechnicalFactors.compute_all(frame)
        combined = pd.concat([frame.reset_index(drop=True), technical.reset_index(drop=True)], axis=1)
        combined = combined.replace([np.inf, -np.inf], np.nan)
        return combined

    def _load_stock_meta(self) -> dict[str, dict[str, str]]:
        stock_list = self._storage.get_stock_list()
        if stock_list.empty:
            return {}
        return {
            str(row["code"]): {
                "name": str(row.get("name", "") or ""),
                "industry": str(row.get("industry", "") or ""),
            }
            for _, row in stock_list.iterrows()
        }

    def _evaluate_formula(self, df: pd.DataFrame, formula: str) -> Any:
        tree = ast.parse(self._normalize_formula(formula), mode="eval")
        env = self._build_env(df)
        return self._eval_node(tree.body, env)

    def _normalize_formula(self, formula: str) -> str:
        return (
            formula.replace(" AND ", " and ")
            .replace(" OR ", " or ")
            .replace(" NOT ", " not ")
        )

    def _build_env(self, df: pd.DataFrame) -> dict[str, Any]:
        env: dict[str, Any] = {}
        for column in df.columns:
            value = df[column]
            env[column] = value
            env[column.upper()] = value
            env[column.lower()] = value

        env.update({
            "TRUE": True,
            "FALSE": False,
            "NP": np,
            "CLOSE": df["close"],
            "OPEN": df["open"],
            "HIGH": df["high"],
            "LOW": df["low"],
            "VOLUME": df["volume"],
            "AMOUNT": df["amount"],
            "MA": lambda series, window=5: self._to_series(series).rolling(int(window), min_periods=int(window)).mean(),
            "EMA": lambda series, window=5: self._to_series(series).ewm(span=int(window), adjust=False).mean(),
            "RSI": lambda series, window=14: TechnicalFactors.rsi(self._to_series(series), int(window)),
            "ATR": lambda high, low, close, window=14: TechnicalFactors.atr(
                self._to_series(high), self._to_series(low), self._to_series(close), int(window)
            ),
            "HHV": lambda series, window=20: self._to_series(series).rolling(int(window), min_periods=int(window)).max(),
            "LLV": lambda series, window=20: self._to_series(series).rolling(int(window), min_periods=int(window)).min(),
            "REF": lambda series, n=1: self._to_series(series).shift(int(n)),
            "SUM": lambda series, window=20: self._to_series(series).rolling(int(window), min_periods=int(window)).sum(),
            "CROSS": self._cross,
            "COUNT": self._count,
            "IF": self._if,
            "MAX": self._max,
            "MIN": self._min,
            "ABS": self._abs,
            "MACD_DIF": lambda close, fast=12, slow=26: TechnicalFactors.macd(
                self._to_series(close), int(fast), int(slow), 9
            )[0],
            "MACD_DEA": lambda close, fast=12, slow=26, signal=9: TechnicalFactors.macd(
                self._to_series(close), int(fast), int(slow), int(signal)
            )[1],
            "MACD_HIST": lambda close, fast=12, slow=26, signal=9: TechnicalFactors.macd(
                self._to_series(close), int(fast), int(slow), int(signal)
            )[2],
        })
        return env

    def _eval_node(self, node: ast.AST, env: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise ValueError(f"未知标识符: {node.id}")
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, env)
            right = self._eval_node(node.right, env)
            return self._apply_binop(node.op, left, right)
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, env)
            return self._apply_unaryop(node.op, operand)
        if isinstance(node, ast.BoolOp):
            values = [self._eval_node(v, env) for v in node.values]
            return self._apply_boolop(node.op, values)
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, env)
            result = None
            current = left
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval_node(comparator, env)
                compared = self._apply_compare(op, current, right)
                result = compared if result is None else self._combine(result, compared, "and")
                current = right
            return result
        if isinstance(node, ast.Call):
            func = self._eval_node(node.func, env)
            if not callable(func):
                raise ValueError("函数不可调用")
            args = [self._eval_node(arg, env) for arg in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, env) for kw in node.keywords}
            return func(*args, **kwargs)
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, env) for elt in node.elts)
        if isinstance(node, ast.List):
            return [self._eval_node(elt, env) for elt in node.elts]
        raise ValueError(f"不支持的表达式: {ast.dump(node, include_attributes=False)}")

    def _apply_binop(self, op: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left**right
        raise ValueError("不支持的运算符")

    def _apply_unaryop(self, op: ast.unaryop, operand: Any) -> Any:
        if isinstance(op, ast.USub):
            return -operand
        if isinstance(op, ast.UAdd):
            return +operand
        if isinstance(op, ast.Not):
            return ~operand if isinstance(operand, pd.Series) else not operand
        raise ValueError("不支持的一元运算符")

    def _apply_boolop(self, op: ast.boolop, values: list[Any]) -> Any:
        if not values:
            return False
        result = values[0]
        for value in values[1:]:
            result = self._combine(result, value, "and" if isinstance(op, ast.And) else "or")
        return result

    def _apply_compare(self, op: ast.cmpop, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        raise ValueError("不支持的比较符")

    def _combine(self, left: Any, right: Any, op: str) -> Any:
        if op == "and":
            return left & right if isinstance(left, pd.Series) or isinstance(right, pd.Series) else bool(left and right)
        return left | right if isinstance(left, pd.Series) or isinstance(right, pd.Series) else bool(left or right)

    def _cross(self, a: Any, b: Any) -> pd.Series:
        left = self._to_series(a)
        right = self._to_series(b)
        return (left > right) & (left.shift(1) <= right.shift(1))

    def _count(self, condition: Any, window: int) -> Any:
        series = self._to_series(condition)
        return series.fillna(False).astype(bool).rolling(int(window), min_periods=int(window)).sum()

    def _if(self, condition: Any, true_value: Any, false_value: Any) -> Any:
        if isinstance(condition, pd.Series):
            return pd.Series(np.where(condition.fillna(False), true_value, false_value), index=condition.index)
        return true_value if condition else false_value

    def _max(self, a: Any, b: Any) -> Any:
        if isinstance(a, pd.Series) or isinstance(b, pd.Series):
            return pd.Series(np.maximum(self._as_array(a), self._as_array(b)))
        return max(a, b)

    def _min(self, a: Any, b: Any) -> Any:
        if isinstance(a, pd.Series) or isinstance(b, pd.Series):
            return pd.Series(np.minimum(self._as_array(a), self._as_array(b)))
        return min(a, b)

    def _abs(self, value: Any) -> Any:
        if isinstance(value, pd.Series):
            return value.abs()
        return abs(value)

    def _build_result(self, code: str, formula: str, df: pd.DataFrame, result: Any) -> FormulaEvaluation:
        if isinstance(result, pd.Series):
            series = [
                {"date": self._format_date(df.iloc[i]["date"]), "value": self._normalize_value(result.iloc[i])}
                for i in range(len(result))
            ]
            latest_value = self._normalize_value(result.iloc[-1]) if len(result) else None
            return FormulaEvaluation(True, formula, code, latest_value, series)

        return FormulaEvaluation(True, formula, code, self._normalize_value(result), [])

    def _to_series(self, value: Any) -> pd.Series:
        if isinstance(value, pd.Series):
            return value
        if isinstance(value, (list, tuple, np.ndarray)):
            return pd.Series(value)
        return pd.Series([value])

    def _as_array(self, value: Any) -> np.ndarray:
        if isinstance(value, pd.Series):
            return value.to_numpy()
        return np.asarray(value)

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, (np.generic,)):
            return value.item()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, float) and np.isnan(value):
            return None
        return value

    def _format_date(self, value: Any) -> str:
        if isinstance(value, pd.Timestamp):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def _is_truthy(self, value: Any) -> bool:
        if isinstance(value, pd.Series):
            value = value.iloc[-1] if not value.empty else False
        if isinstance(value, np.generic):
            value = value.item()
        return bool(value)
