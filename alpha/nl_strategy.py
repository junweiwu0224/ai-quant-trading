"""自然语言策略生成 + AI 结果解读

基于 OpenAI 兼容大模型，提供三个核心能力：
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


# ── 策略代码生成 + 回测诊断 ──

_SYSTEM_STRATEGY_GEN = """你是A股量化策略代码生成器。根据用户的自然语言描述，生成可直接运行的 Python 策略代码。

策略代码规范：
- 继承 BaseStrategy
- 实现 on_init(self) 和 on_bar(self, bar: Bar) 方法
- bar 对象属性：code, open, high, low, close, volume, date
- 买入：self.buy(code, price, volume)  volume 为100的整数
- 卖出：self.sell(code, price, volume)
- 查询持仓：self.portfolio.get_position(code)
- 可用资金：self.portfolio.cash
- 获取历史数据：self.get_bars(code, count) 返回最近 N 根 Bar 列表

可用技术指标库（通过 self._indicators 或自行计算）：
- MA(close, period) → 移动平均
- EMA(close, period) → 指数移动平均
- RSI(close, period) → 相对强弱指数
- MACD(close) → 返回 (dif, dea, macd_hist)
- BOLL(close, period, num_std) → 返回 (upper, middle, lower)
- ATR(high, low, close, period) → 平均真实波幅
- KDJ(high, low, close) → 返回 (k, d, j)

输出格式：仅输出 Python 代码，不要任何解释文字。代码要完整可运行。"""


_SYSTEM_STRATEGY_DIAG = """你是A股量化回测分析师。根据回测结果数据，给出专业的诊断报告。

分析维度：
1. 收益评估：总收益、年化收益是否跑赢基准
2. 风险评估：最大回撤、波动率是否可控
3. 效率评估：夏普比率、Calmar 比率是否优秀
4. 交易评估：胜率、盈亏比、交易频率是否合理
5. 问题诊断：识别策略潜在缺陷（过拟合、信号稀疏、持仓集中等）
6. 改进建议：具体的参数调整或逻辑优化方向

输出格式（Markdown）：
## 回测诊断

### 综合评级：[A/B/C/D]

### 核心指标
| 指标 | 值 | 评价 |
|------|-----|------|

### 问题诊断
- ...

### 改进建议
1. ...

语言简洁专业，建议具体可操作。"""


async def generate_strategy_code(description: str) -> str:
    """自然语言 → 策略代码

    Args:
        description: 用户描述的策略逻辑

    Returns:
        Python 策略代码字符串
    """
    if not description or not description.strip():
        raise ValueError("策略描述不能为空")

    messages = [
        {"role": "system", "content": _SYSTEM_STRATEGY_GEN},
        {"role": "user", "content": description},
    ]
    code = await chat_completion(messages, temperature=0.3)

    # 清理 markdown 代码块标记
    code = code.strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


async def diagnose_backtest(result_json: dict) -> str:
    """回测结果 → AI 诊断报告

    Args:
        result_json: 回测结果指标字典

    Returns:
        Markdown 格式的诊断报告
    """
    context = "回测结果数据：\n```json\n"
    import json
    context += json.dumps(result_json, ensure_ascii=False, indent=2)
    context += "\n```"

    messages = [
        {"role": "system", "content": _SYSTEM_STRATEGY_DIAG},
        {"role": "user", "content": context},
    ]
    return await chat_completion(messages, temperature=0.5)
