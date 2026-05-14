"""因子分析 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.factor_analyzer import AVAILABLE_FACTORS, FactorAnalyzer

router = APIRouter()
_analyzer = FactorAnalyzer()


class FactorAnalyzeRequest(BaseModel):
    factor_name: str
    stock_codes: list[str]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    forward_period: int = 5


class FactorCorrelationRequest(BaseModel):
    factor_names: list[str]
    stock_codes: list[str]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"


@router.get("/list")
async def list_factors():
    """获取可用因子列表"""
    return {
        "factors": [
            {"name": k, "label": v} for k, v in AVAILABLE_FACTORS.items()
        ]
    }


@router.post("/analyze")
async def analyze_factor(req: FactorAnalyzeRequest):
    """单因子分析: IC序列、IR、分层收益"""
    if req.factor_name not in AVAILABLE_FACTORS:
        raise HTTPException(400, f"因子 {req.factor_name} 不在可用列表中")
    if not req.stock_codes:
        raise HTTPException(400, "股票列表不能为空")
    if len(req.stock_codes) > 50:
        raise HTTPException(400, "单次最多分析50只股票")

    try:
        result = _analyzer.analyze_factor(
            factor_name=req.factor_name,
            stock_codes=req.stock_codes,
            start_date=req.start_date,
            end_date=req.end_date,
            forward_period=req.forward_period,
        )
        return {
            "success": True,
            "factor_name": result.factor_name,
            "avg_ic": result.avg_ic,
            "ic_std": result.ic_std,
            "ir": result.ir,
            "ic_series": result.ic_series,
            "quantile_returns": result.quantile_returns,
        }
    except Exception as e:
        raise HTTPException(500, f"因子分析失败: {e}")


@router.post("/correlation")
async def factor_correlation(req: FactorCorrelationRequest):
    """多因子相关性分析"""
    if len(req.factor_names) < 2:
        raise HTTPException(400, "至少需要2个因子")
    if not req.stock_codes:
        raise HTTPException(400, "股票列表不能为空")

    try:
        result = _analyzer.analyze_multiple_factors(
            factor_names=req.factor_names,
            stock_codes=req.stock_codes,
            start_date=req.start_date,
            end_date=req.end_date,
        )
        if "error" in result:
            raise HTTPException(400, result["error"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"因子相关性分析失败: {e}")
