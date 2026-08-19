"""宏观指标因子

数据源：东方财富宏观数据 API
因子：
- shibor: 上海银行间同业拆借利率
- treasury_10y: 10 年期国债收益率
- m2_growth: M2 增速
- social_financing: 社融规模

全市场统一赋值，作为控制变量。
"""
from __future__ import annotations

import time

from loguru import logger

from data.collector.http_client import fetch_json


def fetch_macro_factors() -> dict[str, float]:
    """获取最新宏观指标"""
    result = {
        "shibor_1w": 0, "shibor_1m": 0,
        "treasury_10y": 0, "treasury_1y": 0,
        "m2_growth": 0, "social_financing": 0,
    }

    # SHIBOR
    try:
        shibor_url = (
            "https://datacenter.eastmoney.com/securities/api/data/get"
            "?type=RPT_ECONOMY_SHIBOR&sty=ALL"
            "&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(shibor_url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if data.get("result") and data["result"].get("data"):
            latest = data["result"]["data"][0]
            result["shibor_1w"] = round(float(latest.get("W1", 0) or 0), 4)
            result["shibor_1m"] = round(float(latest.get("M1", 0) or 0), 4)
    except Exception as e:
        logger.warning(f"获取 SHIBOR 失败: {e}")

    # 国债收益率
    try:
        bond_url = (
            "https://datacenter.eastmoney.com/securities/api/data/get"
            "?type=RPT_ECONOMY_BOND_YIELD&sty=ALL"
            "&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(bond_url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if data.get("result") and data["result"].get("data"):
            latest = data["result"]["data"][0]
            result["treasury_10y"] = round(float(latest.get("EMM00588704", 0) or 0), 4)
            result["treasury_1y"] = round(float(latest.get("EMM00166469", 0) or 0), 4)
    except Exception as e:
        logger.warning(f"获取国债收益率失败: {e}")

    # M2 增速
    try:
        m2_url = (
            "https://datacenter.eastmoney.com/securities/api/data/get"
            "?type=RPT_ECONOMY_CURRENCY_SUPPLY&sty=ALL"
            "&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(m2_url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if data.get("result") and data["result"].get("data"):
            latest = data["result"]["data"][0]
            result["m2_growth"] = round(float(latest.get("M2_YOY", 0) or 0), 4)
    except Exception as e:
        logger.warning(f"获取 M2 数据失败: {e}")

    # 社融
    try:
        sf_url = (
            "https://datacenter.eastmoney.com/securities/api/data/get"
            "?type=RPT_ECONOMY_SOCIAL_FINANCE&sty=ALL"
            "&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(sf_url, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if data.get("result") and data["result"].get("data"):
            latest = data["result"]["data"][0]
            result["social_financing"] = round(float(latest.get("CURRENT_VALUE", 0) or 0), 4)
    except Exception as e:
        logger.warning(f"获取社融数据失败: {e}")

    return result
