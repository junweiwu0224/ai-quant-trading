"""实时行情 WebSocket 推送"""
import asyncio
import json
import os
from config.datetime_utils import now_beijing_iso

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from uvicorn.protocols.utils import ClientDisconnected

from agentic.repository import DEFAULT_WORKSPACE_ID, normalize_workspace_id
from dashboard.auth import close_unauthorized_websocket, is_valid_api_key, websocket_api_key
from dashboard.session import optional_websocket_account
from data.collector.quote_service import get_quote_service, QuoteData

router = APIRouter()

# 活跃的 WebSocket 连接
_active_connections: list[WebSocket] = []
_ws_lock = asyncio.Lock()

# 预警引擎按 workspace 隔离；保留旧别名供现有测试/生命周期代码使用。
_alert_engine = None
_alert_engines = {}
_conditional_order_engine = None
_alert_outbox = None
_broadcast_loop: asyncio.AbstractEventLoop | None = None
_connection_workspaces = {}


def configure_broadcast_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Register the application loop used by callbacks from QuoteService threads."""

    global _broadcast_loop
    _broadcast_loop = loop


def close_alert_outbox() -> None:
    global _alert_outbox, _alert_engine, _alert_engines, _connection_workspaces
    if _alert_outbox is not None:
        _alert_outbox.close()
    _alert_outbox = None
    _alert_engine = None
    _alert_engines = {}
    _connection_workspaces = {}


def _workspace_id(workspace_id: str | None) -> str:
    value = str(workspace_id or "").strip()
    if value:
        return normalize_workspace_id(value)
    if os.getenv("APP_ENV", "development").lower() == "test":
        return DEFAULT_WORKSPACE_ID
    raise ValueError("workspace_id is required")


def _account_workspace_id(account: dict | None) -> str:
    return _workspace_id((account or {}).get("workspace", {}).get("id"))


def _get_alert_engine(workspace_id: str | None = None):
    global _alert_engine, _alert_outbox, _alert_engines
    resolved_workspace_id = _workspace_id(workspace_id)
    existing = _alert_engines.get(resolved_workspace_id)
    if existing is not None:
        return existing

    if _alert_outbox is None:
        from engine.alert_engine import AlertEngine
        from engine.events.outbox import SQLiteOutbox
        from config.settings import DB_DIR

        _alert_outbox = SQLiteOutbox(DB_DIR / "events.db")
    from engine.alert_engine import AlertEngine

    if resolved_workspace_id == DEFAULT_WORKSPACE_ID and os.getenv("APP_ENV", "development").lower() == "test":
        _alert_engine = AlertEngine(outbox=_alert_outbox)
    else:
        _alert_engine = AlertEngine(
            outbox=_alert_outbox,
            workspace_id=resolved_workspace_id,
        )
    _alert_engines[resolved_workspace_id] = _alert_engine
    _load_alert_rules(resolved_workspace_id)
    return _alert_engine


def _get_conditional_order_engine():
    global _conditional_order_engine
    if _conditional_order_engine is None:
        from engine.conditional_order import ConditionalOrderEngine
        _conditional_order_engine = ConditionalOrderEngine()
    return _conditional_order_engine


def _load_alert_rules(workspace_id: str | None = None):
    """从数据库加载当前 workspace 的预警规则"""
    try:
        from data.storage import DataStorage
        from engine.alert_engine import AlertRule as EngineAlertRule

        resolved_workspace_id = _workspace_id(workspace_id)
        engine = _alert_engines.get(resolved_workspace_id)
        if engine is None:
            engine = _get_alert_engine(resolved_workspace_id)
        storage = DataStorage()
        rules_data = storage.get_alert_rules(
            enabled_only=True,
            workspace_id=resolved_workspace_id,
        )
        rules = [
            EngineAlertRule(
                id=r["id"], code=r["code"], condition=r["condition"],
                threshold=r["threshold"], enabled=r["enabled"],
                name=r["name"], cooldown=r["cooldown"],
                webhook_url=r.get("webhook_url", ""),
                workspace_id=r.get("workspace_id", resolved_workspace_id),
            )
            for r in rules_data
        ]
        engine.set_rules(rules)
    except Exception as e:
        logger.warning(f"加载预警规则失败: {e}")


def _alert_workspace_ids() -> set[str]:
    """Find rule-bearing workspaces without exposing one workspace's rules to another."""

    workspace_ids = set(_alert_engines)
    if _alert_engine is not None:
        workspace_ids.add(getattr(_alert_engine, "workspace_id", DEFAULT_WORKSPACE_ID))
    try:
        from data.storage import DataStorage

        workspace_ids.update(DataStorage().get_alert_workspace_ids(enabled_only=True))
    except Exception as exc:
        logger.debug(f"加载预警 workspace 列表失败: {exc}")
    return {workspace_id for workspace_id in workspace_ids if workspace_id}


