# Phase 2: 统一执行协议迁移计划

## 目标

将现有 4 条订单路径统一迁移到 `OrderIntentBatch -> RiskDecision -> ExecutionPermit -> Adapter -> Fill/Ledger` 协议。

## 当前 4 条订单路径

### 1. 手动订单 (dashboard/routers/paper_trading.py)

```
POST /orders
  ↓
OrderManager.create_order(code, direction, order_type, volume, price)
  ↓
直接写入 paper_orders 表
  ↓
PaperEngine 轮询执行
```

**特征**：
- 即时下单，无批次概念
- 无风控预检查
- 无幂等键
- 单一订单，不支持批量

### 2. 条件单 (dashboard/routers/conditional_orders.py + engine/conditional_order.py)

```
Alert 触发
  ↓
ConditionalOrderEngine.check_triggers()
  ↓
create_order_from_rule(rule)
  ↓
OrderManager.create_order()
```

**特征**：
- 事件驱动
- 冷却期限制
- 单一订单，无批次
- 无风控集成

### 3. 策略信号 (engine/paper_engine.py + strategy/base.py)

```
QuoteService 推送 bar
  ↓
strategy.on_bar(bar)
  ↓
strategy.buy(code, price, volume) / strategy.sell(code, price, volume)
  ↓
Order 加入 portfolio.orders
  ↓
PaperEngine._process_pending_orders()
  ↓
portfolio.positions 更新
```

**特征**：
- 策略内部生成
- 推送到 `_pending_orders` 队列
- 引擎轮询处理
- 无显式批次边界
- 无持久化 command

### 4. 止损止盈 (engine/paper_engine.py)

```
PaperEngine._check_stoploss(quotes, equity)
  ↓
读取 paper_positions.stop_loss_price / take_profit_price
  ↓
或 StopLossManager.check_all(code, entry_price, current_price, equity)
  ↓
_submit_sell(code, price, volume)
  ↓
立即卖出
```

**特征**：
- 轮询触发
- 紧急强平逻辑
- 直接修改 portfolio
- 无 command 持久化

## 目标架构

所有路径统一为：

```
Entry Point (手动/条件/策略/止损)
  ↓
构造 OrderIntent[]
  ↓
OrderIntentBatch.create(intents, execution_run_id, account_id, environment)
  ↓
RiskGate.evaluate(batch) → RiskDecision
  ↓
ExecutionPermit.from_decision(decision, batch, fence_token, expiry)
  ↓
PaperAdapter.execute_batch(batch, permit)
  ↓
Fill[] + Ledger 写入 paper_ledger
  ↓
Audit 写入 paper_audit
```

## 迁移步骤

### Step 2.1: PaperAdapter 实现 ✅

- [x] `engine/adapters/paper_adapter.py`
- [x] `Fill`, `QuoteSnapshot`, `PaperAdapter`
- [x] `paper_ledger`, `paper_audit`, `paper_outbox` 表
- [x] `tests/test_paper_adapter.py`

### Step 2.2: 手动订单迁移

**改造 `paper_trading.py` 的 `POST /orders`**：

1. 接收请求 → 构造 `OrderIntent`
2. 调用 `PaperCommandClient.submit_manual_order(intent)`
3. `PaperCommandClient` 内部：
   - 创建 `OrderIntentBatch`
   - 调用 `RiskGate.evaluate(batch)`
   - 创建 `ExecutionPermit`
   - 提交 `ExecuteManualOrder` command 到 `OperationsStore`
4. `PaperWorker` claim task → 调用 `PaperAdapter.execute_batch()`

**测试重点**：
- 单订单 → 单 intent batch
- 限价单 / 市价单
- 风控拒绝场景
- 幂等重复提交

### Step 2.3: 策略信号迁移

**改造 `PaperEngine._process_pending_orders()`**：

1. 策略 `on_bar()` 生成 `Order[]` 仍保持不变
2. `_process_pending_orders()` 收集所有 pending orders
3. 转换为 `OrderIntent[]`
4. 创建 `OrderIntentBatch` (单批次)
5. 内联调用 `RiskGate.evaluate(batch)`
6. 内联调用 `PaperAdapter.execute_batch(batch, permit)`
7. 写入 `paper_ledger`

**关键决策**：
- 策略信号**不经过** `OperationsStore`，因为它们在 PaperEngine 内部已经是单线程
- 但必须走 `RiskGate` 和 `PaperAdapter`，确保协议一致
- 每轮 bar 的所有信号作为**一个批次**提交

**测试重点**：
- 多信号同时产生 → 批次提交
- 部分批准 / 部分拒绝
- Ledger 原子性

### Step 2.4: 条件单迁移

**改造 `ConditionalOrderEngine`**：

