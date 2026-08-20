Now I'll compile the audit findings into the markdown report.

# Backtest Engine Alignment Audit

## Executive Summary

本审计验证了回测引擎唯一真源对齐情况。审计覆盖 `engine/backtest_engine.py`、`alpha/backtest.py` 和 `agentic/` 模块的验证逻辑，重点检查市场日历、执行模型、成本版本、复权、退市、基准和缺失数据处理的一致性。

**关键发现**：
- ✅ 执行成本模型和执行契约已统一
- ✅ Next-bar 执行模型已对齐
- ✅ 市场日历和交易规则已共享
- ⚠️ 复权处理存在隐式依赖
- ⚠️ 退市股票处理不完整
- ⚠️ agentic 模块未直接验证执行契约

---

## 1. 市场日历（Trading Calendar）

### 状态：**已对齐**

**真源位置**：`data/markets.py:TradingCalendar` + `engine/market_rules.py:MarketRule.calendar`

#### 发现

两个回测引擎都通过统一接口获取交易日历：

**engine/backtest_engine.py:115-116**
```python
self._market_rule = self._config.market_rule or get_market_rule(self._config.market)
self._trading_calendar = self._config.trading_calendar or self._market_rule.calendar
```

**alpha/backtest.py:99-100**
```python
self._market_rule = self._config.market_rule or get_market_rule(self._config.market)
self._trading_calendar = self._config.trading_calendar or self._market_rule.calendar
```

**engine/backtest_engine.py:193-198** 和 **alpha/backtest.py:138-143**
```python
def _is_trading_day(self, when: date) -> bool:
    try:
        return bool(self._trading_calendar.is_trading_day(when))
    except (AttributeError, TypeError, ValueError):
        return False
```

#### 验证

- ✅ 两个引擎使用相同的 `TradingCalendar` 接口
- ✅ `_is_trading_day` 实现一致
- ✅ 日历来源可审计：`execution_contract.calendar_name` 和 `calendar_source`

#### 潜在风险

- ⚠️ 默认使用 `weekday_fallback`（仅周一至周五），不包含真实假日
- ⚠️ `TradingCalendar.verified=False` 时，回测结果可能包含非交易日

---

## 2. Next-Bar 执行模型

### 状态：**已对齐**

**真源位置**：`engine/execution_model.py:ExecutionDataContract.execution_rule`

#### 发现

两个引擎都实现了 "signal at close, fill at next bar open" 模型：

**engine/backtest_engine.py:272-274**
```python
# 1. 先处理上一日挂单
self._previous_close_by_code = dict(last_close_by_code)
self._match_orders(strategy, portfolio, daily_bars)
```

**alpha/backtest.py:223-226**
```python
if pending_rebalance is not None:
    target_weights, signal_equity = pending_rebalance
    rows = self._rows_for_date(price_data, dt)
    execution_prices, block_reasons = self._execution_context(rows, last_close)
```

**执行契约声明**（`engine/execution_model.py:163`）：
```python
execution_rule: str = "signal_at_close_then_next_tradable_bar_open"
```

#### 验证

- ✅ 信号在 T 日收盘后生成
- ✅ 成交在 T+1 日开盘价执行
- ✅ 停牌/涨跌停时订单延迟到下一个可交易 bar
- ✅ 执行规则文档化在 `ExecutionDataContract`

#### 实现细节对齐

**engine/backtest_engine.py:456-457**（用开盘价 + 滑点）：
```python
fill = self._execution_cost.buy_fill(bar.open, order.volume)
fill_price = fill.fill_price
```

**alpha/backtest.py:267-268**（同样用开盘价）：
```python
fill = self._execution_cost.buy_fill(price, shares)
```

---

## 3. 成本版本（Cost Model）

### 状态：**已对齐**

**真源位置**：`engine/execution_model.py:ExecutionCostModelVersion`

#### 发现

两个引擎都使用 `resolve_execution_cost_model` 统一成本计算：

