"""System tools exposed to OpenClaw under platform permissions."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from loguru import logger

from dashboard.account_store import account_store
from data.storage.storage import DataStorage, _normalize_storage_code
from engine.models import Direction, OrderType, PaperConfig
from engine.order_manager import OrderManager
from engine.performance_analyzer import PerformanceAnalyzer
from utils.db import get_connection

storage = DataStorage()
paper_config = PaperConfig()
order_manager = OrderManager(paper_config.db_path)
performance_analyzer = PerformanceAnalyzer(paper_config.db_path)


SYSTEM_TOOLS = [
    {
        "name": "quant.watchlist.add",
        "label": "加入自选股",
        "permission": "write_watchlist",
        "description": "把指定 A 股股票加入当前用户自选股。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.watchlist.remove",
        "label": "移出自选股",
        "permission": "write_watchlist",
        "description": "从当前用户自选股移除股票。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.watchlist.list",
        "label": "查看自选股",
        "permission": "read_market",
        "description": "读取当前自选股及行情摘要。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.stock.open",
        "label": "打开股票详情",
        "permission": "read_market",
        "description": "返回前端可跳转的股票详情链接和基础信息。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.paper.order",
        "label": "模拟盘下单",
        "permission": "write_paper_trade",
        "description": "创建模拟盘订单。仅模拟盘，不连接实盘。",
        "schema": {
            "code": "6 位股票代码",
            "direction": "buy 或 sell",
            "volume": "股数，A 股应为 100 的整数倍",
            "order_type": "market 或 limit",
            "price": "限价单价格，可选",
            "reason": "下单原因，可选",
        },
        "confirm": True,
    },
    {
        "name": "quant.paper.close_position",
        "label": "模拟盘平仓",
        "permission": "write_paper_trade",
        "description": "创建模拟盘平仓卖出订单。",
        "schema": {"code": "6 位股票代码", "volume": "可选，不填则全平"},
        "confirm": True,
    },
    {
        "name": "quant.paper.summary",
        "label": "模拟盘摘要",
        "permission": "read_portfolio",
        "description": "读取模拟盘绩效、持仓和近期订单摘要。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.valuation.peg",
        "label": "PEG 估值快照",
        "permission": "read_market",
        "description": "读取单只 A 股的机构预测、成长、PEG、目标价和研报摘要。",
        "schema": {"code": "6 位股票代码", "report_limit": "研报数量，可选"},
        "confirm": False,
    },
    {
        "name": "quant.data.snapshot",
        "label": "数据底座快照",
        "permission": "read_market",
        "description": "读取当前工作区的数据覆盖率、行情缓存、估值覆盖和数据源状态。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.qlib.top",
        "label": "Qlib 预测 Top",
        "permission": "read_market",
        "description": "读取 qlib 最新预测池 Top 股票。",
        "schema": {"top_n": "返回数量，可选"},
        "confirm": False,
    },
    {
        "name": "quant.report.generate_daily",
        "label": "生成模拟盘收益日报",
        "permission": "read_portfolio",
        "description": "生成并保存某日模拟盘收益日报。",
        "schema": {"trade_date": "YYYY-MM-DD，可选，默认今天"},
        "confirm": False,
    },
    {
        "name": "quant.report.open",
        "label": "查看模拟盘收益日报",
        "permission": "read_portfolio",
        "description": "打开当前工作区指定日期的模拟盘收益日报。",
        "schema": {"trade_date": "YYYY-MM-DD"},
        "confirm": False,
    },
    {
        "name": "quant.skill.record",
        "label": "记录 Skill",
        "permission": "manage_skills",
        "description": "记录当前工作区已安装或待安装的 OpenClaw Skill，用于权限审计。",
        "schema": {"name": "Skill 名称", "version": "版本，可选", "source": "来源，可选"},
        "confirm": True,
    },
]


TOOL_MAP = {tool["name"]: tool for tool in SYSTEM_TOOLS}


def require_tool_permission(account: dict, tool: dict) -> None:
    permission = tool.get("permission", "")
    if permission and not (account.get("permissions") or {}).get(permission):
        raise HTTPException(status_code=403, detail=f"缺少工具权限: {permission}")


def normalize_code_or_400(code: str) -> str:
    _, plain_code = _normalize_storage_code(code)
    if not plain_code:
        raise HTTPException(status_code=400, detail="股票代码格式非法")
    return plain_code


async def invoke_system_tool(account: dict, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = TOOL_MAP.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="系统工具不存在")
    require_tool_permission(account, tool)

    user_id = account["user"]["id"]
    workspace_id = account["workspace"]["id"]
    arguments = {
        **(arguments or {}),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "sessionKey": account["workspace"]["openclaw_workspace_id"],
    }
    status = "ok"
    reason = ""
    result: dict[str, Any]

    try:
        if tool_name == "quant.watchlist.add":
            result = _watchlist_add(arguments)
        elif tool_name == "quant.watchlist.remove":
            result = _watchlist_remove(arguments)
        elif tool_name == "quant.watchlist.list":
            result = {"items": storage.get_watchlist_with_info(workspace_id)}
        elif tool_name == "quant.stock.open":
            result = _stock_open(arguments)
        elif tool_name == "quant.paper.order":
            result = _paper_order(arguments)
        elif tool_name == "quant.paper.close_position":
            result = _paper_close_position(arguments)
        elif tool_name == "quant.paper.summary":
            result = _paper_summary()
        elif tool_name == "quant.valuation.peg":
            result = _valuation_peg(arguments)
        elif tool_name == "quant.data.snapshot":
            result = _data_snapshot(arguments)
        elif tool_name == "quant.qlib.top":
            result = _qlib_top(arguments)
        elif tool_name == "quant.report.generate_daily":
            result = _generate_daily_report(account, arguments)
        elif tool_name == "quant.report.open":
            result = _open_daily_report(account, arguments)
        elif tool_name == "quant.skill.record":
            result = _skill_record(account, arguments)
        else:
            raise HTTPException(status_code=404, detail="系统工具不存在")
    except HTTPException as exc:
        status = "denied" if exc.status_code in (401, 403) else "error"
        reason = str(exc.detail)
        account_store.record_audit(
            "openclaw.system_tool.invoke",
            user_id=user_id,
            workspace_id=workspace_id,
            target_type="tool",
            target_id=tool_name,
            tool_name=tool_name,
            status=status,
            reason=reason,
            metadata={"arguments": _redact_arguments(arguments)},
        )
        raise
    except Exception as exc:
        logger.exception(f"OpenClaw 系统工具调用失败: {tool_name}")
        status = "error"
        reason = str(exc)
        account_store.record_audit(
            "openclaw.system_tool.invoke",
            user_id=user_id,
            workspace_id=workspace_id,
            target_type="tool",
            target_id=tool_name,
            tool_name=tool_name,
            status=status,
            reason=reason,
            metadata={"arguments": _redact_arguments(arguments)},
        )
        raise HTTPException(status_code=500, detail="工具调用失败")

    account_store.record_audit(
        "openclaw.system_tool.invoke",
        user_id=user_id,
        workspace_id=workspace_id,
        target_type="tool",
        target_id=tool_name,
        tool_name=tool_name,
        status=status,
        reason=reason,
        metadata={"arguments": _redact_arguments(arguments), "result_preview": _preview(result)},
    )
    _auto_record_research_memory(account, tool_name, arguments, result)
    return {
        "success": True,
        "tool": tool_name,
        "permission": tool["permission"],
        "result": result,
    }


def _watchlist_add(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    workspace_id = str(arguments.get("workspace_id") or arguments.get("sessionKey") or "")
    added = storage.add_to_watchlist(code, workspace_id)
    return {
        "code": code,
        "added": added,
        "message": "添加成功" if added else "已在自选股中",
    }


def _watchlist_remove(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    workspace_id = str(arguments.get("workspace_id") or arguments.get("sessionKey") or "")
    removed = storage.remove_from_watchlist(code, workspace_id)
    return {"code": code, "removed": removed}


def _stock_open(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    stock_list = storage.get_stock_list()
    name = ""
    if not stock_list.empty:
        matched = stock_list[stock_list["code"].astype(str).str.replace(r"^(sh|sz)", "", regex=True) == code]
        if not matched.empty:
            name = str(matched.iloc[0].get("name") or "")
    return {
        "code": code,
        "name": name,
        "tab": "stock",
        "hash": f"#stock",
        "query": {"code": code},
        "frontend_action": {"type": "open_stock_detail", "code": code},
    }


def _paper_order(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    direction = Direction.from_value(str(arguments.get("direction") or "buy"))
    order_type = OrderType(str(arguments.get("order_type") or "market"))
    volume = int(arguments.get("volume") or 0)
    price = arguments.get("price")
    if volume <= 0 or volume % 100 != 0:
        raise HTTPException(status_code=400, detail="模拟盘下单数量必须是 100 的正整数倍")
    if order_type != OrderType.MARKET and price is None:
        raise HTTPException(status_code=400, detail="非市价单需要价格")
    order = order_manager.create_order(
        code=code,
        direction=direction,
        order_type=order_type,
        volume=volume,
        price=float(price) if price not in (None, "") else None,
        strategy_name="openclaw",
        signal_reason=str(arguments.get("reason") or "OpenClaw 模拟盘指令"),
    )
    return {"order": order.to_dict(), "message": "模拟盘订单已创建"}


def _paper_close_position(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    requested = arguments.get("volume")
    conn = get_connection(paper_config.db_path)
    try:
        row = conn.execute("SELECT * FROM paper_positions WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"持仓不存在: {code}")
        close_volume = int(requested or row["volume"])
        if close_volume <= 0 or close_volume > row["volume"]:
            raise HTTPException(status_code=400, detail="平仓数量不合法")
    finally:
        conn.close()
    order = order_manager.create_order(
        code=code,
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        volume=close_volume,
        strategy_name="openclaw",
        signal_reason=str(arguments.get("reason") or "OpenClaw 模拟盘平仓"),
    )
    return {"order": order.to_dict(), "message": "模拟盘平仓订单已创建"}


def _paper_summary() -> dict[str, Any]:
    metrics = performance_analyzer.calculate_metrics(initial_cash=paper_config.initial_cash)
    conn = get_connection(paper_config.db_path, readonly=True)
    try:
        positions = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM paper_positions ORDER BY market_value DESC LIMIT 20"
            ).fetchall()
        ]
        orders = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
        ]
    finally:
        conn.close()
    return {
        "metrics": metrics.to_dict(),
        "positions": positions,
        "recent_orders": orders,
    }


def _valuation_peg(arguments: dict[str, Any]) -> dict[str, Any]:
    from data.services.valuation_service import ValuationService

    code = normalize_code_or_400(str(arguments.get("code") or ""))
    report_limit = int(arguments.get("report_limit") or 8)
    return ValuationService(storage=storage).build_snapshot(code, report_limit=max(1, min(report_limit, 20)))


def _data_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    import time

    workspace_id = str(arguments.get("workspace_id") or "")
    watchlist = storage.get_watchlist(workspace_id)
    quote = {
        "running": False,
        "subscriptions": 0,
        "cache_count": 0,
        "last_update_age_sec": None,
    }
    try:
        from data.collector.quote_service import get_quote_service

        quote_service = get_quote_service()
        last_update = quote_service.last_update_time
        quote = {
            "running": quote_service.is_running,
            "subscriptions": quote_service.subscription_count,
            "cache_count": quote_service.cache_count,
            "last_update_age_sec": round(time.time() - last_update, 1) if last_update else None,
        }
    except Exception:
        pass
    return {
        "stock_count": len(storage.get_all_stock_codes()),
        "watchlist_count": len(watchlist),
        "quote": quote,
        "providers": {
            "market": "mootdx + eastmoney + tencent fallback",
            "valuation": "eastmoney analyst consensus adapter",
            "ml": "qlib prediction cache",
        },
    }


def _qlib_top(arguments: dict[str, Any]) -> dict[str, Any]:
    from dashboard.routers.qlib import _enrich_with_stock_info, _load_predictions

    top_n = max(1, min(int(arguments.get("top_n") or 10), 50))
    cache = _load_predictions()
    if not cache:
        return {"predictions": [], "date": None, "total": 0}
    latest_date = max(cache.keys())
    preds = cache[latest_date]
    sorted_preds = sorted(preds.items(), key=lambda item: item[1], reverse=True)[:top_n]
    codes = [code for code, _ in sorted_preds]
    info_map = _enrich_with_stock_info(codes)
    predictions = []
    for code, score in sorted_preds:
        info = info_map.get(code, {})
        predictions.append({
            "code": code[-6:] if len(code) > 6 else code,
            "raw_code": code,
            "name": info.get("name", code),
            "score": round(float(score), 6),
            "industry": info.get("industry", "--"),
            "price": info.get("price"),
        })
    return {"predictions": predictions, "date": latest_date, "total": len(preds)}


def _generate_daily_report(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    from config.datetime_utils import today_beijing

    trade_date = str(arguments.get("trade_date") or today_beijing())
    summary = _paper_summary()
    trades = _trades_for_date(trade_date)
    metrics = summary["metrics"]
    positions = summary["positions"]
    title = f"{trade_date} 模拟盘收益日报"
    content = {
        "trade_date": trade_date,
        "summary": {
            "total_equity": metrics.get("total_equity"),
            "daily_return": metrics.get("daily_return"),
            "cumulative_return": metrics.get("cumulative_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "win_rate": metrics.get("win_rate"),
            "total_trades": metrics.get("total_trades"),
        },
        "positions": positions,
        "trades": trades,
        "review": _build_report_review(metrics, positions, trades),
    }
    report = account_store.save_daily_report(
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        trade_date=trade_date,
        title=title,
        content=content,
    )
    return {"report": report}


def _open_daily_report(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(arguments.get("trade_date") or "").strip()
    if not trade_date:
        raise HTTPException(status_code=400, detail="请提供 trade_date")
    report = account_store.get_daily_report(account["workspace"]["id"], trade_date)
    if not report:
        raise HTTPException(status_code=404, detail=f"日报不存在: {trade_date}")
    return {"report": report}


def _trades_for_date(trade_date: str) -> list[dict[str, Any]]:
    conn = get_connection(paper_config.db_path, readonly=True)
    try:
        rows = conn.execute(
            """SELECT * FROM paper_trades
            WHERE substr(created_at, 1, 10) = ?
            ORDER BY created_at DESC""",
            (trade_date,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _build_report_review(metrics: dict[str, Any], positions: list[dict[str, Any]], trades: list[dict[str, Any]]) -> list[str]:
    lines = []
    daily_return = metrics.get("daily_return") or 0
    lines.append(f"当日收益率 {daily_return:.2%}，累计收益率 {(metrics.get('cumulative_return') or 0):.2%}。")
    if positions:
        top = positions[0]
        lines.append(f"最大持仓为 {top.get('code')}，市值 {top.get('market_value', 0):.2f}。")
    else:
        lines.append("当前无持仓，适合复盘空仓原因和下一交易日观察列表。")
    if trades:
        lines.append(f"当日有 {len(trades)} 笔成交，需要重点复盘信号来源、滑点和仓位占比。")
    else:
        lines.append("当日没有成交，重点检查策略是否过于保守或条件未触发。")
    return lines


def _skill_record(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill 名称不能为空")
    skill = account_store.upsert_skill(
        workspace_id=account["workspace"]["id"],
        name=name,
        version=str(arguments.get("version") or ""),
        status=str(arguments.get("status") or "installed"),
        source=str(arguments.get("source") or "openclaw"),
        permissions=list(arguments.get("permissions") or []),
    )
    return {"skill": skill}


def _auto_record_research_memory(
    account: dict,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    code = str(arguments.get("code") or result.get("code") or result.get("order", {}).get("code") or "").strip()
    reason = str(arguments.get("reason") or "").strip()
    specs = {
        "quant.watchlist.add": {
            "title": "加入自选",
            "tags": ["watchlist", "关注"],
            "content": "通过龙虾加入自选。",
        },
        "quant.watchlist.remove": {
            "title": "移出自选",
            "tags": ["watchlist", "复盘"],
            "content": "通过龙虾移出自选。",
        },
        "quant.stock.open": {
            "title": "打开详情",
            "tags": ["stock_detail", "研究"],
            "content": "通过龙虾打开股票详情。",
        },
        "quant.paper.order": {
            "title": "模拟盘下单",
            "tags": ["paper_trade", "交易原因"],
            "content": "通过龙虾创建模拟盘订单。",
        },
        "quant.paper.close_position": {
            "title": "模拟盘平仓",
            "tags": ["paper_trade", "平仓原因"],
            "content": "通过龙虾创建模拟盘平仓订单。",
        },
        "quant.report.generate_daily": {
            "title": "生成收益日报",
            "tags": ["daily_report", "复盘"],
            "content": "通过龙虾生成模拟盘收益日报。",
        },
        "quant.report.open": {
            "title": "查看收益日报",
            "tags": ["daily_report", "复盘"],
            "content": "通过龙虾查看模拟盘收益日报。",
        },
    }
    spec = specs.get(tool_name)
    if not spec:
        return

    details = [spec["content"]]
    if reason:
        details.append(f"原因：{reason}")
    if tool_name == "quant.paper.order":
        order = result.get("order") or {}
        details.append(
            "订单："
            f"{order.get('direction') or arguments.get('direction') or '--'} "
            f"{order.get('volume') or arguments.get('volume') or '--'} 股，"
            f"{order.get('order_type') or arguments.get('order_type') or '--'}。"
        )
    if tool_name == "quant.report.generate_daily":
        report = result.get("report") or {}
        details.append(f"日期：{report.get('trade_date') or arguments.get('trade_date') or '默认交易日'}")
    if tool_name == "quant.report.open":
        report = result.get("report") or {}
        details.append(f"日期：{report.get('trade_date') or arguments.get('trade_date') or '默认交易日'}")

    title_code = f" {code}" if code else ""
    try:
        account_store.create_memory(
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            title=f"{spec['title']}{title_code}",
            content="\n".join(details),
            code=code,
            tags=spec["tags"],
            source="openclaw:auto",
        )
    except Exception:
        logger.exception(f"自动记录 OpenClaw 研究记忆失败: {tool_name}")


def _redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(arguments or {})
    for key in list(redacted):
        if "password" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            redacted[key] = "***"
    return redacted


def _preview(result: dict[str, Any]) -> dict[str, Any]:
    text = str(result)
    return {"text": text[:500], "truncated": len(text) > 500}
