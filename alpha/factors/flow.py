"""资金流因子

- 北向资金因子：持股比例变化、连续 N 日净买入、持仓市值变化
- 龙虎榜因子：机构净买入、游资动向

数据源：东方财富 datacenter API
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from data.collector.http_client import fetch_json


# ── 北向资金因子 ──

def fetch_northbound_factors(code: str, days: int = 30) -> dict[str, float]:
    """获取北向资金因子

    返回：
    - nb_hold_ratio: 最新持股比例 (%)
    - nb_hold_ratio_change: 近 N 日持股比例变化
    - nb_consecutive_buy: 连续净买入天数
    - nb_net_buy_sum: 近 N 日累计净买入额 (亿)
    """
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_MUTUAL_STOCK_NORTHSTA"
            f"&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)(INTERVAL_TYPE=%221%22)"
            f"&p=1&ps={days}&sr=-1&st=TRADE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})

        items = []
        api_result = data.get("result", {})
        if api_result and api_result.get("data"):
            for row in api_result["data"]:
                items.append({
                    "date": str(row.get("TRADE_DATE", ""))[:10],
                    "hold_ratio": float(row.get("FREE_SHARES_RATIO", 0) or 0),
                    "change_shares": float(row.get("ADD_SHARES_REPAIR", 0) or 0),
                    "market_cap": float(row.get("HOLD_MARKET_CAP", 0) or 0),
                })

        if not items:
            return {
                "nb_hold_ratio": 0, "nb_hold_ratio_change": 0,
                "nb_consecutive_buy": 0, "nb_net_buy_sum": 0,
            }

        latest = items[0]
        hold_ratio = latest["hold_ratio"]

        # 持股比例变化
        oldest_ratio = items[-1]["hold_ratio"] if len(items) > 1 else hold_ratio
        ratio_change = hold_ratio - oldest_ratio

        # 连续净买入天数
        consecutive = 0
        for item in items:
            if item["change_shares"] > 0:
                consecutive += 1
            else:
                break

        # 累计净买入额
        net_buy_sum = sum(item["change_shares"] for item in items if item["change_shares"] > 0)
        net_buy_sum = round(net_buy_sum / 1e8, 4)  # 转为亿

        return {
            "nb_hold_ratio": round(hold_ratio, 4),
            "nb_hold_ratio_change": round(ratio_change, 4),
            "nb_consecutive_buy": consecutive,
            "nb_net_buy_sum": net_buy_sum,
        }
    except Exception as e:
        logger.warning(f"获取 {code} 北向因子失败: {e}")
        return {
            "nb_hold_ratio": 0, "nb_hold_ratio_change": 0,
            "nb_consecutive_buy": 0, "nb_net_buy_sum": 0,
        }


# ── 龙虎榜因子 ──

def fetch_dragon_tiger_factors(code: str, days: int = 30) -> dict[str, float]:
    """获取龙虎榜因子

    返回：
    - dt_count: 近 N 日上榜次数
    - dt_net_buy: 近 N 日机构净买入额 (亿)
    - dt_hot_score: 热度评分（上榜次数 × 净买入方向）
    """
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_BILLBOARD_DAILYDETAILS&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps={days * 3}&sr=-1&st=TRADE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})

        items = []
        api_result = data.get("result", {})
        if api_result and api_result.get("data"):
            for row in api_result["data"]:
                items.append({
                    "date": str(row.get("TRADE_DATE", ""))[:10],
                    "buy_amount": float(row.get("BUY", 0) or 0),
                    "sell_amount": float(row.get("SELL", 0) or 0),
                    "net_amount": float(row.get("NET", 0) or 0),
                    "reason": row.get("EXPLAIN", "") or "",
                })

        if not items:
            return {"dt_count": 0, "dt_net_buy": 0, "dt_hot_score": 0}

        # 按日期去重
        dates = set(item["date"] for item in items)
        count = len(dates)

        # 净买入
        total_net = sum(item["net_amount"] for item in items)
        net_buy = round(total_net / 1e8, 4)

        # 热度评分
        hot_score = count * (1 if total_net > 0 else -1)

        return {
            "dt_count": count,
            "dt_net_buy": net_buy,
            "dt_hot_score": hot_score,
        }
    except Exception as e:
        logger.warning(f"获取 {code} 龙虎榜因子失败: {e}")
        return {"dt_count": 0, "dt_net_buy": 0, "dt_hot_score": 0}


def compute_flow_factors(code: str, northbound_days: int = 30, dragon_days: int = 30) -> dict[str, float]:
    """计算全部资金流因子"""
    nb = fetch_northbound_factors(code, northbound_days)
    dt = fetch_dragon_tiger_factors(code, dragon_days)
    return {**nb, **dt}