**engine/backtest_engine.py:117-125**
```python
configured_cost = self._config.execution_cost_model
if configured_cost is None:
    configured_cost = {
        "version": self._config.cost_model_version,
        "commission_rate": self._config.commission_rate,
        # ...
    }
self._execution_cost = resolve_execution_cost_model(configured_cost)
```

**alpha/backtest.py:92-96**
```python
configured_cost = self._config.execution_cost_model
# ... fallback logic ...
self._execution_cost = resolve_execution_cost_model(
    configured_cost if configured_cost is not None else self._config.cost.to_execution_model()
)
```

#### 验证

- ✅ `ExecutionCostModelVersion` 包含版本号、佣金率、印花税、滑点、最低佣金
- ✅ `buy_fill()` 和 `sell_fill()` 方法统一计算成交价和费用
- ✅ 成本模型可序列化到回测结果的 `execution_contract.cost_model`

#### 成本计算示例

**engine/execution_model.py:54-66**
```python
def buy_fill(self, reference_price: float, shares: float) -> "ExecutionFill":
    price, quantity = self._validate_transaction(reference_price, shares)
    fill_price = price * (1.0 + self.buy_slippage)
    gross = fill_price * quantity
    commission = max(gross * self.commission_rate, self.min_commission)
    transfer_fee = gross * self.transfer_fee_rate
    return ExecutionFill(
        side="buy",
        fill_price=fill_price,
        cash_delta=gross + commission + transfer_fee,
        # ...
    )
```

两个引擎都调用此方法，确保成本计算一致。

---

## 4. Coverage（数据覆盖率）

### 状态：**已对齐**

**真源位置**：回测引擎自身计算，基于 `trading_calendar.trading_days()`

#### 发现

两个引擎都实现了 `_coverage()` 方法：

**engine/backtest_engine.py:374-390**
```python
def _coverage(self, bars_by_code: dict[str, list[Bar]], backtest_dates: list[date]) -> dict[str, Any]:
    expected_days = len(backtest_dates)
    expected_set = set(backtest_dates)
    per_symbol: dict[str, dict[str, Any]] = {}
    for code, bars in bars_by_code.items():
        observed = len({bar.date for bar in bars if bar.date in expected_set})
        per_symbol[code] = {
            "observed_trading_days": observed,
            "expected_trading_days": expected_days,
            "coverage_pct": round(observed / expected_days * 100, 2) if expected_days else 0.0,
        }
    return {
        "calendar": self._execution_contract.calendar_name,
        "calendar_source": self._execution_contract.calendar_source,
        "expected_trading_days": expected_days,
        "per_symbol": per_symbol,
    }
```

**alpha/backtest.py:341-363**（几乎相同的实现）
```python
def _coverage(
    self,
    price_data: dict[str, pd.DataFrame],
    observed_dates: list[str],
    deferred: list[dict[str, str]],
) -> dict[str, Any]:
    # ... 同样计算 observed/expected 比例 ...
    return {
        "calendar": self._execution_contract.calendar_name,
        "calendar_source": self._execution_contract.calendar_source,
        "expected_trading_days": expected,
        "observed_trading_days": len(observed_dates),
        "per_symbol": per_symbol,
        "deferred": deferred,
    }
```

#### 验证

- ✅ Coverage 定义一致：`observed_trading_days / expected_trading_days`
- ✅ `expected_trading_days` 基于日历计算，而非硬编码
- ✅ `per_symbol` 覆盖率独立计算，支持部分股票缺失数据的场景
- ✅ `alpha/backtest.py` 额外记录 `deferred` 订单（因停牌/涨跌停未成交）

#### Coverage 策略文档化

**engine/execution_model.py:170**
```python
coverage_policy: str = "observed_trading_days_over_expected_calendar_days"
```

---

## 5. 复权处理（Adjustment）

### 状态：**部分对齐**

**真源位置**：`data/storage.py:StockDaily.adj_factor` + `data/collector/collector.py`

#### 发现

**数据采集层**（`data/collector/collector.py:56`）：
```python
df = ak.stock_zh_a_hist(
    # ...
    adjust="qfq",  # 前复权
)
```

