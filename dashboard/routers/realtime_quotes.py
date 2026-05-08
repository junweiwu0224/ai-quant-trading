"""实时行情 WebSocket 推送"""
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from data.collector.quote_service import get_quote_service, QuoteData

router = APIRouter()

# 活跃的 WebSocket 连接
_active_connections: list[WebSocket] = []
_ws_lock = asyncio.Lock()


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
        "time": datetime.now().isoformat(),
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


def _sync_broadcast(quotes: dict[str, QuoteData]):
    """同步回调 -> 异步广播"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast_quotes(quotes))
    except RuntimeError:
        pass


@router.websocket("/ws/quotes")
async def websocket_quotes(ws: WebSocket):
    """WebSocket 行情推送端点

    连接后自动推送所有订阅股票的行情更新。
    客户端可发送消息：
    - {"action": "subscribe", "codes": ["002297", "600519"]}
    - {"action": "unsubscribe", "codes": ["002297"]}
    - {"action": "ping"}
    """
    await ws.accept()
    async with _ws_lock:
        if len(_active_connections) >= 100:
            await ws.close(code=1013, reason="Too many connections")
            return
        _active_connections.append(ws)
    logger.info(f"WebSocket 连接建立, 当前 {len(_active_connections)} 个连接")

    service = get_quote_service()

    # 发送当前缓存的行情
    cached = service.get_all_quotes()
    if cached:
        await ws.send_text(json.dumps({
            "type": "quotes",
            "data": {code: _quote_to_dict(q) for code, q in cached.items()},
            "time": datetime.now().isoformat(),
        }))

    # 发送当前状态
    await ws.send_text(json.dumps({
        "type": "status",
        "running": service.is_running,
        "subscriptions": service.subscription_count,
        "cache_count": service.cache_count,
        "update_count": service.update_count,
    }))

    try:
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