def _quote_to_dict(q: QuoteData) -> dict:
    """QuoteData -> 可序列化字典"""
    return {
        "code": q.code,
        "name": q.name,
        "price": round(q.price, 2),
        "open": round(q.open, 2),
        "high": round(q.high, 2),
        "low": round(q.low, 2),
        "pre_close": round(q.pre_close, 2),
        "volume": q.volume,
        "amount": q.amount,
        "change_pct": round(q.change_pct, 2),
        "industry": q.industry,
        "sector": q.sector,
        "concepts": q.concepts.split(",") if q.concepts else [],
    }


async def _broadcast_quotes(quotes: dict[str, QuoteData]):
    """广播行情到所有 WebSocket 连接"""
    async with _ws_lock:
        connections = list(_active_connections)
    if not connections:
        return

    payload = json.dumps({
        "type": "quotes",
        "data": {code: _quote_to_dict(q) for code, q in quotes.items()},
        "time": now_beijing_iso(),
    })

    disconnected = []
    for ws in connections:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)

    if disconnected:
        async with _ws_lock:
            for ws in disconnected:
                if ws in _active_connections:
                    _active_connections.remove(ws)
                _connection_workspaces.pop(ws, None)


async def _broadcast_alerts(alerts):
    """只向同 workspace 的 WebSocket 连接广播预警。"""
    async with _ws_lock:
        connections = list(_active_connections)
    if not connections:
        return

    disconnected = []
    for ws in connections:
        workspace_id = _connection_workspaces.get(ws, DEFAULT_WORKSPACE_ID)
        visible_alerts = [
            alert for alert in alerts
            if getattr(alert, "workspace_id", DEFAULT_WORKSPACE_ID) == workspace_id
        ]
        if not visible_alerts:
            continue
        try:
            await ws.send_text(json.dumps({
                "type": "alerts",
                "data": [alert.to_dict() for alert in visible_alerts],
                "time": now_beijing_iso(),
            }))
        except Exception:
            disconnected.append(ws)

    if disconnected:
        async with _ws_lock:
            for ws in disconnected:
                if ws in _active_connections:
                    _active_connections.remove(ws)
                _connection_workspaces.pop(ws, None)


async def _safe_ws_send_text(ws: WebSocket, payload: str) -> bool:
    try:
        await ws.send_text(payload)
        return True
    except (WebSocketDisconnect, ClientDisconnected):
        return False


def _sync_broadcast(quotes: dict[str, QuoteData]):
    """同步回调 -> 异步广播（行情 + 预警检查）"""
    alerts = []
    for workspace_id in _alert_workspace_ids():
        try:
            workspace_alerts = _get_alert_engine(workspace_id).check(quotes)
            alerts.extend(workspace_alerts)
            if workspace_alerts:
                try:
                    _get_conditional_order_engine().handle_alerts(workspace_alerts, quotes)
                except Exception as e:
                    logger.warning(f"条件单执行异常: {e}")
        except Exception as e:
            logger.debug(f"预警检查异常 ({workspace_id}): {e}")

    loop = _broadcast_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
    if loop is None or not loop.is_running():
        return
    loop.call_soon_threadsafe(
        lambda: asyncio.create_task(_broadcast_quotes(quotes))
    )
    if alerts:
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(_broadcast_alerts(alerts))
        )