**数据库存储**（`data/storage/storage.py:213`）：
```python
adj_factor = Column(Float, default=1.0)  # 复权因子: 不复权价 / 前复权价
```

**回测引擎**：
- `engine/backtest_engine.py` 和 `alpha/backtest.py` **直接使用数据库中的价格**，未显式处理复权
- 隐式依赖：数据采集时已应用前复权（`adjust="qfq"`）

#### 验证

- ⚠️ **复权处理不在回测引擎内**，而是在数据采集时完成
- ⚠️ 回测引擎未验证 `adj_factor` 是否存在或一致
- ✅ 复权策略文档化在 `ExecutionDataContract.adjustment_policy`：
  ```python
  adjustment_policy: str = "provider_versioned_adjustment_required"
  ```

#### 风险

- 如果数据库中混入未复权数据，回测结果会失真
- 缺少运行时验证机制确保所有 bar 使用相同复权版本

#### 建议

1. 在回测引擎 `_load_bars()` 中验证 `adj_factor` 字段存在且非空
2. 在 `execution_contract` 中记录实际使用的复权版本（如 `qfq`、`hfq`、`none`）
3. 考虑在 `BacktestResult` 中添加 `adjustment_version` 字段

---

## 6. 退市股票处理（Delisting）

### 状态：**未对齐**

**真源位置**：`engine/execution_model.py:167`

#### 发现

**执行契约声明**：
```python
delisting_policy: str = "retain_last_available_quote_and_mark_delisted"
```

**实际实现**：
- `engine/backtest_engine.py` **未显式处理退市**
- `alpha/backtest.py` **未显式处理退市**
- 数据库无 `delisted` 字段标记退市状态

#### 当前行为

当股票退市时：
1. 数据库停止更新该股票的日线数据
2. 回测引擎在 `_load_bars()` 时加载历史数据
3. 如果持有退市股票，`daily_bars.get(code)` 返回 `None`
4. `_match_orders()` 中 `deferred.append(order)`，订单永久挂起
5. 权益计算使用 `last_close_by_code.get(code, pos["avg_price"])`（最后可用价格）

#### 验证

- ✅ 行为符合 "retain last available quote" 部分
- ❌ **未标记退市状态**（"mark_delisted" 未实现）
- ❌ **未强制平仓退市股票**

#### 风险

- 退市股票继续占用仓位，影响组合表现计算
- 无法区分"临时停牌"和"永久退市"

#### 建议

1. 在 `data/storage.py:StockInfo` 中添加 `delisted_date` 字段
2. 在回测引擎中检测退市，强制按最后价格平仓
3. 在 `BacktestResult` 中记录退市股票列表和平仓日期

---

## 7. 基准对比（Benchmark）

### 状态：**已对齐**

**真源位置**：`engine/execution_model.py:ExecutionDataContract.benchmark`

#### 发现

两个引擎都实现了基准加载和对比：

**engine/backtest_engine.py:393-407**
```python
def _load_benchmark(self, benchmark_code: str, start_date: str, end_date: str) -> list[dict]:
    df = self._storage.get_stock_daily(benchmark_code, start, end)
    if df.empty:
        logger.warning(f"基准 {benchmark_code} 无数据")
        return []
    # 转换为收益率曲线（以第一天为基准归一化到1）
    closes = df["close"].tolist()
    dates = df["date"].tolist()
    if not closes or closes[0] == 0:
        return []
    first_close = closes[0]
    return [
        {"date": d, "equity": round(c / first_close, 6)}
        for d, c in zip(dates, closes)
    ]
```

**alpha/backtest.py** 未直接实现基准加载（留给调用方）

#### 验证

- ✅ 基准声明在 `ExecutionDataContract.benchmark`：`"CSI 300 total return"`
- ✅ 基准数据源可配置：`benchmark_source`、`benchmark_instrument`
- ⚠️ **alpha/backtest.py 未实现基准加载**，调用方需自行处理

#### Alpha 回测和基准

`alpha/backtest.py` 侧重组合构建，基准对比留给外部分析层。这是合理的设计分离。

