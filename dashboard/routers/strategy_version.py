"""策略版本管理 & 回测结果持久化 API"""
import json
from datetime import datetime
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from typing import Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from data.storage.storage import BacktestRecord, StrategyVersion, DataStorage

router = APIRouter()
storage = DataStorage()


# ── 策略版本管理 ──


class VersionCreateRequest(BaseModel):
    strategy_name: str
    label: str = ""
    description: str = ""
    params: dict = {}
    code: str = ""


class VersionRollbackRequest(BaseModel):
    strategy_name: str
    version: int


@router.get("/versions/{strategy_name}")
async def list_versions(strategy_name: str):
    """获取策略的所有版本"""
    session = storage._get_session()
    try:
        versions = (
            session.query(StrategyVersion)
            .filter(StrategyVersion.strategy_name == strategy_name)
            .order_by(StrategyVersion.version.desc())
            .all()
        )
        return [
            {
                "id": v.id,
                "strategy_name": v.strategy_name,
                "version": v.version,
                "label": v.label,
                "description": v.description,
                "params": json.loads(v.params) if v.params else {},
                "code": v.code,
                "created_at": v.created_at,
                "is_current": bool(v.is_current),
            }
            for v in versions
        ]
    finally:
        session.close()


@router.post("/versions/save")
async def save_version(req: VersionCreateRequest):
    """保存当前策略为新版本"""
    session = storage._get_session()
    try:
        # 获取当前最大版本号
        latest = (
            session.query(StrategyVersion)
            .filter(StrategyVersion.strategy_name == req.strategy_name)
            .order_by(StrategyVersion.version.desc())
            .first()
        )
        new_version = (latest.version + 1) if latest else 1

        # 将旧版本标记为非当前
        if latest:
            session.query(StrategyVersion).filter(
                StrategyVersion.strategy_name == req.strategy_name,
                StrategyVersion.is_current == 1,
            ).update({"is_current": 0})

        record = StrategyVersion(
            strategy_name=req.strategy_name,
            version=new_version,
            label=req.label or f"v{new_version}",
            description=req.description,
            params=json.dumps(req.params, ensure_ascii=False),
            code=req.code,
            created_at=now_beijing().strftime("%Y-%m-%d %H:%M:%S"),
            is_current=1,
        )
        session.add(record)
        session.commit()

        logger.info(f"保存策略版本: {req.strategy_name} v{new_version}")
        return {
            "id": record.id,
            "strategy_name": req.strategy_name,
            "version": new_version,
            "label": record.label,
            "created_at": record.created_at,
        }
    finally:
        session.close()


@router.post("/versions/rollback")
async def rollback_version(req: VersionRollbackRequest):
    """回滚到指定版本"""
    session = storage._get_session()
    try:
        target = (
            session.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_name == req.strategy_name,
                StrategyVersion.version == req.version,
            )
            .first()
        )
        if not target:
            return {"error": f"版本 v{req.version} 不存在"}

        # 取消当前版本标记
        session.query(StrategyVersion).filter(
            StrategyVersion.strategy_name == req.strategy_name,
            StrategyVersion.is_current == 1,
        ).update({"is_current": 0})

        # 标记目标版本为当前
        target.is_current = 1
        session.commit()

        logger.info(f"回滚策略: {req.strategy_name} -> v{req.version}")
        return {
            "strategy_name": req.strategy_name,
            "version": req.version,
            "params": json.loads(target.params) if target.params else {},
            "code": target.code,
        }
    finally:
        session.close()


@router.get("/versions/{strategy_name}/diff")
async def diff_versions(strategy_name: str, v1: int, v2: int):
    """比较两个版本的差异"""
    session = storage._get_session()
    try:
        ver1 = (
            session.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_name == strategy_name,
                StrategyVersion.version == v1,
            )
            .first()
        )
        ver2 = (
            session.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_name == strategy_name,
                StrategyVersion.version == v2,
            )
            .first()
        )
        if not ver1 or not ver2:
            return {"error": "版本不存在"}

        params1 = json.loads(ver1.params) if ver1.params else {}
        params2 = json.loads(ver2.params) if ver2.params else {}

        # 参数差异
        all_keys = set(params1.keys()) | set(params2.keys())
        param_diff = {}
        for k in sorted(all_keys):
            val1 = params1.get(k)
            val2 = params2.get(k)
            if val1 != val2:
                param_diff[k] = {"v" + str(v1): val1, "v" + str(v2): val2}

        # 代码差异（简化：只报告是否相同）
        code_changed = (ver1.code or "") != (ver2.code or "")

        return {
            "strategy_name": strategy_name,
            "v1": {"version": v1, "label": ver1.label, "created_at": ver1.created_at},
            "v2": {"version": v2, "label": ver2.label, "created_at": ver2.created_at},
            "param_diff": param_diff,
            "code_changed": code_changed,
        }
    finally:
        session.close()


