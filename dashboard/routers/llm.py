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