#### 建议

- 在 `alpha/backtest.py` 的文档中明确说明基准对比由调用方负责
- 或提供可选的基准加载方法，保持接口一致性

---

## 8. 缺失数据处理（Missing Data）

### 状态：**已对齐**

**真源位置**：`engine/execution_model.py:168-169`

#### 发现

**执行契约声明**：
```python
missing_data_policy: str = "skip_missing_bars_and_never_fill_zero"
deferred_execution_policy: str = "retain_order_until_next_tradable_bar; never_fill_missing_quote"
```

**实际实现一致**：

**engine/backtest_engine.py:450-453**
```python
bar = daily_bars.get(order.code)
if bar is None:
    deferred.append(order)
    continue
```

**alpha/backtest.py:262-264**
```python
price = prices.get(code)
if not price or price <= 0:
    unresolved.add(code)
    continue
```

**停牌/涨跌停处理**：

**engine/backtest_engine.py:455-458**
```python
block_reason = self._bar_block_reason(bar, "buy" if order.direction == Direction.LONG else "sell")
if block_reason is not None:
    deferred.append(order)
    continue
```

**alpha/backtest.py:257-260**
```python
if blocked(code, "buy"):
    unresolved.add(code)
    continue
```

#### 验证

- ✅ 缺失数据 bar 不会触发成交
- ✅ 停牌/涨跌停订单延迟到下一个可交易 bar
- ✅ 不使用零价格或空价格填充缺失数据
- ✅ `market_rule.execution_block_reason()` 统一判断可交易性

#### 可交易性判断逻辑

**engine/market_rules.py:127-183**
```python
def execution_block_reason(
    self,
    code: str,
    side: str | None,
    *,
    open_price: Any,
    close_price: Any,
    volume: Any,
    pre_close: Any = None,
    bar_status: Any = None,
    suspended: Any = False,
    limit_up: Any = None,
    limit_down: Any = None,
) -> str | None:
    """Return why a bar cannot be used for a fill, or ``None`` if valid."""
    
    if bool(suspended):
        return "halted"
    if isinstance(bar_status, str):
        status = bar_status.strip().lower()
        if status in {"halt", "halted", "suspended", "停牌", "停牌中"}:
            return "halted"
    # ... 检查价格有效性和涨跌停 ...
```

两个引擎都调用此方法，确保可交易性判断一致。

---

## Agentic 模块验证逻辑对齐

### 状态：**部分对齐**

#### 发现

**agentic/backtest_compiler.py** 编译回测请求时：
- ✅ 传递 `commission_rate`、`stamp_tax_rate`、`slippage`
- ✅ 传递风控配置（`stop_loss_pct`、`max_drawdown_pct` 等）
- ❌ **未显式传递 `execution_contract` 或 `cost_model_version`**

**agentic/backtest_runner.py:41-43**
```python
async def _execute(self, compiled_request: dict[str, Any]) -> dict[str, Any]:
    runner = self._run_backtest or _default_run_backtest
    backtest_request = _build_backtest_request(compiled_request)
```

调用的是 `dashboard/routers/backtest.py:run_backtest()`，后者会创建 `BacktestEngine`，继承默认成本模型。

**agentic/signal_validation.py** 和 **agentic/promotion.py**：
- ✅ 验证回测指标（Sharpe、回撤、交易次数）
- ❌ **未验证执行契约一致性**

#### 风险

- Agentic 模块生成的回测结果可能使用不同的成本版本
- 无法审计 agentic 回测是否使用了与主回测引擎相同的执行规则

#### 建议

1. 在 `BacktestCompileRequest` 中添加 `execution_contract` 字段
2. 在 `agentic/promotion.py:PromotionContext` 中添加 `execution_contract_version` 字段
3. 在晋级门槛中验证执行契约一致性：
   ```python
   if context.execution_contract_version != "generic-assumption-v1":
       failures.append("execution_contract")
       reasons.append("execution contract version mismatch")
   ```

---

## 对齐措施建议

### 高优先级

