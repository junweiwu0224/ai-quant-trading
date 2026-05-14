"""qlib 预测数据代理路由

主仪表盘 (8001) 代理访问 qlib 预测缓存，
避免前端直接跨端口请求 qlib 微服务 (8002)。
"""

import json
from pathlib import Path

import httpx
from fastapi import APIRouter
from loguru import logger

from config.settings import QLIB_SERVICE_URL
from utils.db import get_connection

router = APIRouter()

PRED_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "qlib" / "predictions_cache.json"
DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "quant.db"
QLIB_TRAIN_URL = f"{QLIB_SERVICE_URL.rstrip('/')}/train"
QLIB_TRAIN_STATUS_URL = f"{QLIB_SERVICE_URL.rstrip('/')}/train/status"


def _load_predictions() -> dict:
    """读取预测缓存文件"""
    if not PRED_CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(PRED_CACHE_FILE.read_text(encoding="utf-8"))
        if "predictions" in data:
            return data["predictions"]
        return data
    except Exception as e:
        logger.warning(f"读取预测缓存失败: {e}")
        return {}


def _enrich_with_stock_info(codes: list[str]) -> dict[str, dict]:
    """从数据库批量获取股票名称、行业、最新收盘价

    codes 格式统一为 sh/sz 前缀 (sz002049)。
    """
    result: dict[str, dict] = {}
    if not DB_PATH.exists() or not codes:
        return result

    conn = get_connection(str(DB_PATH), readonly=True)
    try:
        cur = conn.cursor()

        # 批量查询名称和行业
        placeholders = ",".join("?" * len(codes))
        cur.execute(
            f"SELECT code, name, industry FROM stock_info WHERE code IN ({placeholders})",
            codes,
        )
        for row in cur.fetchall():
            result[row["code"]] = {"name": row["name"], "industry": row["industry"] or "--"}

        # 批量查询每只股票的最新收盘价、成交量、成交额
        cur.execute(
            f"""SELECT s.code, s.close, s.volume, s.amount
                FROM stock_daily s
                INNER JOIN (
                    SELECT code, MAX(date) AS max_date
                    FROM stock_daily
                    WHERE code IN ({placeholders})
                    GROUP BY code
                ) latest ON s.code = latest.code AND s.date = latest.max_date""",
            codes,
        )
        for row in cur.fetchall():
            if row["code"] in result:
                result[row["code"]]["price"] = round(row["close"], 2)
                result[row["code"]]["volume"] = row["volume"]
                result[row["code"]]["amount"] = row["amount"]
    except Exception as e:
        logger.warning(f"查询股票信息失败: {e}")
    finally:
        conn.close()

    return result


@router.get("/top")
async def get_top_predictions(top_n: int = 10):
    """获取 AI 预测池 Top N

    返回格式:
    {
        "success": true,
        "predictions": [
            {"code": "000001", "name": "平安银行", "score": 0.73,
             "industry": "金融业", "price": 11.37},
            ...
        ],
        "date": "2026-05-07",
        "total": 100
    }
    """
    try:
        cache = _load_predictions()
        if not cache:
            return {"success": True, "predictions": [], "date": None, "total": 0}

        # 取最新日期
        latest_date = max(cache.keys())
        preds = cache[latest_date]

        # 按分数降序排列，取 top_n
        sorted_preds = sorted(preds.items(), key=lambda x: x[1], reverse=True)[:top_n]
        codes = [code for code, _ in sorted_preds]

        # 批量关联股票信息
        info_map = _enrich_with_stock_info(codes)

        predictions = []
        for code, score in sorted_preds:
            info = info_map.get(code, {})
            predictions.append({
                "code": code,
                "name": info.get("name", code),
                "score": round(score, 6),
                "industry": info.get("industry", "--"),
                "price": info.get("price"),
                "volume": info.get("volume"),
                "amount": info.get("amount"),
            })

        return {
            "success": True,
            "predictions": predictions,
            "date": latest_date,
            "total": len(preds),
        }
    except Exception as e:
        logger.error(f"获取预测数据失败: {e}")
        return {"success": False, "predictions": [], "date": None, "total": 0, "error": str(e)}


