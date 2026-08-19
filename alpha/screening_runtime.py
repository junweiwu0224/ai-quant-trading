"""Evidence-aware screening facade over the canonical alpha screener.

The runtime owns the screening strategy contract.  ``StockScreener`` remains
the market-data/filter adapter, so existing callers can continue to use its
legacy filter arguments without opting into the richer strategy schema.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .screener import StockScreener


# These are intentionally small, deterministic defaults.  Project-specific
# strategies can be supplied as a mapping or a YAML document without changing
# the runtime's interface.
BUILTIN_SCREENING_STRATEGIES: dict[str, dict[str, Any]] = {
    "screening:低估蓝筹": {
        "namespace": "screening",
        "name": "低估蓝筹",
        "hard_filters": [
            {"field": "pe_ratio", "op": "between", "value": [0, 20]},
            {"field": "pb_ratio", "op": "between", "value": [0, 3]},
            {"field": "market_cap", "op": "gt", "value": 200},
        ],
        "factors": [{"field": "pe_ratio", "weight": 0.45, "direction": "lower"},
                    {"field": "pb_ratio", "weight": 0.35, "direction": "lower"},
                    {"field": "market_cap", "weight": 0.20, "direction": "higher"}],
        "risk_adjustment": {"fields": {"amplitude": 0.7, "turnover_rate": 0.3}},
    },
    "screening:动量突破": {
        "namespace": "screening",
        "name": "动量突破",
        "hard_filters": [
            {"field": "change_pct", "op": "gt", "value": 3},
            {"field": "turnover_rate", "op": "gt", "value": 3},
        ],
        "factors": [{"field": "change_pct", "weight": 0.55, "direction": "higher"},
                    {"field": "turnover_rate", "weight": 0.25, "direction": "higher"},
                    {"field": "amount", "weight": 0.20, "direction": "higher"}],
        "risk_adjustment": {"fields": {"amplitude": 0.65, "turnover_rate": 0.35}},
    },
}

# Public alias for callers that use the shorter name.
SCREENING_STRATEGIES = BUILTIN_SCREENING_STRATEGIES

@dataclass(frozen=True)
class ScreeningRun:
    run_id: str
    strategy_namespace: str
    strategy_name: str
    status: str
    source: str
    source_health: Mapping[str, Any]
    candidates: tuple[Mapping[str, Any], ...]
    total: int
    degraded: bool = False
    error: str = ""
    strategy_source: str = "legacy"
    strategy_config: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_namespace": self.strategy_namespace,
            "strategy_name": self.strategy_name,
            "status": self.status,
            "source": self.source,
            "source_health": dict(self.source_health),
            "candidates": [dict(item) for item in self.candidates],
            "total": self.total,
            "degraded": self.degraded,
            "error": self.error,
            "strategy_source": self.strategy_source,
            "strategy_config": dict(self.strategy_config or {}),
        }


class ScreeningRuntime:
    """Run deterministic candidate selection with an optional rerank adapter."""

    def __init__(
        self,
        screener: StockScreener | None = None,
        *,
        cache_ttl: int = 300,
        now: Callable[[], float] | None = None,
        llm_reranker: Callable[..., Any] | None = None,
    ) -> None:
        self.screener = screener or StockScreener()
        self.cache_ttl = max(1, int(cache_ttl))
        self._now = now or time.time
        self.llm_reranker = llm_reranker
        self._last_good: dict[str, tuple[float, ScreeningRun]] = {}

    def run(
        self,
        *,
        strategy_name: str,
        filters: list[dict] | None = None,
        codes: list[str] | None = None,
        sort_by: str = "change_pct",
        sort_desc: bool = True,
        page_size: int = 50,
        namespace: str = "screening",
        strategy: Mapping[str, Any] | str | Path | None = None,
        strategy_yaml: Mapping[str, Any] | str | Path | None = None,
        llm_reranker: Callable[..., Any] | None = None,
    ) -> ScreeningRun:
        if namespace == "analysis":
            raise ValueError("single-stock analysis strategies cannot run in screening namespace")
        config, strategy_source = self._resolve_strategy(
            strategy_name, namespace, strategy if strategy is not None else strategy_yaml
        )
        effective_namespace = str(config.get("namespace") or namespace).strip() or namespace
        if effective_namespace == "analysis":
            raise ValueError("single-stock analysis strategies cannot run in screening namespace")
        effective_name = str(config.get("name") or strategy_name).strip() or strategy_name
        hard_filters = [*list(filters or []), *self._as_filter_list(config.get("hard_filters", config.get("filters")))]
        bounded_page_size = max(1, min(int(page_size), 500))
        key_payload = {
            "namespace": effective_namespace,
            "strategy_name": effective_name,
            "strategy_source": strategy_source,
            "strategy": config,
            "filters": hard_filters,
            "codes": codes or [],
            "sort_by": sort_by,
            "sort_desc": sort_desc,
            "page_size": bounded_page_size,
            "llm": bool(llm_reranker or self.llm_reranker or config.get("llm_rerank")),
        }
        key = hashlib.sha256(
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()[:24]
        now = self._now()
        try:
            result = self.screener.screen(
                filters=hard_filters,
                codes=list(codes or []),
                sort_by=sort_by,
                sort_desc=sort_desc,
                page=1,
                page_size=bounded_page_size,
            )
            raw_candidates = [dict(item) for item in (result.get("stocks") or [])]
            # The adapter is allowed to be a test double or a legacy provider;
            # enforcing the contract here guarantees hard filters either way.
            candidates = [item for item in raw_candidates if self._matches_all(item, hard_filters)]
            candidates, quality_exclusions = self._exclude_missing_numeric_inputs(candidates, config)
            candidates = self._score_candidates(candidates, config)
            source = str(config.get("source") or "eastmoney_realtime")
            health: dict[str, Any] = {
                "status": "degraded" if quality_exclusions else "ok",
                "stale": False,
                "candidate_count": len(candidates),
                "provider": source,
                "data_quality": "partial" if quality_exclusions else "complete",
            }
            if quality_exclusions:
                health["excluded_candidates"] = {
                    "missing_numeric_fields": quality_exclusions,
                }
            run_id = f"screen_{key}_{int(now)}"
            reranker = llm_reranker or self.llm_reranker
            rerank_requested = bool(reranker or config.get("llm_rerank"))
            if rerank_requested:
                if reranker is None:
                    health.update({"llm_rerank": "unavailable", "status": "degraded"})
                else:
                    try:
                        candidates = self._apply_rerank(reranker, candidates, config)
                        health["llm_rerank"] = "ok"
                    except Exception as exc:
                        # Deterministic ranking is already complete.  Preserve it
                        # and expose the optional provider failure to the caller.
                        health.update({"llm_rerank": "degraded", "status": "degraded", "llm_error": str(exc)})
            candidates = self._decorate_candidates(
                candidates,
                run_id=run_id,
                namespace=effective_namespace,
                strategy_name=effective_name,
                source=source,
                source_health=health,
            )
            degraded = health.get("status") != "ok"
            run = ScreeningRun(
                run_id=run_id,
                strategy_namespace=effective_namespace,
                strategy_name=effective_name,
                status="completed",
                source=source,
                source_health=health,
                candidates=tuple(candidates),
                total=len(candidates),
                degraded=degraded,
                strategy_source=strategy_source,
                strategy_config=config,
            )
            self._last_good[key] = (now, run)
            return run
        except Exception as exc:
            cached = self._last_good.get(key)
            if cached and now - cached[0] <= self.cache_ttl:
                previous = cached[1]
                return ScreeningRun(
                    **{
                        **previous.__dict__,
                        "status": "stale_cache",
                        "degraded": True,
                        "error": str(exc),
                        "source_health": {
                            **dict(previous.source_health),
                            "status": "stale",
                            "stale": True,
                            "error": str(exc),
                        },
                    }
                )
            return ScreeningRun(
                run_id=f"screen_{key}_{int(now)}",
                strategy_namespace=effective_namespace,
                strategy_name=effective_name,
                status="failed",
                source=str(config.get("source") or "eastmoney_realtime"),
                source_health={"status": "failed", "stale": False, "error": str(exc)},
                candidates=(),
                total=0,
                degraded=True,
                error=str(exc),
                strategy_source=strategy_source,
                strategy_config=config,
            )

    @staticmethod
    def _resolve_strategy(
        strategy_name: str,
        namespace: str,
        supplied: Mapping[str, Any] | str | Path | None,
    ) -> tuple[dict[str, Any], str]:
        if supplied is not None:
            payload = _load_strategy_document(supplied)
            if not isinstance(payload, Mapping):
                raise ValueError("screening strategy must be a mapping")
            config = dict(payload)
            config.setdefault("namespace", namespace)
            config.setdefault("name", strategy_name)
            if str(config["namespace"]) == "analysis":
                raise ValueError("single-stock analysis strategies cannot run in screening namespace")
            return config, "yaml"
        builtin = BUILTIN_SCREENING_STRATEGIES.get(f"{namespace}:{strategy_name}")
        if builtin is None:
            builtin = BUILTIN_SCREENING_STRATEGIES.get(strategy_name)
        if builtin is not None:
            return dict(builtin), "builtin"
        return {"namespace": namespace, "name": strategy_name}, "legacy"

    @staticmethod
    def _as_filter_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, Mapping):
            return [dict(value)]
        if not isinstance(value, (list, tuple)):
            raise ValueError("screening hard_filters must be a list")
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @classmethod
    def _score_candidates(cls, items: list[dict[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
        factors = cls._factor_specs(config.get("factors") or config.get("factor_weights"))
        if not factors:
            return cls._stable_candidates(items)
        output = [dict(item) for item in items]
        contributions: dict[str, list[float]] = {}
        for spec in factors:
            field = spec["field"]
            values = [cls._number(item.get(field)) for item in output]
            observed = [value for value in values if value is not None]
            lo = cls._number(spec.get("min", spec.get("low")))
            hi = cls._number(spec.get("max", spec.get("high")))
            if lo is None:
                lo = min(observed) if observed else None
            if hi is None:
                hi = max(observed) if observed else None
            if lo is None or hi is None:
                return []
            for item, raw in zip(output, values):
                if raw is None:
                    return []
                normalized = cls._normalize(raw, lo, hi)
                if str(spec.get("direction", "higher")).lower() in {"lower", "low", "descending"}:
                    normalized = 1.0 - normalized
                contributions.setdefault(field, []).append(normalized * float(spec["weight"]))
        total_weight = sum(float(spec["weight"]) for spec in factors) or 1.0
        for index, item in enumerate(output):
            breakdown = {field: round(values[index] / total_weight * 100, 4) for field, values in contributions.items()}
            factor_score = sum(breakdown.values())
            risk_penalty = cls._risk_penalty(item, output, config.get("risk_adjustment"))
            item["factor_score"] = round(factor_score, 4)
            item["risk_penalty"] = round(risk_penalty, 4)
            item["risk_adjusted_score"] = round(factor_score - risk_penalty, 4)
            item["score"] = item["risk_adjusted_score"]
            item["score_breakdown"] = breakdown
        return sorted(output, key=lambda item: (-float(item.get("risk_adjusted_score") or 0), str(item.get("code") or "")))

    @staticmethod
    def _factor_specs(value: Any) -> list[dict[str, Any]]:
        if not value:
            return []
        if isinstance(value, Mapping):
            value = [{"field": field, "weight": weight} for field, weight in value.items()]
        result = []
        for item in value if isinstance(value, (list, tuple)) else []:
            if not isinstance(item, Mapping) or not item.get("field"):
                continue
            weight = float(item.get("weight", 1.0) or 0)
            if weight > 0:
                result.append({**dict(item), "field": str(item["field"]), "weight": weight})
        return result

    @classmethod
    def _risk_penalty(cls, item: Mapping[str, Any], items: list[dict[str, Any]], value: Any) -> float:
        if not value:
            return 0.0
        if isinstance(value, Mapping):
            fields = value.get("fields") or value.get("risk_fields") or value.get("penalty_fields") or {}
            if isinstance(fields, (list, tuple)):
                fields = {str(field): 1.0 for field in fields}
            if not fields and value.get("field"):
                fields = {str(value["field"]): float(value.get("weight", 1.0) or 0)}
            multiplier = float(value.get("weight", 1.0) or 0)
        else:
            fields = {str(field): 1.0 for field in value if isinstance(value, (list, tuple))}
            multiplier = 1.0
        penalty = 0.0
        total_weight = sum(float(weight or 0) for weight in fields.values()) or 1.0
        for field, weight in fields.items():
            raw_values = [cls._number(other.get(field)) for other in items]
            observed = [raw for raw in raw_values if raw is not None]
            raw = cls._number(item.get(field))
            normalized = 1.0 if raw is None or not observed else cls._normalize(raw, min(observed), max(observed))
            penalty += normalized * float(weight or 0) / total_weight
        return penalty * 100 * multiplier

    @classmethod
    def _apply_rerank(cls, reranker: Callable[..., Any], items: list[dict[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = reranker(items, dict(config))
        if inspect.isawaitable(result):
            raise TypeError("async LLM rerankers are not supported by synchronous ScreeningRuntime.run")
        if isinstance(result, Mapping):
            scores = result.get("scores", result)
            if isinstance(scores, Mapping):
                for item in items:
                    if str(item.get("code")) in scores:
                        item["llm_score"] = float(scores[str(item["code"])])
                return sorted(items, key=lambda item: (-float(item.get("llm_score") or 0), str(item.get("code") or "")))
        if not isinstance(result, (list, tuple)):
            raise ValueError("LLM reranker must return candidates, codes, or a score mapping")
        by_code = {str(item.get("code")): item for item in items}
        reordered: list[dict[str, Any]] = []
        for entry in result:
            code = str(entry.get("code")) if isinstance(entry, Mapping) else str(entry)
            if code in by_code and by_code[code] not in reordered:
                if isinstance(entry, Mapping) and entry.get("llm_score") is not None:
                    by_code[code]["llm_score"] = float(entry["llm_score"])
                reordered.append(by_code[code])
        reordered.extend(item for item in items if item not in reordered)
        return reordered

    @classmethod
    def _decorate_candidates(
        cls,
        items: list[dict[str, Any]],
        *,
        run_id: str,
        namespace: str,
        strategy_name: str,
        source: str,
        source_health: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        total = len(items)
        for rank, item in enumerate(items, start=1):
            code = str(item.get("code") or "").strip()
            source_context = {
                "source": source,
                "source_health": dict(source_health),
                "run_id": run_id,
                "strategy_namespace": namespace,
                "strategy_name": strategy_name,
                "rank": rank,
                "pool_size": total,
            }
            actions = [
                {"id": "open_stock", "code": code, "label": "打开个股"},
                {"id": "research", "code": code, "label": "发起研究"},
                {"id": "add_watch", "code": code, "label": "加入观察"},
                {"id": "draft_backtest", "code": code, "label": "生成回测草案"},
                {"id": "paper_candidate", "code": code, "label": "生成 Paper 观察项"},
            ]
            item.update(
                {
                    "candidate_id": f"{run_id}:{code or rank}",
                    "rank": rank,
                    "source": source,
                    "source_context": source_context,
                    "next_actions": actions,
                    "actions": actions,
                    "rank_reason": "risk-adjusted factor score" if "risk_adjusted_score" in item else "deterministic screener ranking",
                }
            )
        return items

    @staticmethod
    def _matches_all(item: Mapping[str, Any], filters: list[dict[str, Any]]) -> bool:
        return all(ScreeningRuntime._matches(item, condition) for condition in filters)

    @staticmethod
    def _matches(item: Mapping[str, Any], condition: Mapping[str, Any]) -> bool:
        field = str(condition.get("field") or "")
        op = str(condition.get("op") or "").lower()
        value = condition.get("value")
        actual = item.get(field)
        if actual is None:
            return False
        try:
            if op in {"gt", "lt", "gte", "lte", "between"}:
                actual = ScreeningRuntime._number(actual)
                if actual is None:
                    return False
                if op == "between":
                    if not isinstance(value, (list, tuple)) or len(value) != 2:
                        return False
                    bounds = [ScreeningRuntime._number(item) for item in value]
                    if any(bound is None for bound in bounds):
                        return False
                    return bounds[0] <= actual <= bounds[1]
                numeric_value = ScreeningRuntime._number(value)
                if numeric_value is None:
                    return False
                value = numeric_value
            if op in {"eq", "=", "equal"}:
                return actual == value
            if op in {"ne", "!=", "not_equal"}:
                return actual != value
            if op == "gt":
                return actual > value
            if op == "lt":
                return actual < value
            if op == "gte":
                return actual >= value
            if op == "lte":
                return actual <= value
            if op in {"in", "one_of"}:
                return actual in value
            if op in {"not_in", "nin"}:
                return actual not in value
            if op == "contains":
                return value in actual
        except (TypeError, ValueError, IndexError):
            return False
        return False

    @classmethod
    def _exclude_missing_numeric_inputs(
        cls,
        items: list[dict[str, Any]],
        config: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Keep only candidates with complete inputs for deterministic scoring.

        A missing factor or risk input is a data-quality failure, not a zero
        score.  Exclusions are returned separately so the run can expose the
        exact reason without presenting an under-specified candidate as valid.
        """

        factor_fields = [spec["field"] for spec in cls._factor_specs(config.get("factors") or config.get("factor_weights"))]
        risk_fields = cls._risk_fields(config.get("risk_adjustment"))
        required_fields = list(dict.fromkeys([*factor_fields, *risk_fields]))
        if not required_fields:
            return items, []

        qualified: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        factor_field_set = set(factor_fields)
        for item in items:
            missing = [field for field in required_fields if cls._number(item.get(field)) is None]
            if not missing:
                qualified.append(item)
                continue
            reason = "missing_numeric_factor" if any(field in factor_field_set for field in missing) else "missing_numeric_risk"
            excluded.append(
                {
                    "code": str(item.get("code") or ""),
                    "fields": missing,
                    "reason": reason,
                }
            )
        excluded.sort(key=lambda item: item["code"])
        return qualified, excluded

    @staticmethod
    def _risk_fields(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, Mapping):
            fields = value.get("fields") or value.get("risk_fields") or value.get("penalty_fields") or {}
            if isinstance(fields, Mapping):
                return [str(field) for field in fields if str(field).strip()]
            if isinstance(fields, (list, tuple)):
                return [str(field) for field in fields if str(field).strip()]
            if value.get("field"):
                return [str(value["field"])]
        if isinstance(value, (list, tuple)):
            return [str(field) for field in value if str(field).strip()]
        return []

    @staticmethod
    def _normalize(value: float, low: float, high: float) -> float:
        if high == low:
            return 0.5
        return max(0.0, min(1.0, (value - low) / (high - low)))

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stable_candidates(items: list[dict]) -> list[dict]:
        def sort_key(item: Mapping[str, Any]) -> tuple[bool, float, str]:
            change_pct = ScreeningRuntime._number(item.get("change_pct"))
            return (
                change_pct is None,
                0.0 if change_pct is None else -change_pct,
                str(item.get("code") or ""),
            )

        return sorted(
            (dict(item) for item in items),
            key=sort_key,
        )