1. **复权验证**
   - 在 `_load_bars()` 中检查 `adj_factor` 字段
   - 在 `execution_contract` 中记录实际复权版本
   - 添加运行时警告：数据库中缺失 `adj_factor` 时

2. **退市处理**
   - 在 `StockInfo` 表添加 `delisted_date` 字段
   - 在回测引擎中检测退市并强制平仓
   - 在 `BacktestResult` 中记录退市事件

3. **Agentic 执行契约对齐**
   - `BacktestCompileRequest` 接受 `execution_contract` 参数
   - `PromotionContext` 验证执行契约版本
   - 在回测报告中暴露 `execution_contract` 字段

### 中优先级

4. **基准对比统一**
   - 在 `alpha/backtest.py` 中提供可选的基准加载方法
   - 或在文档中明确说明基准对比责任边界

5. **日历验证增强**
   - 在回测开始时检查 `calendar.verified` 标志
   - 如果使用 `weekday_fallback`，在报告中添加警告
   - 提供 `--strict-calendar` 选项，拒绝未验证的日历

### 低优先级

6. **Coverage 可视化**
   - 在 Dashboard 中展示 `per_symbol` 覆盖率
   - 标记覆盖率低于 95% 的股票

7. **执行契约版本管理**
   - 在数据库中记录每次回测使用的 `execution_contract` 版本
   - 支持历史回测结果的契约版本回溯

---

## 残余风险

1. **隐式复权依赖**
   - 当前回测引擎假设数据库中的价格已复权，但无运行时验证
   - 如果数据采集配置变更（如改为不复权），回测结果会失真

2. **退市股票占用仓位**
   - 退市股票使用最后可用价格计算权益，但无法卖出
   - 可能虚增回测净值，掩盖真实风险

3. **Agentic 回测契约未强制验证**
   - Agentic 模块生成的候选策略可能使用不同的成本假设
   - 晋级决策基于不可比的回测结果

4. **日历假日缺失**
   - 默认 `weekday_fallback` 不包含法定假日
   - 回测可能在非交易日执行订单（虽然实际数据缺失会自然延迟）

---

## 结论

| 契约 | 状态 | engine/backtest_engine.py | alpha/backtest.py | agentic/* | 备注 |
|------|------|---------------------------|-------------------|-----------|------|
| 市场日历 | ✅ 已对齐 | 使用 `TradingCalendar` | 使用 `TradingCalendar` | 未直接使用 | 默认为 weekday fallback |
| Next-bar 执行 | ✅ 已对齐 | T+1 开盘价成交 | T+1 开盘价成交 | 继承引擎 | 文档化在 `execution_rule` |
| 成本版本 | ✅ 已对齐 | `ExecutionCostModelVersion` | `ExecutionCostModelVersion` | 继承引擎 | 可序列化、可审计 |
| Coverage | ✅ 已对齐 | 计算 observed/expected | 计算 observed/expected | 未验证 | 支持 per-symbol 覆盖率 |
| 复权处理 | ⚠️ 部分对齐 | 隐式依赖数据采集 | 隐式依赖数据采集 | 隐式依赖 | 缺少运行时验证 |
| 退市处理 | ❌ 未对齐 | 未实现强制平仓 | 未实现强制平仓 | 未处理 | 仅保留最后价格 |
| 基准对比 | ⚠️ 部分对齐 | 已实现 | 未实现 | 未验证 | alpha 留给调用方 |
| 缺失数据 | ✅ 已对齐 | 延迟订单，不填充零 | 延迟订单，不填充零 | 继承引擎 | 通过 `execution_block_reason` 统一判断 |

**总体对齐度**：约 **70%**

**主要差距**：
1. 复权处理依赖数据采集时完成，缺少回测时验证
2. 退市股票未标记和强制平仓
3. Agentic 模块未显式验证执行契约版本

**推荐行动**：
1. 实现高优先级建议（复权验证、退市处理、agentic 执行契约对齐）
2. 在 Dashboard 回测报告中展示 `execution_contract` 完整字段
3. 在晋级门槛中添加执行契约版本一致性检查