@router.get("/consistency")
async def get_consistency(top_n: int = 50):
    """计算 Qlib 预测一致性 (IC_adj = Score / σ(Historical))

    返回格式:
    {
        "success": true,
        "items": [
            {"code": "000001", "score": 0.73, "hist_std": 0.12,
             "ic_adj": 6.08, "diamond": true, "appearances": 45},
            ...
        ],
        "date": "2026-05-06"
    }
    """
    try:
        cache = _load_predictions()
        if not cache:
            return {"success": True, "items": [], "date": None}

        latest_date = max(cache.keys())
        latest_preds = cache[latest_date]
        if not latest_preds:
            return {"success": True, "items": [], "date": latest_date}

        # 取最新日期 Top N
        sorted_latest = sorted(latest_preds.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_codes = {code for code, _ in sorted_latest}

        # 统计每个 Top 股票的历史分数
        from collections import defaultdict
        import math

        history: dict[str, list[float]] = defaultdict(list)
        for date, preds in cache.items():
            if date == latest_date:
                continue
            if isinstance(preds, dict):
                for code, score in preds.items():
                    if code in top_codes:
                        history[code].append(float(score))

        # 批量获取股票信息
        codes = [code for code, _ in sorted_latest]
        info_map = _enrich_with_stock_info(codes)

        items = []
        for code, score in sorted_latest:
            hist = history.get(code, [])
            hist_std = 0.0
            ic_adj = 0.0
            diamond = False

            if len(hist) >= 3:
                mean_h = sum(hist) / len(hist)
                variance = sum((x - mean_h) ** 2 for x in hist) / len(hist)
                hist_std = math.sqrt(variance)
                if hist_std > 0:
                    ic_adj = round(score / hist_std, 4)
                    # Diamond: IC_adj > 2 表示高一致性
                    diamond = ic_adj > 2.0

            info = info_map.get(code, {})
            items.append({
                "code": code,
                "name": info.get("name", code),
                "score": round(score, 6),
                "industry": info.get("industry", "--"),
                "price": info.get("price"),
                "amount": info.get("amount"),
                "hist_std": round(hist_std, 6),
                "ic_adj": ic_adj,
                "diamond": diamond,
                "appearances": len(hist),
            })

        return {"success": True, "items": items, "date": latest_date}
    except Exception as e:
        logger.error(f"计算一致性失败: {e}")
        return {"success": False, "items": [], "date": None, "error": str(e)}


@router.get("/health")
async def qlib_health():
    """Qlib 服务健康检查

    检查预测缓存文件是否存在且在24小时内更新过。
    返回格式:
    {
        "success": true,
        "status": "online" | "stale" | "offline",
        "last_update": "2026-05-06",
        "cache_age_hours": 2.5
    }
    """
    try:
        if not PRED_CACHE_FILE.exists():
            return {"success": True, "status": "offline", "last_update": None, "cache_age_hours": None}

        import time
        mtime = PRED_CACHE_FILE.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600

        # 读取最新日期
        try:
            data = json.loads(PRED_CACHE_FILE.read_text(encoding="utf-8"))
            preds = data.get("predictions", data)
            latest_date = max(preds.keys()) if isinstance(preds, dict) and preds else None
        except Exception:
            latest_date = None

        if age_hours < 24:
            status = "online"
        elif age_hours < 72:
            status = "stale"
        else:
            status = "offline"

        return {
            "success": True,
            "status": status,
            "last_update": latest_date,
            "cache_age_hours": round(age_hours, 1),
        }
    except Exception as e:
        logger.error(f"Qlib 健康检查失败: {e}")
        return {"success": True, "status": "offline", "last_update": None, "cache_age_hours": None}


@router.post("/train")
async def qlib_train():
    """触发 qlib 模型训练（代理到 qlib 微服务）"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(QLIB_TRAIN_URL)
            return resp.json()
    except Exception as e:
        logger.error(f"调用 qlib 训练服务失败: {e}")
        return {"success": False, "message": f"qlib 服务不可用: {e}"}


@router.get("/train/status")
async def qlib_train_status():
    """查询 qlib 训练状态"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(QLIB_TRAIN_STATUS_URL)
            return resp.json()
    except Exception as e:
        return {"training": False, "error": str(e)}
