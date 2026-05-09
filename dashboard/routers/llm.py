"""AI 助手 API — mimo-v2.5 大模型接入

端点：
- POST /api/llm/chat         — 通用对话（流式 SSE）
- POST /api/llm/generate-filters — 自然语言 → 选股条件
- POST /api/llm/interpret    — AI 预测结果解读
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from alpha import nl_strategy

router = APIRouter()


# ── 请求模型 ──


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class GenerateFiltersRequest(BaseModel):
    description: str


class InterpretRequest(BaseModel):
    stock_code: str
    stock_name: str = ""
    prediction: dict = {}
    shap_values: list[dict] = []


# ── 端点 ──


@router.post("/chat")
async def llm_chat(req: ChatRequest):
    """通用量化对话（流式 SSE 响应）"""

    async def event_stream():
        try:
            history = [{"role": m.role, "content": m.content} for m in req.history]
            stream = await nl_strategy.chat(req.message, history=history)
            async for token in stream:
                yield f"data: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"LLM 对话异常: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-filters")
async def llm_generate_filters(req: GenerateFiltersRequest):
    """自然语言 → 选股条件 JSON"""
    try:
        filters = await nl_strategy.generate_filters(req.description)
        return {"success": True, "filters": filters}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"生成选股条件异常: {e}")
        return {"success": False, "error": "AI 生成失败，请稍后重试"}


@router.post("/interpret")
async def llm_interpret(req: InterpretRequest):
    """AI 预测结果自然语言解读"""
    try:
        text = await nl_strategy.interpret_prediction(
            stock_code=req.stock_code,
            stock_name=req.stock_name,
            prediction=req.prediction,
            shap_values=req.shap_values if req.shap_values else None,
        )
        return {"success": True, "interpretation": text}
    except Exception as e:
        logger.error(f"AI 解读异常: {e}")
        return {"success": False, "error": "AI 解读失败，请稍后重试"}


# ── 研报整合 + LLM 解读 ──

class ReportAnalyzeRequest(BaseModel):
    title: str
    content: str
    stock_code: str = ""
    stock_name: str = ""


@router.get("/reports/{code}")
async def get_stock_reports(code: str, page: int = 1, page_size: int = 10):
    """获取个股研报列表（东方财富）"""
    import time
    import asyncio
    from data.collector.http_client import fetch_json

    try:
        url = (
            f"https://reportapi.eastmoney.com/report/list"
            f"?industryCode=*&pageSize={page_size}&industry=*&rating=*&ratingChange=*&beginTime=2024-01-01"
            f"&endTime=&pageNo={page}&fields=&qType=0&orgCode=&code={code}"
            f"&rcode=&p={page}&pageNum={page}&pageSize={page_size}"
            f"&_={int(time.time() * 1000)}"
        )
        data = await asyncio.to_thread(fetch_json, url, None, 10.0, {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com",
        })

        reports = []
        for item in (data.get("data") or [])[:page_size]:
            reports.append({
                "title": item.get("title", ""),
                "org": item.get("orgSName", ""),
                "author": item.get("researcher", ""),
                "date": (item.get("publishDate", ""))[:10],
                "rating": item.get("emRatingName", ""),
                "target_price": item.get("predictThisYearPe", ""),
                "summary": item.get("content", "")[:200] if item.get("content") else "",
                "url": f"https://data.eastmoney.com/report/zw/stock.jshtml?encodeUrl={item.get('encodeUrl', '')}",
            })

        return {
            "success": True,
            "code": code,
            "reports": reports,
            "total": data.get("totalHits", 0),
            "page": page,
        }
    except Exception as e:
        logger.error(f"获取研报失败 {code}: {e}")
        return {"success": False, "error": str(e), "reports": []}


@router.post("/reports/analyze")
async def analyze_report(req: ReportAnalyzeRequest):
    """用 LLM 解读研报内容"""
    try:
        stock_info = f"（{req.stock_code} {req.stock_name}）" if req.stock_code else ""
        prompt = f"""请用简洁中文解读以下研报{stock_info}，输出格式：
1. 核心观点（2-3句话）
2. 评级与目标价
3. 关键风险点
4. 投资建议

研报标题：{req.title}
研报内容：
{req.content[:3000]}"""

        result = await nl_strategy.chat(prompt)
        text = ""
        async for token in result:
            text += token
        return {"success": True, "analysis": text}
    except Exception as e:
        logger.error(f"研报解读异常: {e}")
        return {"success": False, "error": "AI 解读失败，请稍后重试"}
