from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
"""自选股管理 API"""
import threading

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from pydantic import BaseModel

from data.storage.storage import DataStorage, _normalize_storage_code
from data.collector.quote_service import get_quote_service
from data.collector.http_client import fetch_industry_batch

router = APIRouter()
storage = DataStorage()


class AddWatchlistRequest(BaseModel):
    code: str


@router.get("")
async def get_watchlist():
    """获取自选股列表（含名称、行业、最新价、数据日期、概念、板块）"""
    stocks = storage.get_watchlist_with_info()

    # 对行业为空的股票，从东方财富 F10 API 补充行业/板块/概念数据
    empty_codes = [s["code"] for s in stocks if not s.get("industry")]
    if empty_codes:
        info_map = fetch_industry_batch(empty_codes)
        if info_map:
            for s in stocks:
                info = info_map.get(s["code"])
                if info:
                    if info.get("industry"):
                        s["industry"] = info["industry"]
                    if info.get("sector"):
                        s["sector"] = info["sector"]
                    if info.get("concepts"):
                        s["concepts"] = [info["concepts"]]
            # 持久化行业到 stock_info 表
            try:
                industry_only = {k: v["industry"] for k, v in info_map.items() if v.get("industry")}
                if industry_only:
                    storage.update_stock_industry(industry_only)
            except Exception as e:
                logger.warning(f"更新 stock_info 行业数据失败: {e}")

    # 补充板块/概念为空的股票（push2 stock/get 暂不可用时）
    sector_empty = [s["code"] for s in stocks if not s.get("sector")]
    if sector_empty:
        info_map = fetch_industry_batch(sector_empty)
        for s in stocks:
            info = info_map.get(s["code"])
            if info:
                if not s.get("industry") and info.get("industry"):
                    s["industry"] = info["industry"]
                if not s.get("sector") and info.get("sector"):
                    s["sector"] = info["sector"]
                if not s.get("concepts") and info.get("concepts"):
                    s["concepts"] = [info["concepts"]]

    # 合并实时行情数据
    try:
        qs = get_quote_service()
        for s in stocks:
            q = qs.get_quote(s["code"])
            if q:
                s["price"] = q.price
                s["change_pct"] = q.change_pct
                if q.industry:
                    s["industry"] = q.industry
                if q.sector:
                    s["sector"] = q.sector
                if q.concepts:
                    s["concepts"] = q.concepts.split(",")
    except Exception as e:
        logger.warning(f"合并自选股实时行情失败: {e}")
    return stocks


@router.post("")
async def add_to_watchlist(req: AddWatchlistRequest):
    """添加自选股"""
    raw_code = req.code.strip()
    if not raw_code:
        raise HTTPException(400, "股票代码不能为空")

    _, plain_code = _normalize_storage_code(raw_code)
    if not plain_code:
        raise HTTPException(400, "股票代码格式非法")

    code = plain_code

    stock_list = storage.get_stock_list()
    if stock_list.empty or code not in stock_list["code"].values:
        try:
            from data.collector import StockCollector

            def _load_stock_match():
                collector = StockCollector()
                all_stocks = collector.get_stock_list()
                return all_stocks[all_stocks["code"] == code]

            match = await run_in_threadpool(_load_stock_match)
        except Exception as e:
            logger.warning(f"同步校验股票 {code} 失败: {e}")
            raise HTTPException(502, "股票校验失败")

        if match.empty:
            raise HTTPException(404, f"股票 {code} 不存在")

        storage.save_stock_info(match)
        stock_list = storage.get_stock_list()

    added = storage.add_to_watchlist(code)

    stock_list = storage.get_stock_list()
    stock_name = ""
    if not stock_list.empty:
        match = stock_list[stock_list["code"] == code]
        if not match.empty:
            stock_name = match.iloc[0].get("name", "")
    quote = None
    try:
        quote = get_quote_service().get_quote(code)
    except Exception as e:
        logger.warning(f"获取股票 {code} 实时行情失败: {e}")

    if not added:
        return {
            "success": True, "message": "已在自选股中", "code": code,
            "name": stock_name,
            "price": quote.price if quote else None,
            "change_pct": quote.change_pct if quote else None,
        }

    try:
        get_quote_service().subscribe([code])
    except Exception as e:
        logger.warning(f"订阅股票 {code} 实时行情失败: {e}")

    def _bg_collect():
        try:
            from data.collector import StockCollector
            collector = StockCollector()
            latest = storage.get_latest_date(code)
            start = str(latest) if latest else "20200101"
            end = now_beijing().strftime("%Y%m%d")
            df = collector.get_stock_daily(code, start_date=start, end_date=end)
            if not df.empty:
                storage.save_stock_daily(code, df)
                logger.info(f"后台采集 {code} 完成: {len(df)} 条")
        except Exception as e:
            logger.warning(f"后台采集 {code} 数据失败: {e}")

    threading.Thread(target=_bg_collect, daemon=True, name=f"collect-{code}").start()

    return {
        "success": True, "message": "添加成功", "code": code,
        "name": stock_name,
        "price": quote.price if quote else None,
        "change_pct": quote.change_pct if quote else None,
    }


@router.delete("/{code}")
async def remove_from_watchlist(code: str):
    """删除自选股"""
    _, plain_code = _normalize_storage_code(code)
    if not plain_code:
        raise HTTPException(400, "股票代码格式非法")

    removed = storage.remove_from_watchlist(plain_code)
    if not removed:
        raise HTTPException(404, f"自选股 {plain_code} 不存在")

    try:
        get_quote_service().unsubscribe([plain_code])
    except Exception as e:
        logger.warning(f"退订股票 {plain_code} 实时行情失败: {e}")

    return {"message": "删除成功", "code": plain_code}


@router.post("/sync")
async def sync_watchlist():
    """手动触发自选股数据同步"""
    from datetime import datetime
    from data.collector import StockCollector
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
            end = now_beijing().strftime("%Y%m%d")
            df = collector.get_stock_daily(code, start_date=start, end_date=end)
            if not df.empty:
                storage.save_stock_daily(code, df)
                synced += 1
        except Exception as e:
            errors.append(f"{code}: {e}")
            logger.warning(f"同步 {code} 失败: {e}")

    return {"message": f"同步完成", "synced": synced, "total": len(codes), "errors": errors}
