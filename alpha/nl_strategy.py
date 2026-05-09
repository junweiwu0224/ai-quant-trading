"""自然语言策略生成 + AI 结果解读

基于 mimo-v2.5 大模型，提供三个核心能力：
1. 自然语言 → 选股条件 JSON
2. AI 预测结果 → 自然语言解读
3. 量化领域通用对话
"""
from __future__ import annotations

from alpha.llm_client import chat_completion, chat_completion_stream, chat_json

# ── 系统提示词 ──

_SYSTEM_SCREEN = """你是A股量化选股助手。用户用自然语言描述选股逻辑，你将其转换为 JSON 格式的筛选条件。

可用字段与含义：
- code: 股票代码, name: 股票名称, industry: 所属行业
- price: 最新价(元), change_pct: 涨跌幅(%)
- pe_ratio: 市盈率(动态), pb_ratio: 市净率, roe: 净资产收益率(%)
- market_cap: 总市值(亿元), circulating_cap: 流通市值(亿)
- turnover_rate: 换手率(%), volume_ratio: 量比, amplitude: 振幅(%)
- high: 最高价, low: 最低价, open: 开盘价, prev_close: 昨收价
- volume: 成交量(手), amount: 成交额(万元)

运算符(op)支持：
- gt: 大于, lt: 小于, gte: 大于等于, lte: 小于等于
- between: 区间 [min, max], in: 包含在列表中

输出格式（JSON 数组）：
[{"field": "pe_ratio", "op": "lt", "value": 20, "desc": "市盈率低于20"},
 {"field": "change_pct", "op": "between", "value": [3, 7], "desc": "涨幅3%~7%"}]

规则：
- 仅输出 JSON 数组，不要任何解释文字
- desc 字段用中文简要说明条件含义
- 如果用户描述模糊，选择最合理的数值"""

_SYSTEM_INTERPRET = """你是A股量化分析师。根据 AI 模型的预测结果和因子贡献度，用简洁中文解读选股逻辑。

解读格式：
## 推荐理由
（2-3 句话概括为什么推荐）

## 关键因子
| 因子 | 贡献度 | 解读 |
|------|--------|------|
| ... | ... | ... |

## 风险提示
- （1-2 个主要风险）

## 操作建议
- 持有周期：...
- 仓位建议：...

语言简洁专业，避免夸大收益。涉及具体操作时注明仅供参考。"""

_SYSTEM_CHAT = """你是A股量化交易专家助手，名叫「量化小智」。你可以：
1. 解释量化策略和因子含义（如 MA、RSI、MACD、布林带等）
2. 分析股票技术面和基本面
3. 建议选股条件和策略思路
4. 解读回测结果和风险指标（夏普比率、最大回撤、胜率等）
5. 讨论仓位管理和风控方法

回答规则：
- 简洁专业，避免冗长
- 涉及具体股票时注明"仅供参考，不构成投资建议"
- 可以在回答中使用 Markdown 格式（表格、列表、加粗等）
- 如果用户问与量化投资无关的问题，礼貌引导回主题"""


# ── 可用字段描述（给 generate_filters 用） ──

AVAILABLE_FIELDS = {
    "code": "股票代码",
    "name": "股票名称",
    "industry": "所属行业",
    "price": "最新价(元)",
    "change_pct": "涨跌幅(%)",
    "pe_ratio": "市盈率(动态)",
    "pb_ratio": "市净率",
    "roe": "净资产收益率(%)",
    "market_cap": "总市值(亿元)",
    "circulating_cap": "流通市值(亿元)",
    "turnover_rate": "换手率(%)",
    "volume_ratio": "量比",
    "amplitude": "振幅(%)",
    "high": "最高价",
    "low": "最低价",
    "open": "开盘价",
    "prev_close": "昨收价",
    "volume": "成交量(手)",
    "amount": "成交额(万元)",
}


async def generate_filters(description: str) -> list[dict]:
    """自然语言 → 选股条件 JSON 列表

    Args:
        description: 用户自然语言描述的选股逻辑

    Returns:
        条件列表，每项包含 field/op/value/desc
    """
    messages = [
        {"role": "system", "content": _SYSTEM_SCREEN},
        {"role": "user", "content": description},
    ]
    result = await chat_json(messages, temperature=0.2)
    if not isinstance(result, list):
        raise ValueError(f"LLM 返回格式错误，期望数组，得到 {type(result).__name__}")
    # 校验每个条件的字段
    valid_ops = {"gt", "lt", "gte", "lte", "between", "in"}
    for item in result:
        if not isinstance(item, dict):
            raise ValueError(f"条件项应为对象: {item}")
        if "field" not in item or "op" not in item:
            raise ValueError(f"条件缺少 field 或 op: {item}")
        if item["op"] not in valid_ops:
            raise ValueError(f"不支持的运算符: {item['op']}")
        if "value" not in item:
            raise ValueError(f"条件缺少 value: {item}")
    return result


async def interpret_prediction(
    stock_code: str,
    stock_name: str,
    prediction: dict,
    shap_values: list[dict] | None = None,
) -> str:
    """AI 预测结果 → 自然语言解读

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        prediction: 预测结果（score, signal, risk_score 等）
        shap_values: SHAP 因子贡献度列表 [{"feature": "xx", "importance": 0.1}, ...]

    Returns:
        Markdown 格式的解读文本
    """
    if not stock_code or not isinstance(stock_code, str):
        raise ValueError("stock_code 不能为空")
    if not isinstance(prediction, dict):
        raise ValueError(f"prediction 必须是 dict，收到 {type(prediction).__name__}")

    context = f"股票：{stock_code} {stock_name}\n"
    context += f"预测评分：{prediction.get('score', 'N/A')}\n"
    context += f"信号：{prediction.get('signal', 'N/A')}\n"
    if prediction.get("risk_score"):
        context += f"风险评分：{prediction['risk_score']}\n"

    if shap_values and isinstance(shap_values, list):
        context += "\n因子贡献度 TOP 10：\n"
        for sv in shap_values[:10]:
            if isinstance(sv, dict) and "feature" in sv and "importance" in sv:
                context += f"- {sv['feature']}: {sv['importance']:.4f}\n"

    messages = [
        {"role": "system", "content": _SYSTEM_INTERPRET},
        {"role": "user", "content": context},
    ]
    return await chat_completion(messages, temperature=0.5)


async def chat(
    user_message: str,
    history: list[dict[str, str]] | None = None,
):
    """通用量化对话（返回 AsyncIterator[str] 用于流式输出）

    Args:
        user_message: 用户消息
        history: 历史消息列表 [{"role": "user/assistant", "content": "..."}]

    Returns:
        AsyncIterator[str] 流式 token
    """
    messages = [{"role": "system", "content": _SYSTEM_CHAT}]
    if history:
        messages.extend(history[-20:])  # 最多保留最近 20 条
    messages.append({"role": "user", "content": user_message})

    return chat_completion_stream(messages, temperature=0.7)


async def chat_sync(
    user_message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """通用量化对话（非流式，返回完整文本）"""
    messages = [{"role": "system", "content": _SYSTEM_CHAT}]
    if history:
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": user_message})

    return await chat_completion(messages, temperature=0.7)