@router.websocket("/ws/quotes")
async def websocket_quotes(ws: WebSocket):
    """WebSocket 行情推送端点

    连接后自动推送所有订阅股票的行情更新。
    客户端可发送消息：
    - {"action": "subscribe", "codes": ["002297", "600519"]}
    - {"action": "unsubscribe", "codes": ["002297"]}
    - {"action": "ping"}
    """
    if not is_valid_api_key(websocket_api_key(ws)):
        await close_unauthorized_websocket(ws)
        return
    account = await optional_websocket_account(ws)
    try:
        workspace_id = _account_workspace_id(account)
    except ValueError:
        await ws.close(code=1008, reason="请先登录")
        return

    await ws.accept()
    async with _ws_lock:
        if len(_active_connections) >= 100:
            await ws.close(code=1013, reason="Too many connections")
            return
        _active_connections.append(ws)
        _connection_workspaces[ws] = workspace_id
    logger.info(f"WebSocket 连接建立, 当前 {len(_active_connections)} 个连接")

    service = get_quote_service()

    # 发送当前缓存的行情
    try:
        cached = service.get_all_quotes()
        if cached:
            if not await _safe_ws_send_text(ws, json.dumps({
                "type": "quotes",
                "data": {code: _quote_to_dict(q) for code, q in cached.items()},
                "time": now_beijing_iso(),
            })):
                return

        # 发送当前状态
        if not await _safe_ws_send_text(ws, json.dumps({
            "type": "status",
            "running": service.is_running,
            "subscriptions": service.subscription_count,
            "temporary_subscriptions": getattr(service, "temporary_subscription_count", 0),
            "cache_count": service.cache_count,
            "update_count": service.update_count,
        })):
            return

        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")

                if action == "subscribe":
                    codes = msg.get("codes", [])
                    if codes:
                        service.subscribe(codes)
                        await ws.send_text(json.dumps({
                            "type": "subscribed",
                            "codes": codes,
                        }))

                elif action == "unsubscribe":
                    codes = msg.get("codes", [])
                    if codes:
                        service.unsubscribe(codes)
                        await ws.send_text(json.dumps({
                            "type": "unsubscribed",
                            "codes": codes,
                        }))

                elif action == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            if ws in _active_connections:
                _active_connections.remove(ws)
            _connection_workspaces.pop(ws, None)
        logger.info(f"WebSocket 断开, 剩余 {len(_active_connections)} 个连接")


@router.get("/quotes/status")
async def quote_service_status():
    """行情服务状态"""
    service = get_quote_service()
    return {
        "running": service.is_running,
        "subscriptions": service.subscription_count,
        "cache_count": service.cache_count,
        "update_count": service.update_count,
        "interval": service._interval,
        "last_update": service.last_update_time,
        "connections": len(_active_connections),
    }


@router.post("/quotes/subscribe")
async def subscribe_quotes(codes: list[str]):
    """订阅行情（HTTP 方式）"""
    service = get_quote_service()
    service.subscribe(codes)
    return {"message": f"已订阅 {len(codes)} 只股票", "total": service.subscription_count}


@router.post("/quotes/unsubscribe")
async def unsubscribe_quotes(codes: list[str]):
    """取消订阅"""
    service = get_quote_service()
    service.unsubscribe(codes)
    return {"message": f"已取消 {len(codes)} 只", "total": service.subscription_count}


# ── L2 十档行情 WebSocket ──

@router.websocket("/ws/l2")
async def websocket_l2(ws: WebSocket):
    """L2 十档行情 WebSocket 端点

    客户端发送：
    - {"action": "subscribe", "code": "000001"}   订阅 L2 行情
    - {"action": "unsubscribe", "code": "000001"} 取消订阅
    - {"action": "ping"}

    服务端推送：
    - {"type": "l2", "data": {OrderBook.to_dict()}}
    - {"type": "pong"}
    """
    if not is_valid_api_key(websocket_api_key(ws)):
        await close_unauthorized_websocket(ws)
        return
    if not await optional_websocket_account(ws):
        await ws.close(code=1008, reason="请先登录")
        return

    await ws.accept()
    from engine.order_book import get_l2_simulator
    simulator = get_l2_simulator()

    subscribed_code = {"code": None}

    def on_book(book):
        """L2 数据回调 → 推送到 WebSocket"""
        if book.code == subscribed_code.get("code"):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(ws.send_text(json.dumps({
                        "type": "l2",
                        "data": book.to_dict(),
                    })))
            except Exception:
                pass

    simulator.on_update(on_book)

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")

                if action == "subscribe":
                    code = msg.get("code", "")
                    if code:
                        # 取消旧订阅
                        if subscribed_code["code"]:
                            simulator.unsubscribe(subscribed_code["code"])
                        subscribed_code["code"] = code
                        simulator.subscribe(code)
                        await ws.send_text(json.dumps({
                            "type": "subscribed",
                            "code": code,
                        }))

                elif action == "unsubscribe":
                    code = msg.get("code", "")
                    if code:
                        simulator.unsubscribe(code)
                        if subscribed_code["code"] == code:
                            subscribed_code["code"] = None
                        await ws.send_text(json.dumps({
                            "type": "unsubscribed",
                            "code": code,
                        }))

                elif action == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        if subscribed_code["code"]:
            simulator.unsubscribe(subscribed_code["code"])
