"""自选股管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data.storage.storage import DataStorage
from data.collector.quote_service import get_quote_service

router = APIRouter()
storage = DataStorage()


class AddWatchlistRequest(BaseModel):
    code: str


@router.get("")
async def get_watchlist():
    """获取自选股列表（含名称、行业、最新价、数据日期、概念、板块）"""
    stocks = storage.get_watchlist_with_info()
    # 合并实时行情数据
    try:
        qs = get_quote_service()
        for s in stocks:
            q = qs.get_quote(s["code"])
            if q:
                s["price"] = q.price
                s["change_pct"] = q.change_pct
                s["industry"] = q.industry or s.get("industry", "")
                s["sector"] = q.sector or ""
                s["concepts"] = q.concepts.split(",") if q.concepts else []
    except Exception:
        pass
    return stocks


@router.post("")
async def add_to_watchlist(req: AddWatchlistRequest):
    """添加自选股"""
    code = req.code.strip()
    if not code:
        raise HTTPException(400, "股票代码不能为空")

    # 检查股票是否在数据库中
    stock_list = storage.get_stock_list()
    if stock_list.empty or code not in stock_list["code"].values:
        # 尝试从 AKShare 查询
        try:
            from data.collector.collector import StockCollector
            collector = StockCollector()
            all_stocks = collector.get_stock_list()
            match = all_stocks[all_stocks["code"] == code]
            if match.empty:
                raise HTTPException(404, f"股票代码 {code} 不存在")
            # 保存到 stock_info
            storage.save_stock_info(match)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"查询股票信息失败: {e}")

    added = storage.add_to_watchlist(code)
    if not added:
        return {"message": "已在自选股中", "code": code}

    # 自动触发数据采集
    try:
        from data.collector.collector import StockCollector
        from datetime import datetime
        collector = StockCollector()
        latest = storage.get_latest_date(code)
        start = str(latest) if latest else "20200101"
        end = datetime.now().strftime("%Y%m%d")
        df = collector.get_stock_daily(code, start_date=start, end_date=end)
        if not df.empty:
            storage.save_stock_daily(code, df)
    except Exception as e:
        from loguru import logger
        logger.warning(f"自动采集 {code} 数据失败: {e}")

    # 更新行情订阅
    try:
        get_quote_service().subscribe([code])
    except Exception:
        pass

    return {"message": "添加成功", "code": code}


@router.delete("/{code}")
async def remove_from_watchlist(code: str):
    """删除自选股"""
    removed = storage.remove_from_watchlist(code)
    if not removed:
        raise HTTPException(404, f"自选股 {code} 不存在")

    # 更新行情订阅
    try:
        get_quote_service().unsubscribe([code])
    except Exception:
        pass

    return {"message": "删除成功", "code": code}


@router.post("/sync")
async def sync_watchlist():
    """手动触发自选股数据同步"""
    from datetime import datetime
    from data.collector.collector import StockCollector
    from loguru import logger

    codes = storage.get_watchlist()
    if not codes:
        return {"message": "自选股为空", "synced": 0}

    collector = StockCollector()
    synced = 0
    errors = []
    for code in codes:
        try:
            latest = storage.get_latest_date(code)
            start = str(latest) if latest else "20200101"
            end = datetime.now().strftime("%Y%m%d")
            df = collector.get_stock_daily(code, start_date=start, end_date=end)
            if not df.empty:
                storage.save_stock_daily(code, df)
                synced += 1
        except Exception as e:
            errors.append(f"{code}: {e}")
            logger.warning(f"同步 {code} 失败: {e}")

    return {"message": f"同步完成", "synced": synced, "total": len(codes), "errors": errors}
