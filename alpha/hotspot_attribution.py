"""热点归因分析模块

基于同花顺数据，分析当前市场热点板块、概念轮动、资金流向。
输出结构化 JSON，供 LLM 和前端使用。

数据源：AKShare 同花顺接口
- 概念板块排名：stock_board_concept_name_ths
- 行业板块资金流：stock_sector_fund_flow_rank_ths
- 个股所属概念：stock_board_concept_cons_ths
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pandas as pd
from loguru import logger


async def get_hot_concepts(top_n: int = 20) -> list[dict]:
    """获取当前热门概念板块排名

    Returns:
        [{"name": "锂电池", "change_pct": 3.5, "leader": "宁德时代", "stock_count": 50}, ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, ak.stock_board_concept_name_ths)

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.head(top_n).iterrows():
            records.append({
                "name": str(row.get("概念名称", "") or ""),
                "change_pct": round(float(row.get("涨跌幅", 0) or 0), 2),
                "leader": str(row.get("领涨股票", "") or ""),
                "leader_change": round(float(row.get("领涨股票-涨跌幅", 0) or 0), 2),
                "stock_count": int(row.get("总家数", 0) or 0),
                "up_count": int(row.get("上涨家数", 0) or 0),
                "down_count": int(row.get("下跌家数", 0) or 0),
            })
        return records

    except ImportError:
        logger.warning("AKShare 未安装，热点归因不可用")
        return []
    except Exception as e:
        logger.warning(f"获取热门概念失败: {e}")
        return []


async def get_hot_industries(top_n: int = 20) -> list[dict]:
    """获取当前热门行业板块排名

    Returns:
        [{"name": "半导体", "change_pct": 2.1, "main_net_inflow": 15.3}, ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, ak.stock_board_industry_name_ths)

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.head(top_n).iterrows():
            records.append({
                "name": str(row.get("板块名称", "") or ""),
                "change_pct": round(float(row.get("涨跌幅", 0) or 0), 2),
                "leader": str(row.get("领涨股票", "") or ""),
                "leader_change": round(float(row.get("领涨股票-涨跌幅", 0) or 0), 2),
                "stock_count": int(row.get("总家数", 0) or 0),
            })
        return records

    except Exception as e:
        logger.warning(f"获取热门行业失败: {e}")
        return []


async def get_sector_fund_flow(top_n: int = 20) -> list[dict]:
    """获取行业板块资金流向排名

    Returns:
        [{"name": "半导体", "main_net_inflow": 15.3, "main_net_inflow_pct": 2.1}, ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None, lambda: ak.stock_sector_fund_flow_rank_ths(indicator="今日")
        )

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.head(top_n).iterrows():
            records.append({
                "name": str(row.get("名称", "") or ""),
                "change_pct": round(float(row.get("今日涨跌幅", 0) or 0), 2),
                "main_net_inflow": round(float(row.get("主力净流入-净额", 0) or 0) / 1e8, 2),
                "main_net_inflow_pct": round(float(row.get("主力净流入-净占比", 0) or 0), 2),
            })
        return records

    except Exception as e:
        logger.warning(f"获取行业资金流失败: {e}")
        return []


async def get_concept_for_stock(code: str) -> list[str]:
    """获取个股所属概念板块列表

    Returns:
        ["锂电池", "新能源汽车", ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None, lambda: ak.stock_board_concept_cons_ths(symbol=code)
        )

        if df is None or df.empty:
            return []

        concepts = []
        if "概念名称" in df.columns:
            concepts = df["概念名称"].dropna().tolist()
        return [str(c) for c in concepts]

    except Exception as e:
        logger.warning(f"获取个股概念失败({code}): {e}")
        return []


async def get_hotspot_attribution() -> dict:
    """综合热点归因分析

    Returns:
        {
            "timestamp": "...",
            "hot_concepts": [...],
            "hot_industries": [...],
            "fund_flow": [...],
            "summary": "今日热点：锂电池(+3.5%)、半导体(+2.1%)..."
        }
    """
    concepts, industries, flow = await asyncio.gather(
        get_hot_concepts(10),
        get_hot_industries(10),
        get_sector_fund_flow(10),
        return_exceptions=True,
    )

    # 处理异常
    if isinstance(concepts, Exception):
        logger.warning(f"热点概念获取失败: {concepts}")
        concepts = []
    if isinstance(industries, Exception):
        logger.warning(f"热门行业获取失败: {industries}")
        industries = []
    if isinstance(flow, Exception):
        logger.warning(f"资金流向获取失败: {flow}")
        flow = []

    # 生成摘要
    top3 = [f"{c['name']}({c['change_pct']:+.1f}%)" for c in (concepts or [])[:3]]
    summary = f"今日热点：{'、'.join(top3)}" if top3 else "暂无热点数据"

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hot_concepts": concepts or [],
        "hot_industries": industries or [],
        "fund_flow": flow or [],
        "summary": summary,
    }
