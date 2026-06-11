"""AI 信号 legacy adapter 路由

主仪表盘 (8001) 保留 /api/qlib/* 兼容路径，
实际运行时语义为 Signal Engine / AI 信号缓存。
"""

import json
from pathlib import Path

import httpx
from fastapi import APIRouter
from loguru import logger

from config.settings import QLIB_SERVICE_URL, QLIB_SYNC_STATUS
from utils.db import get_connection

router = APIRouter()

PRED_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "qlib" / "predictions_cache.json"
SYNC_STATUS_FILE = QLIB_SYNC_STATUS
DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "quant.db"
QLIB_TRAIN_URL = f"{QLIB_SERVICE_URL.rstrip('/')}/train"
QLIB_TRAIN_STATUS_URL = f"{QLIB_SERVICE_URL.rstrip('/')}/train/status"
LEGACY_QLIB_HEALTH_META = {
    "legacy": True,
    "adapter_for": "signals",
    "primary_endpoint": "/api/signals/health",
}
_PREDICTIONS_CACHE: dict[str, object] = {
    "path": None,
    "mtime_ns": None,
    "size": None,
    "data": {},
}


def _load_predictions() -> dict:
    """读取预测缓存文件"""
    if not PRED_CACHE_FILE.exists():
        _PREDICTIONS_CACHE.update({"path": None, "mtime_ns": None, "size": None, "data": {}})
        return {}
    try:
        stat = PRED_CACHE_FILE.stat()
        cache_path = str(PRED_CACHE_FILE)
        if (
            _PREDICTIONS_CACHE.get("path") == cache_path
            and _PREDICTIONS_CACHE.get("mtime_ns") == stat.st_mtime_ns
            and _PREDICTIONS_CACHE.get("size") == stat.st_size
        ):
            cached = _PREDICTIONS_CACHE.get("data")
            return cached if isinstance(cached, dict) else {}
        data = json.loads(PRED_CACHE_FILE.read_text(encoding="utf-8"))
        if "predictions" in data:
            predictions = data["predictions"]
        else:
            predictions = data
        predictions = predictions if isinstance(predictions, dict) else {}
        _PREDICTIONS_CACHE.update(
            {
                "path": cache_path,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "data": predictions,
            }
        )
        return predictions
    except Exception as e:
        logger.warning(f"读取预测缓存失败: {e}")
        return {}


def _load_sync_status() -> dict:
    """读取 AI 信号覆盖同步状态（兼容旧同步状态文件）。"""
    if not SYNC_STATUS_FILE.exists():
        return {}
    try:
        payload = json.loads(SYNC_STATUS_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        errors = [
            {"code": str(item.get("code") or ""), "error": str(item.get("error") or "")}
            for item in items
            if isinstance(item, dict) and item.get("success") is False and item.get("error")
        ][:5]
        return {
            "source": payload.get("source"),
            "success": payload.get("success"),
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
            "duration_sec": payload.get("duration_sec"),
            "target_count": payload.get("target_count"),
            "success_count": payload.get("success_count"),
            "fail_count": payload.get("fail_count"),
            "prediction_success": payload.get("prediction_success"),
            "prediction_latest_date": payload.get("prediction_latest_date"),
            "prediction_total": payload.get("prediction_total"),
            "prediction_message": payload.get("prediction_message"),
            "last_error_samples": errors,
        }
    except Exception as exc:
        logger.warning(f"读取 AI 信号同步状态失败: {exc}")
        return {}


def _enrich_with_stock_info(codes: list[str]) -> dict[str, dict]:
    """从数据库批量获取股票名称、行业、最新收盘价

    缓存通常使用六位裸码，数据库历史数据可能使用 sh/sz 前缀。
    """
    result: dict[str, dict] = {}
    if not DB_PATH.exists() or not codes:
        return result

    def _plain_code(code: str) -> str:
        raw = str(code or "").strip()
        if raw[:2].lower() in {"sh", "sz"}:
            raw = raw[2:]
        return raw if len(raw) == 6 and raw.isdigit() else str(code or "").strip()

    def _storage_code_candidates(code: str) -> list[str]:
        plain = _plain_code(code)
        if not plain or len(plain) != 6 or not plain.isdigit():
            return [plain] if plain else []
        if plain.startswith("6"):
            return [plain, f"sh{plain}"]
        if plain.startswith(("0", "3", "9")):
            return [plain, f"sz{plain}", f"sh{plain}"]
        return [plain]

    requested_by_storage_code: dict[str, str] = {}
    for code in codes:
        plain = _plain_code(code)
        requested_by_storage_code[str(code)] = plain
        for candidate in _storage_code_candidates(plain):
            requested_by_storage_code[candidate] = plain
    query_codes = list(requested_by_storage_code.keys())

    conn = get_connection(str(DB_PATH), readonly=True)
    try:
        cur = conn.cursor()

        # 批量查询名称和行业
        placeholders = ",".join("?" * len(query_codes))
        cur.execute(
            f"SELECT code, name, industry FROM stock_info WHERE code IN ({placeholders})",
            query_codes,
        )
        for row in cur.fetchall():
            plain = requested_by_storage_code.get(row["code"], _plain_code(row["code"]))
            industry = str(row["industry"] or "").strip()
            result[plain] = {
                "name": row["name"],
                "industry": industry or "--",
                "industry_source": "stock_info" if industry else "missing",
            }

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
            query_codes,
        )
        for row in cur.fetchall():
            plain = requested_by_storage_code.get(row["code"], _plain_code(row["code"]))
            if plain in result:
                result[plain]["price"] = round(row["close"], 2)
                result[plain]["volume"] = row["volume"]
                result[plain]["amount"] = row["amount"]

        missing_industry_codes = [
            code
            for code in {_plain_code(item) for item in codes}
            if code and (not result.get(code, {}).get("industry") or result.get(code, {}).get("industry") == "--")
        ]
        if missing_industry_codes:
            try:
                from data.storage.storage import DataStorage

                storage = DataStorage(db_url=f"sqlite:///{DB_PATH}")
                for plain in missing_industry_codes:
                    snapshot = storage.get_latest_data_snapshot(plain, "valuation") or {}
                    payload = snapshot.get("payload") if isinstance(snapshot, dict) else {}
                    if not isinstance(payload, dict):
                        continue
                    industry = str(payload.get("industry") or "").strip()
                    sector = str(payload.get("sector") or "").strip()
                    name = str(payload.get("name") or payload.get("stock_name") or "").strip()
                    if not industry and not sector and not name:
                        continue
                    info = result.setdefault(plain, {"name": plain, "industry": "--", "industry_source": "missing"})
                    if name and (not info.get("name") or info.get("name") == plain):
                        info["name"] = name
                    if industry:
                        info["industry"] = industry
                        info["industry_source"] = "valuation_snapshot"
                    if sector:
                        info["sector"] = sector
            except Exception as exc:
                logger.debug(f"估值快照补齐股票行业失败: {exc}")
    except Exception as e:
        logger.warning(f"查询股票信息失败: {e}")
    finally:
        conn.close()

    return result


