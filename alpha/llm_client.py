"""mimo-v2.5 LLM 客户端封装

使用 OpenAI SDK 调用小米 mimo 模型（OpenAI 兼容接口）。
提供同步/异步两种调用方式，全局单例复用连接池。
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from loguru import logger
from openai import AsyncOpenAI

from config.settings import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL

_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    """获取全局 AsyncOpenAI 单例"""
    global _client
    if _client is None:
        if not MIMO_API_KEY:
            raise ValueError("MIMO_API_KEY 未配置，请在 .env 或环境变量中设置")
        _client = AsyncOpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
        )
    return _client


async def chat_completion(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """单次对话完成（非流式）"""
    client = get_llm_client()
    resp = await client.chat.completions.create(
        model=MIMO_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def chat_completion_stream(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """流式对话完成，逐 token 返回"""
    client = get_llm_client()
    stream = await client.chat.completions.create(
        model=MIMO_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def chat_json(
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict | list:
    """对话完成并解析 JSON 响应"""
    raw = await chat_completion(messages, temperature=temperature, max_tokens=max_tokens)
    # 提取 JSON 块（兼容 markdown 代码块包裹）
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)
    return json.loads(text)
