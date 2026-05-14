"""组合优化 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.portfolio_optimizer import METHODS, optimize_portfolio

router = APIRouter()


class PortfolioOptRequest(BaseModel):
    codes: list[str]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    method: str = "max_sharpe"  # equal_weight | risk_parity | min_variance | max_sharpe
    risk_free: float = 0.03


@router.get("/methods")
async def list_methods():
    """获取可用优化方法"""
    return {
        "methods": [
            {"name": "equal_weight", "label": "等权组合", "description": "每只股票等权重配置"},
            {"name": "risk_parity", "label": "风险平价", "description": "权重与波动率成反比"},
            {"name": "min_variance", "label": "最小方差", "description": "最小化组合方差"},
            {"name": "max_sharpe", "label": "最大夏普", "description": "最大化夏普比率"},
        ]
    }


@router.post("/optimize")
async def optimize(req: PortfolioOptRequest):
    """执行组合优化"""
    if len(req.codes) < 2:
        raise HTTPException(400, "至少需要2只股票")
    if len(req.codes) > 20:
        raise HTTPException(400, "单次最多优化20只股票")
    if req.method not in METHODS:
        raise HTTPException(400, f"不支持的优化方法: {req.method}")

    try:
        result = optimize_portfolio(
            codes=req.codes,
            start_date=req.start_date,
            end_date=req.end_date,
            method=req.method,
            risk_free=req.risk_free,
        )
        return {
            "success": True,
            "weights": result.weights,
            "expected_return": result.expected_return,
            "expected_volatility": result.expected_volatility,
            "sharpe_ratio": result.sharpe_ratio,
            "method": result.method,
        }
    except Exception as e:
        raise HTTPException(500, f"组合优化失败: {e}")