def _load_strategy_document(value: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    path = Path(value).expanduser() if isinstance(value, (str, Path)) else None
    raw = path.read_text(encoding="utf-8") if path is not None and path.exists() else str(value)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, Mapping):
            return parsed
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw)
        if isinstance(parsed, Mapping):
            return parsed
    except ImportError:
        pass
    except Exception as exc:
        raise ValueError(f"invalid screening strategy YAML: {exc}") from exc
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, Mapping):
            return parsed
    except (SyntaxError, ValueError):
        pass
    return _parse_basic_yaml(raw)


def _parse_basic_yaml(raw: str) -> Mapping[str, Any]:
    """Parse the small YAML subset used by screening profiles.

    PyYAML remains preferred.  This fallback keeps the runtime usable in the
    project's minimal test/runtime installs without turning YAML into a new
    mandatory dependency.  It supports nested mappings, lists of mappings,
    scalar values, and inline JSON-style lists.
    """
    lines = []
    for raw_line in raw.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        raise ValueError("screening strategy YAML is empty")

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        is_list = lines[index][1].startswith("-")
        result: Any = [] if is_list else {}
        while index < len(lines) and lines[index][0] == indent:
            text = lines[index][1]
            if is_list:
                if not text.startswith("-"):
                    break
                content = text[1:].strip()
                if not content:
                    if index + 1 < len(lines) and lines[index + 1][0] > indent:
                        value, index = parse_block(index + 1, lines[index + 1][0])
                    else:
                        value, index = None, index + 1
                    result.append(value)
                    continue
                if ":" in content and not content.startswith(("[", "{")):
                    key, value_text = content.split(":", 1)
                    entry: dict[str, Any] = {key.strip(): _yaml_scalar(value_text.strip())} if value_text.strip() else {key.strip(): {}}
                    index += 1
                    if index < len(lines) and lines[index][0] > indent:
                        nested, index = parse_block(index, lines[index][0])
                        if not value_text.strip():
                            entry[key.strip()] = nested
                        elif isinstance(nested, dict):
                            entry.update(nested)
                    result.append(entry)
                    continue
                result.append(_yaml_scalar(content))
                index += 1
                continue
            if ":" not in text:
                raise ValueError(f"invalid YAML line: {text}")
            key, value_text = text.split(":", 1)
            key = key.strip()
            value_text = value_text.strip()
            index += 1
            if not value_text and index < len(lines) and lines[index][0] > indent:
                value, index = parse_block(index, lines[index][0])
            else:
                value = _yaml_scalar(value_text)
            result[key] = value
        return result, index

    value, _ = parse_block(0, lines[0][0])
    if not isinstance(value, Mapping):
        raise ValueError("screening strategy YAML root must be a mapping")
    return value


def _yaml_scalar(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return float(value) if any(char in value for char in ".eE") else int(value)
    except ValueError:
        return value.strip("'\"")