@router.get("/top")
async def get_top_predictions(top_n: int = 10):
    """获取 AI 信号池 Top N

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
        from data.signals.engine import get_signal_records

        records, meta = get_signal_records(
            provider="local_momentum",
            top_n=top_n,
            cache_path=PRED_CACHE_FILE,
        )
        if not records:
            return {
                "success": True,
                "predictions": [],
                "date": meta.get("latest_date"),
                "total": meta.get("total") or 0,
                "provider": meta.get("provider") or "local_momentum",
                "model_version": meta.get("model_version") or "",
                "legacy": True,
            }

        info_map = _enrich_with_stock_info([record.code for record in records])
        predictions = []
        for record in records:
            info = info_map.get(record.code, {})
            row = record.to_dict(legacy_keys=True)
            row.update({
                "name": info.get("name", record.code),
                "industry": info.get("industry", "--"),
                "price": info.get("price"),
                "volume": info.get("volume"),
                "amount": info.get("amount"),
            })
            predictions.append(row)

        return {
            "success": True,
            "predictions": predictions,
            "signals": predictions,
            "date": records[0].date,
            "total": meta.get("total") or len(predictions),
            "provider": meta.get("provider") or "local_momentum",
            "model_version": meta.get("model_version") or "",
            "raw_source": meta.get("raw_source") or "legacy_qlib",
            "legacy": True,
        }
    except Exception as e:
        logger.error(f"获取预测数据失败: {e}")
        return {"success": False, "predictions": [], "date": None, "total": 0, "error": str(e)}


@router.get("/consistency")
async def get_consistency(top_n: int = 50):
    """计算 AI 信号一致性 (IC_adj = Score / σ(Historical))

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
    """AI 信号兼容接口健康检查

    检查 AI 信号缓存文件是否存在且在24小时内更新过。
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
            return {
                "success": True,
                "status": "offline",
                **LEGACY_QLIB_HEALTH_META,
                "last_update": None,
                "cache_age_hours": None,
                "cache_exists": False,
                "cache_path": str(PRED_CACHE_FILE),
                "prediction_total": 0,
                "service_url": QLIB_SERVICE_URL,
                "sync_status": _load_sync_status(),
            }

        import time
        mtime = PRED_CACHE_FILE.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600

        # 读取最新日期
        prediction_total = 0
        try:
            data = json.loads(PRED_CACHE_FILE.read_text(encoding="utf-8"))
            preds = data.get("predictions", data)
            latest_date = max(preds.keys()) if isinstance(preds, dict) and preds else None
            latest_preds = preds.get(latest_date, {}) if latest_date and isinstance(preds, dict) else {}
            prediction_total = len(latest_preds) if isinstance(latest_preds, dict) else 0
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
            **LEGACY_QLIB_HEALTH_META,
            "last_update": latest_date,
            "cache_age_hours": round(age_hours, 1),
            "cache_exists": True,
            "cache_path": str(PRED_CACHE_FILE),
            "prediction_total": prediction_total,
            "service_url": QLIB_SERVICE_URL,
            "sync_status": _load_sync_status(),
        }
    except Exception as e:
        logger.error(f"AI 信号兼容接口健康检查失败: {e}")
        return {
            "success": True,
            "status": "offline",
            **LEGACY_QLIB_HEALTH_META,
            "last_update": None,
            "cache_age_hours": None,
            "cache_exists": False,
            "cache_path": str(PRED_CACHE_FILE),
            "prediction_total": 0,
            "service_url": QLIB_SERVICE_URL,
            "sync_status": _load_sync_status(),
        }


@router.post("/train")
async def qlib_train():
    """触发 AI 信号模型刷新（保留 /api/qlib/train 兼容路径）"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(QLIB_TRAIN_URL)
            return resp.json()
    except Exception as e:
        logger.error(f"调用 AI 信号模型服务失败: {e}")
        return {"success": False, "message": f"AI 信号模型服务不可用: {e}"}


@router.get("/train/status")
async def qlib_train_status():
    """查询 AI 信号模型刷新状态（保留 /api/qlib/train/status 兼容路径）"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(QLIB_TRAIN_STATUS_URL)
            return resp.json()
    except Exception as e:
        return {"training": False, "error": str(e)}