# ── 回测结果持久化 ──


class RecordSaveRequest(BaseModel):
    strategy_name: str
    label: str = ""
    codes: list[str] = []
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 100000
    result: dict = {}


@router.post("/records/save")
async def save_record(req: RecordSaveRequest):
    """保存回测结果"""
    r = req.result
    session = storage._get_session()
    try:
        record = BacktestRecord(
            strategy_name=req.strategy_name,
            label=req.label or f"{req.strategy_name}_{now_beijing().strftime('%m%d_%H%M')}",
            codes=json.dumps(req.codes),
            start_date=req.start_date,
            end_date=req.end_date,
            initial_cash=req.initial_cash,
            total_return=r.get("total_return"),
            annual_return=r.get("annual_return"),
            max_drawdown=r.get("max_drawdown"),
            sharpe_ratio=r.get("sharpe_ratio"),
            win_rate=r.get("win_rate"),
            total_trades=r.get("total_trades"),
            params=json.dumps(r.get("params", {}), ensure_ascii=False),
            result_json=json.dumps(r, ensure_ascii=False),
            created_at=now_beijing().strftime("%Y-%m-%d %H:%M:%S"),
        )
        session.add(record)
        session.commit()

        logger.info(f"保存回测记录: {record.label}")
        return {"id": record.id, "label": record.label}
    finally:
        session.close()


@router.get("/records")
async def list_records(strategy_name: Optional[str] = None, limit: int = 20):
    """获取回测历史记录"""
    session = storage._get_session()
    try:
        query = session.query(BacktestRecord).order_by(BacktestRecord.id.desc())
        if strategy_name:
            query = query.filter(BacktestRecord.strategy_name == strategy_name)
        records = query.limit(limit).all()

        return [
            {
                "id": r.id,
                "strategy_name": r.strategy_name,
                "label": r.label,
                "codes": json.loads(r.codes) if r.codes else [],
                "start_date": r.start_date,
                "end_date": r.end_date,
                "initial_cash": r.initial_cash,
                "total_return": r.total_return,
                "annual_return": r.annual_return,
                "max_drawdown": r.max_drawdown,
                "sharpe_ratio": r.sharpe_ratio,
                "win_rate": r.win_rate,
                "total_trades": r.total_trades,
                "created_at": r.created_at,
            }
            for r in records
        ]
    finally:
        session.close()


@router.get("/records/{record_id}")
async def get_record(record_id: int):
    """获取单条回测记录详情"""
    session = storage._get_session()
    try:
        r = session.query(BacktestRecord).filter(BacktestRecord.id == record_id).first()
        if not r:
            return {"error": "记录不存在"}

        return {
            "id": r.id,
            "strategy_name": r.strategy_name,
            "label": r.label,
            "codes": json.loads(r.codes) if r.codes else [],
            "start_date": r.start_date,
            "end_date": r.end_date,
            "initial_cash": r.initial_cash,
            "total_return": r.total_return,
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "params": json.loads(r.params) if r.params else {},
            "result": json.loads(r.result_json) if r.result_json else {},
            "created_at": r.created_at,
        }
    finally:
        session.close()


@router.delete("/records/{record_id}")
async def delete_record(record_id: int):
    """删除回测记录"""
    session = storage._get_session()
    try:
        r = session.query(BacktestRecord).filter(BacktestRecord.id == record_id).first()
        if not r:
            return {"error": "记录不存在"}
        session.delete(r)
        session.commit()
        return {"deleted": record_id}
    finally:
        session.close()


@router.post("/records/compare")
async def compare_records(record_ids: list[int]):
    """对比多条回测记录"""
    session = storage._get_session()
    try:
        records = (
            session.query(BacktestRecord)
            .filter(BacktestRecord.id.in_(record_ids))
            .all()
        )
        return [
            {
                "id": r.id,
                "label": r.label,
                "strategy_name": r.strategy_name,
                "total_return": r.total_return,
                "annual_return": r.annual_return,
                "max_drawdown": r.max_drawdown,
                "sharpe_ratio": r.sharpe_ratio,
                "win_rate": r.win_rate,
                "total_trades": r.total_trades,
                "params": json.loads(r.params) if r.params else {},
            }
            for r in records
        ]
    finally:
        session.close()
