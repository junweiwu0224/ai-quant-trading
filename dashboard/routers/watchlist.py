"""自选股管理 API"""
import requests
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from data.storage.storage import DataStorage
from data.collector.quote_service import get_quote_service

router = APIRouter()
storage = DataStorage()

_DATACENTER_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_DATACENTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/",
}


def _fetch_industry_batch(codes: list[str]) -> dict[str, dict[str, str]]:
    """从东方财富 F10 API 批量获取股票分类，返回 {code: {industry, sector, concepts}}"""
    if not codes:
        return {}
    try:
        code_list = ",".join(f'"{c}"' for c in codes)
        params = {
            "reportName": "RPT_F10_BASIC_ORGINFO",
            "columns": "SECURITY_CODE,INDUSTRYCSRC1,BOARD_NAME_LEVEL",
            "filter": f"(SECURITY_CODE in ({code_list}))",
            "pageSize": len(codes),
            "pageNumber": 1,
            "source": "HSF10",
            "client": "PC",
        }
        resp = requests.get(_DATACENTER_URL, params=params, headers=_DATACENTER_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        for row in (data.get("result", {}) or {}).get("data", []) or []:
            code = row.get("SECURITY_CODE", "")
            if not code:
                continue
            industry = row.get("INDUSTRYCSRC1", "")
            board_level = row.get("BOARD_NAME_LEVEL", "")
            # BOARD_NAME_LEVEL 格式: "一级分类-二级分类-三级分类"
            parts = [p.strip() for p in board_level.split("-") if p.strip()] if board_level else []
            sector = parts[1] if len(parts) >= 2 else ""
            concepts = parts[2] if len(parts) >= 3 else ""
            result[code] = {"industry": industry, "sector": sector, "concepts": concepts}
        return result
    except Exception as e:
        logger.warning(f"获取行业数据失败: {e}")
        return {}


class AddWatchlistRequest(BaseModel):
    code: str


@router.get("")
async def get_watchlist():
    """获取自选股列表（含名称、行业、最新价、数据日期、概念、板块）"""
    stocks = storage.get_watchlist_with_info()

    # 对行业为空的股票，从东方财富 F10 API 补充行业/板块/概念数据
    empty_codes = [s["code"] for s in stocks if not s.get("industry")]
    if empty_codes:
        info_map = _fetch_industry_batch(empty_codes)
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
        info_map = _fetch_industry_batch(sector_empty)
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
