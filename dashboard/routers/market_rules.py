"""市场规则 API"""
from fastapi import APIRouter, Query

from engine.market_rules import get_market_rule, get_rule_for_code, list_markets

router = APIRouter()


@router.get("/list")
async def get_markets():
    """列出支持的市场"""
    return {"markets": list_markets()}


@router.get("/detail")
async def get_market_detail(market: str = Query("CN", description="市场代码")):
    """获取市场详细规则"""
    try:
        rule = get_market_rule(market)
        fees = rule.fees()
        sessions = []
        for wd in range(7):
            for s in rule.trading_sessions(wd):
                sessions.append({
                    "weekday": wd,
                    "open": s.open.strftime("%H:%M"),
                    "close": s.close.strftime("%H:%M"),
                    "label": s.label,
                })
        return {
            "code": rule.market_code,
            "name": rule.market_name,
            "is_t_plus_1": rule.is_t_plus_1(),
            "fees": {
                "commission_rate": fees.commission_rate,
                "commission_min": fees.commission_min,
                "stamp_tax_rate": fees.stamp_tax_rate,
                "slippage": fees.slippage,
                "margin_rate": fees.margin_rate,
            },
            "sessions": sessions,
        }
    except ValueError as e:
        return {"error": str(e)}


@router.get("/detect")
async def detect_market(code: str = Query(..., description="股票代码")):
    """根据代码自动检测市场"""
    rule = get_rule_for_code(code)
    return {
        "code": rule.market_code,
        "name": rule.market_name,
        "lot_size": rule.lot_size(code),
        "is_t_plus_1": rule.is_t_plus_1(),
    }
