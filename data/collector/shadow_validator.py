"""影子流量对比框架（无感化设计）

在 DATA_SOURCE_MODE="shadow" 模式下：
  - 主请求始终走旧数据源，返回给前端
  - 新数据源在后台异步对比，不阻塞主请求
  - 对比结果写入日志文件，供迁移验证
"""
import json
import os
import time
from pathlib import Path

from loguru import logger

# 对比日志目录
_SHADOW_LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "shadow"
_SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _calc_diff(old_val, new_val, field: str) -> dict | None:
    """计算单字段差异"""
    if old_val is None and new_val is None:
        return None
    if old_val is None or new_val is None:
        return {"field": field, "old": old_val, "new": new_val, "type": "null_mismatch"}

    try:
        old_f = float(old_val)
        new_f = float(new_val)
    except (ValueError, TypeError):
        if str(old_val) != str(new_val):
            return {"field": field, "old": old_val, "new": new_val, "type": "string_diff"}
        return None

    if old_f == 0 and new_f == 0:
        return None

    diff = abs(old_f - new_f)
    base = max(abs(old_f), abs(new_f), 1e-10)
    pct = diff / base * 100

    # 价格差异 >0.01 元 或 >0.1%
    if field in ("price", "open", "high", "low", "pre_close"):
        if diff > 0.01 and pct > 0.1:
            return {"field": field, "old": old_f, "new": new_f, "diff": diff, "pct": round(pct, 2)}

    # 成交量差异 >5%
    if field in ("volume", "amount"):
        if pct > 5:
            return {"field": field, "old": old_f, "new": new_f, "diff": diff, "pct": round(pct, 2)}

    # 名称不匹配
    if field == "name":
        if str(old_val) != str(new_val):
            return {"field": field, "old": old_val, "new": new_val, "type": "name_diff"}

    return None


def validate_quote_consistency(code: str, old_data: dict, new_data: dict) -> list[dict]:
    """对比新旧数据源的行情数据一致性，返回差异列表"""
    diffs = []
    compare_fields = ["price", "open", "high", "low", "pre_close", "volume", "amount", "name"]

    for field in compare_fields:
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        diff = _calc_diff(old_val, new_val, field)
        if diff:
            diffs.append(diff)

    return diffs


def log_shadow_result(code: str, diffs: list[dict], old_data: dict, new_data: dict):
    """将对比结果写入日志文件"""
    if not diffs:
        return

    date_str = time.strftime("%Y%m%d")
    log_file = _SHADOW_LOG_DIR / f"shadow_{date_str}.jsonl"

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "diff_count": len(diffs),
        "diffs": diffs,
        "old_price": old_data.get("price"),
        "new_price": new_data.get("price"),
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.warning(f"[SHADOW] {code}: {len(diffs)} 项差异 — "
                   f"价格 old={old_data.get('price')} new={new_data.get('price')}")


def get_shadow_stats(date_str: str | None = None) -> dict:
    """获取影子对比统计"""
    if date_str is None:
        date_str = time.strftime("%Y%m%d")
    log_file = _SHADOW_LOG_DIR / f"shadow_{date_str}.jsonl"

    if not log_file.exists():
        return {"date": date_str, "total_checks": 0, "total_diffs": 0}

    total_checks = 0
    total_diffs = 0
    codes_with_diffs = set()

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                total_checks += 1
                total_diffs += entry.get("diff_count", 0)
                if entry.get("diff_count", 0) > 0:
                    codes_with_diffs.add(entry.get("code", ""))

    return {
        "date": date_str,
        "total_checks": total_checks,
        "total_diffs": total_diffs,
        "codes_with_diffs": len(codes_with_diffs),
        "consistency_rate": round(1 - len(codes_with_diffs) / max(total_checks, 1), 4),
    }
