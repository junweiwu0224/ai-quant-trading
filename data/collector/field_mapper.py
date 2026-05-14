"""字段映射 + 脏数据清洗管道

将不同数据源（mootdx、腾讯、AKShare）的返回字段统一映射为系统标准格式，
同时清洗空值、停牌、NaN 等异常数据。
"""
import math
from typing import Any, Callable


# ── 清洗函数 ──

def _clean_price(val: Any) -> float | None:
    """价格字段：≤0 / NaN / None → None（标记停牌或无效）"""
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v) or v <= 0:
            return None
        return v
    except (ValueError, TypeError):
        return None


def _clean_volume(val: Any) -> float | None:
    """成交量字段：NaN / None → None，0 保留"""
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


def _clean_volume_lot_to_share(val: Any) -> float | None:
    """成交量字段（手→股）：mootdx 返回手数，需乘 100 转为股数"""
    v = _clean_volume(val)
    if v is not None:
        return v * 100
    return None


def _clean_ratio(val: Any) -> float | None:
    """比率字段（PE/PB/换手率）：NaN / None / 0 → None"""
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v) or v == 0:
            return None
        return v
    except (ValueError, TypeError):
        return None


def _clean_string(val: Any) -> str:
    """字符串字段：None → 空字符串"""
    if val is None:
        return ""
    return str(val).strip()


def _clean_amount(val: Any) -> float | None:
    """成交额字段：NaN / None → None，0 保留"""
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


# ── mootdx 字段映射 ──

# mootdx quotes() 返回的字段 → 系统标准字段 + 清洗函数
# 注意：mootdx 的 vol 字段返回的是"手"（1手=100股），需要转换
MOOTDX_QUOTE_MAP: dict[str, tuple[str, Callable]] = {
    "code":        ("code",          _clean_string),
    "name":        ("name",          _clean_string),
    "price":       ("price",         _clean_price),
    "open":        ("open",          _clean_price),
    "high":        ("high",          _clean_price),
    "low":         ("low",           _clean_price),
    "last_close":  ("pre_close",     _clean_price),
    "vol":         ("volume",        _clean_volume),  # 保留手为单位
    "amount":      ("amount",        _clean_amount),
    "bid1":        ("bid1",          _clean_price),
    "ask1":        ("ask1",          _clean_price),
    "bid_vol1":    ("bid1_vol",      _clean_volume),
    "ask_vol1":    ("ask1_vol",      _clean_volume),
    "bid2":        ("bid2",          _clean_price),
    "ask2":        ("ask2",          _clean_price),
    "bid_vol2":    ("bid2_vol",      _clean_volume),
    "ask_vol2":    ("ask2_vol",      _clean_volume),
    "bid3":        ("bid3",          _clean_price),
    "ask3":        ("ask3",          _clean_price),
    "bid_vol3":    ("bid3_vol",      _clean_volume),
    "ask_vol3":    ("ask3_vol",      _clean_volume),
    "bid4":        ("bid4",          _clean_price),
    "ask4":        ("ask4",          _clean_price),
    "bid_vol4":    ("bid4_vol",      _clean_volume),
    "ask_vol4":    ("ask4_vol",      _clean_volume),
    "bid5":        ("bid5",          _clean_price),
    "ask5":        ("ask5",          _clean_price),
    "bid_vol5":    ("bid5_vol",      _clean_volume),
    "ask_vol5":    ("ask5_vol",      _clean_volume),
}


def map_mootdx_quote(row: dict) -> dict:
    """将 mootdx quotes() 返回的一行数据映射为系统标准格式，同时清洗脏数据"""
    result = {}
    for src_key, (dst_key, cleaner) in MOOTDX_QUOTE_MAP.items():
        raw = row.get(src_key)
        result[dst_key] = cleaner(raw)
    # 计算涨跌幅
    price = result.get("price")
    pre_close = result.get("pre_close")
    if price and pre_close and pre_close > 0:
        result["change_pct"] = round((price - pre_close) / pre_close * 100, 2)
    else:
        result["change_pct"] = None
    return result


# ── 腾讯 K线字段映射 ──

TENCENT_KLINE_MAP: dict[str, tuple[str, Callable]] = {
    "0": ("date",   _clean_string),
    "1": ("open",   _clean_price),
    "2": ("close",  _clean_price),
    "3": ("high",   _clean_price),
    "4": ("low",    _clean_price),
    "5": ("volume", _clean_volume),
}


def map_tencent_kline(row: list) -> dict:
    """将腾讯 K线数组映射为系统标准格式"""
    result = {}
    for idx, (dst_key, cleaner) in TENCENT_KLINE_MAP.items():
        raw = row[int(idx)] if int(idx) < len(row) else None
        result[dst_key] = cleaner(raw)
    return result


# ── mootdx K线字段映射 ──

MOOTDX_KLINE_MAP: dict[str, tuple[str, Callable]] = {
    "open":     ("open",   _clean_price),
    "close":    ("close",  _clean_price),
    "high":     ("high",   _clean_price),
    "low":      ("low",    _clean_price),
    "vol":      ("volume", _clean_volume),
    "amount":   ("amount", _clean_amount),
}


def map_mootdx_kline(row: dict) -> dict:
    """将 mootdx bars() 返回的一行映射为系统标准格式"""
    result = {}
    for src_key, (dst_key, cleaner) in MOOTDX_KLINE_MAP.items():
        raw = row.get(src_key)
        result[dst_key] = cleaner(raw)
    return result