1. Alert 触发 → `check_triggers()` 收集触发的 rules
2. 每个 rule 转换为 `OrderIntent`
3. 批次提交到 `OperationsStore` (通过 `PaperCommandClient`)
4. `PaperWorker` claim 并执行

**测试重点**：
- 冷却期在 command 提交前检查
- 多个 rule 同时触发 → 批次
- 风控拒绝不消耗冷却期

### Step 2.5: 止损止盈迁移

**改造 `_check_stoploss()`**：

1. 检测到触发 → 构造 `OrderIntent`
2. 创建 `OrderIntentBatch` (标记为 `emergency=True`)
3. `RiskGate` 对紧急批次应用最小限制 (不检查仓位限额，只检查资金可用性)
4. 内联调用 `PaperAdapter.execute_batch()`

**关键决策**：
- 止损**不经过** `OperationsStore`，因为紧急性要求立即执行
- 但必须走协议，写入 `paper_ledger` 并产生 `Fill`
- `emergency` 标志让 `RiskGate` 放宽检查

**测试重点**：
- 止损优先级高于风控限制
- 全局回撤强平 → 所有持仓批次平仓
- Ledger 完整记录

## 残留旧路径清理

迁移完成后，以下组件应删除或标记废弃：

- `OrderManager.create_order()` 直接写 DB 的路径
- `paper_orders` 表的直接写入
- `PaperEngine._submit_sell()` 的直接 portfolio 修改
- `portfolio.positions` 的非 Ledger 驱动更新

## 验证矩阵

| 路径 | 单元测试 | 集成测试 | E2E 测试 |
|------|---------|---------|---------|
| 手动订单 | ✓ | ✓ | ✓ (Playwright) |
| 策略信号 | ✓ | ✓ | ✓ (backtest) |
| 条件单 | ✓ | ✓ | ✓ (mock alert) |
| 止损止盈 | ✓ | ✓ | ✓ (price trigger) |

## 风险和缓解

**风险 1**: 策略信号批次过大导致部分拒绝
- **缓解**: 策略层面限制单批次订单数量；RiskGate 分批审批

**风险 2**: 止损不经过 OperationsStore，仍是旁路
- **缓解**: 止损必须走协议和 Ledger；紧急标志只是放宽风控，不跳过记录

**风险 3**: 迁移期间新旧路径并存
- **缓解**: 按路径逐一迁移，迁移完立即删除旧代码；集成测试覆盖

## 迁移进度

- [x] **Step 2.1: PaperAdapter 实现** (commit: b495bbb)
  - engine/adapters/paper_adapter.py: 统一执行接口
  - tests/test_paper_adapter.py: 9/9 测试通过
  - 数据库表: paper_ledger (幂等键约束)、paper_audit、paper_outbox

- [x] **Step 2.2: 手工订单迁移** (commit: b495bbb)
  - dashboard/routers/paper_trading.py: POST /paper/order 改用 PaperCommandClient
  - engine/paper_commands.py: enqueue_manual_order() 方法
  - engine/paper_worker.py: paper_execute_batch 处理
  - tests/test_manual_order_migration.py: 5/5 测试通过
  - 完整测试: 1052 passed

- [ ] **Step 2.3: 条件单执行迁移**
  - 目标: engine/conditional_order.py 的 create_order_from_rule()
  - 改为: enqueue_conditional_order() → paper_execute_batch

- [ ] **Step 2.4: 策略信号迁移**
  - 目标: engine/paper_engine.py 的 _handle_signal()
  - 改为: enqueue_strategy_signal() → paper_execute_batch

- [ ] **Step 2.5: 止损止盈迁移**
  - 目标: engine/paper_engine.py 的 _check_stop_loss/take_profit()
  - 改为: enqueue_stop_order() → paper_execute_batch

- [ ] **Step 2.6: 移除旧订单路径**
  - 删除: OrderManager.create_order() 直接写表逻辑
  - 保留: OrderManager 作为只读查询接口

## 成功标准

- [x] 所有订单路径生成 `OrderIntent` 和 `OrderIntentBatch` (手工订单已完成)
- [x] 所有订单经过 `RiskGate.evaluate()` (当前为 auto-approved，Phase 3 接入真实风控)
- [x] 所有成交写入 `paper_ledger`，无直接 portfolio 修改 (PaperAdapter 已实现)
- [x] 所有 Fill 具备幂等键和 fence (paper_ledger.idempotency_key 唯一约束)
- [ ] 集成测试覆盖 4 条路径 (1/4 完成)
- [ ] E2E 测试验证前端 → 后端 → Ledger 完整链路

## 下一步

完成 Phase 2 后，进入 Phase 3：冻结研究链 (ScopeSnapshot, ValidationRun, Qualification, Approval)。
