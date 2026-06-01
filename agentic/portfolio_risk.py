from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortfolioRiskLimits:
    max_strategy_cash_pct: float = 0.2
    max_position_pct: float = 0.1
    max_holdings: int = 10
    blacklist: set[str] = field(default_factory=set)
    max_industry_pct: float = 0.35


@dataclass(frozen=True)
class PortfolioRiskResult:
    allowed: bool
    reasons: tuple[str, ...]


class PortfolioRiskGate:
    def __init__(self, limits: PortfolioRiskLimits | None = None):
        self.limits = limits or PortfolioRiskLimits()

    def evaluate(self, intent: dict, portfolio: dict | None = None, industry_map: dict[str, str] | None = None) -> PortfolioRiskResult:
        portfolio = dict(portfolio or {})
        industry_map = dict(industry_map or {})
        codes = [_plain_code(code) for code in intent.get("codes", [])]
        positions = { _plain_code(code): float(value) for code, value in dict(portfolio.get("positions") or {}).items() }
        total_equity = max(float(portfolio.get("total_equity") or 0), 1.0)
        cash_pct = _safe_float(intent.get("cash_pct"), default=0.0)
        reasons: list[str] = []

        for code in codes:
            if code in self.limits.blacklist:
                reasons.append(f"blacklisted code: {code}")

        if cash_pct > self.limits.max_strategy_cash_pct:
            reasons.append(f"strategy cash pct {cash_pct:.4f} exceeds {self.limits.max_strategy_cash_pct:.4f}")

        per_code_pct = cash_pct / max(len(codes), 1)
        for code in codes:
            current_pct = positions.get(code, 0.0) / total_equity
            projected_pct = current_pct + per_code_pct
            if projected_pct > self.limits.max_position_pct:
                reasons.append(f"position pct {projected_pct:.4f} exceeds {self.limits.max_position_pct:.4f}")
                break

        holding_count = len(set(positions) | set(codes))
        if holding_count > self.limits.max_holdings:
            reasons.append(f"holding count {holding_count} exceeds {self.limits.max_holdings}")

        industry_pct: dict[str, float] = {}
        for code, amount in positions.items():
            industry = industry_map.get(code)
            if industry:
                industry_pct[industry] = industry_pct.get(industry, 0.0) + amount / total_equity
        for code in codes:
            industry = industry_map.get(code)
            if industry:
                industry_pct[industry] = industry_pct.get(industry, 0.0) + per_code_pct
        for industry, pct in sorted(industry_pct.items()):
            if pct + 1e-12 >= self.limits.max_industry_pct:
                reasons.append(f"industry {industry} pct {pct:.4f} reaches limit {self.limits.max_industry_pct:.4f}")
                break

        return PortfolioRiskResult(allowed=not reasons, reasons=tuple(reasons))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _plain_code(code: object) -> str:
    raw = str(code or "").strip()
    if raw[:2].lower() in {"sh", "sz", "bj"}:
        raw = raw[2:]
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw

