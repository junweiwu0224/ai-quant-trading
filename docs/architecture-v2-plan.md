# AI Quant Trading 架构 V2：可信研究到可恢复执行

状态：目标架构基线，尚未代表当前代码已经实现

适用范围：单机/小规模 A 股量化系统，Python + FastAPI + Vue + SQLite，模块化单体加独立 Worker，模拟盘优先，实盘默认关闭。

## 1. 结论

V1 的方向是对的，但不能直接作为施工图。它把页面组织、研究流程、交易执行和异步任务压缩成一条漂亮的线，却没有把真正的安全边界落实到状态所有权和事务边界上。

V2 的不可替代目标是：

> 把不确定的市场事实和研究假设，转换成可复现、可质疑、经过风险约束、可恢复的决策与执行证据链。

因此 V2 优先级固定为：

```text
正确性与安全性
  > 可复现性与审计
  > 故障恢复与可运维性
  > 用户流程效率
  > 新功能数量与性能
```

这不是对所有交易系统都“绝对最佳”的方案，而是在当前单机 SQLite、模拟盘优先、真实 Broker 尚未可用的约束下，复杂度和可信度最平衡的方案。

## 2. 第一性原理审查

### 2.1 可被替代的东西

以下能力有价值，但不是系统的核心护城河：

- AI 解读、自然语言选股和报告润色
- 因子数量、指标数量和页面数量
- 单独的策略编辑器或漂亮的 Dashboard
- 多种通知渠道和导出格式
- 未来接入某一个具体券商

它们都不应决定核心状态模型。

### 2.2 不可替代的四条事实

1. **证据事实**：系统使用了什么市场观察、数据快照、范围成员、策略版本和风险规则。
2. **执行事实**：系统实际接受了什么意图、做了什么风控决定、产生了什么订单、成交和账本分录。
3. **所有权事实**：哪个 Worker 在什么租约和 fencing token 下拥有写入权。
4. **恢复事实**：任务失败、进程丢失、外部状态不明或账本不一致时，系统如何停止、重试、对账和恢复。

任何页面或 AI 结果都不能替代这四类事实。

### 2.3 V1 的可证伪反例

| 等级 | 反例 | 代码证据 | V2 修正 |
|---|---|---|---|
| P0 | Dashboard 和 CLI 都能直接启动 PaperEngine，多个进程可同时处理同一订单 | `dashboard/routers/paper_control.py:157`、`scripts/run_paper.py:49` | 命令客户端化；PaperWorker 按 `environment + account` 持有唯一 lease |
| P0 | 订单进入执行队列后，旧的预检查可能因账户状态变化而失效 | `docs/backend-target-architecture.architecture.json` 的 V1 `RiskGate -> TradeQueue` 顺序 | Worker 在 Adapter 前基于最新账户快照重新 RiskGate，并原子预留风险/现金 |
| P0 | 手工订单在策略订单过滤之后才加载，绕过同一风控路径 | `engine/paper_engine.py:254-262`、`:570-596` | 手工、策略、条件单统一为 `OrderIntentBatch` |
| P0 | `PaperEngine` 的 `Order` 导入、方向枚举和订单类型转换存在可验证不一致 | `engine/paper_engine.py:30,581-596`、`engine/models.py:11-14` | 只允许统一命令协议进入执行 Worker，旧表写入路径隔离并下线 |
| P0 | RiskManager 被 API 和引擎分别实例化，规则更新不一定作用于真实下单路径 | `dashboard/routers/paper_trading.py:693`、`engine/paper_engine.py:143` | `RiskPolicyVersion` 不可变；最终 RiskGate 只在执行 Worker 内拥有权威性 |
| P0 | 启动 Paper 不要求策略版本、资格结果或人工批准 | `dashboard/routers/paper_control.py:67-72` | 创建 `ExecutionRun` 时数据库约束强制绑定冻结引用 |
| P0 | SQLite 和运行时的 logs/paper/portfolio_state.json 双写，数据库失败后仍可能保存 JSON | `engine/paper_engine.py:270-273,601-709` | 交易账本成为唯一事实源；JSON 只允许导出快照 |
| P1 | Paper 表以代码为全局持仓维度，缺少 workspace/account/environment 隔离 | `engine/migrate.py:27-72` | 所有执行事实带 `execution_run_id` 和 `account_id`，关键约束包含环境维度 |
| P1 | 批量订单逐笔检查，不能保证组合级现金、行业和仓位约束 | `engine/paper_engine.py:534-554`、`risk/position.py:50-65` | 批量 RiskGate，一次性返回全批/部分/全拒绝并记录原因 |
| P1 | Live 路径创建风控对象但下单前未形成统一强制闸门，CLI 还提供 `--no-risk` | `engine/live_engine.py:92,154,260`、`scripts/run_live.py:29` | V2 不开放 Live；代码协议中禁止无风控执行 |
| P1 | AI provider 最长调用时间超过 Worker lease，可能重复发起不可撤销的外部调用 | `engine/ai_worker.py:32,51,98-105` | 持续 heartbeat、attempt/fence、幂等 artifact key；旧 Worker 失去 fence 后不能写终态 |
| P1 | reset 只重置 JSON，未同步清理订单、成交和持仓 | `dashboard/routers/paper_control.py:171` | 不提供原地 reset；创建新 ExecutionRun，旧运行先归档/对账 |
| P2 | 阻断节点已画出，但没有真实的失败、重试、撤单和恢复转移 | `docs/user-functional-journey.workflow.json:45-57` | 将 ResearchCase、Task、ExecutionRun、Reconciliation 分成可执行状态机 |
| P2 | 现有 Paper/Live 测试大量关闭风控，不能证明端到端安全链 | `tests/test_paper.py:196`、`tests/test_live.py:170` | 新增真实启用风控的 command → permit → fill → ledger 测试 |

## 3. V2 核心模型

### 3.1 统一研究范围，不统一业务语义

不为单股、Universe、Basket、Portfolio 各写一套流程。用不可变 `ScopeSnapshot` 统一下游输入，但保留来源语义：

```text
ScopeDefinition
  ├─ Instrument
  ├─ UniverseDefinition
  ├─ BasketVersion (可带目标权重)
  └─ PortfolioSnapshot (来自账本的持仓/成本快照)

ScopeSnapshot
  ├─ kind: instrument | universe | basket | portfolio
  ├─ members[]
  ├─ weights[] / constraints
  ├─ market_context
  ├─ captured_at
  └─ content_hash
```

研究和执行只消费 `ScopeSnapshot`，不直接读取会变化的筛选结果或当前组合表。

### 3.2 领域实体和关系

```text
Workspace
  -> Environment(paper | live-disabled)
  -> TradingAccount
  -> MarketContext

ScopeSnapshot
  + DataSnapshot
  + StrategyVersion
  -> ResearchCase
  -> ResearchRun(mode=exploratory | executable)
  -> ResearchArtifact / ValidationRun
  -> Qualification
  -> Approval

RiskPolicyVersion
  + Approval
  + frozen references
  -> ExecutionRun
  -> ExecutionCycle
  -> OrderIntentBatch
  -> RiskDecision
  -> ExecutionPermit
  -> Order
  -> AdapterAck / Fill
  -> LedgerEntry
  -> PositionProjection / PerformanceProjection
  -> ReconciliationCase
  -> Review / PromotionCandidate

Command
  -> Task
  -> TaskAttempt(lease, fence, retry, idempotency)

Any authoritative write
  -> AuditEvent
  -> OutboxEvent
```

`ExecutionRun` 是一次模拟/实盘运行的聚合根；`ExecutionCycle` 是运行中的一次决策/行情周期；`OrderIntentBatch` 是一次组合级订单意图。这样既能支持长期策略运行，也能保证每批订单以整体接受或拒绝。

### 3.3 不可变事实与可变投影

**不可变或只能追加补偿的事实：**

- provider observation 及来源、时间、请求参数
- ScopeSnapshot、DataSnapshot、StrategyVersion
- ResearchArtifact、ValidationRun、Qualification、Approval
- OrderIntentBatch、RiskDecision、ExecutionPermit
- Order、AdapterAck、Fill、LedgerEntry
- Report、AuditEvent、OutboxEvent、ReconciliationCase

修订通过新版本、新运行或补偿分录完成，不原地覆盖历史事实。

**可重建投影：**

- 任务当前状态和进度
- ExecutionRun 当前状态
- 当前订单列表视图
- Position、equity、performance
- Worker health/readiness
- 报告索引和通知状态视图

任何投影都可以从权威事实重建；投影损坏不能改变账本。

## 4. 状态模型

不要把所有生命周期压成一条状态机。V2 使用三个互相引用但独立的状态机。

### 4.1 ResearchCase

```text
DISCOVERING
  -> SCOPE_FROZEN
  -> EXPLORING
  -> CANDIDATE_FROZEN
  -> VALIDATING

VALIDATING
  -> BLOCKED_DATA -> DATA_REPAIRING -> SCOPE_FROZEN
  -> BLOCKED_VALIDATION -> STRATEGY_REVISING -> CANDIDATE_FROZEN
  -> QUALIFIED -> AWAITING_APPROVAL -> APPROVED

任何 scope/data/strategy/policy hash 改变
  -> QUALIFICATION_INVALIDATED -> CANDIDATE_FROZEN

APPROVED -> SUPERSEDED
```

`exploratory` 研究允许不完整数据和 AI 辅助，但永远不能创建 `ExecutionPermit`。`executable` 研究必须绑定完整快照、确定性验证和资格记录。

### 4.2 ExecutionRun

```text
CREATED -> READY -> RUNNING
READY -> BLOCKED
RUNNING -> PAUSED -> RUNNING
RUNNING -> HALT_REQUESTED -> HALTED
HALTED -> CANCEL_PENDING -> RECONCILING
RUNNING -> RECONCILING
RECONCILING -> COMPLETED
RECONCILING -> RECONCILIATION_BLOCKED
任何关键事实变化 -> BLOCKED / 重新审批
```

恢复前置条件必须显式记录：

```text
风险暂停
  -> 撤单确认
  -> 未完成订单检查
  -> 账本/外部状态对账
  -> 人工批准（如需要）
  -> 最新 RiskGate
  -> 才能恢复
```

### 4.3 Task / Attempt

```text
QUEUED -> CLAIMED -> RUNNING
RUNNING -> SUCCEEDED
RUNNING -> RETRY_WAIT -> CLAIMED
RUNNING -> FAILED -> DEAD
RUNNING -> CANCEL_REQUESTED -> CANCELLED
租约过期 -> RECLAIMED_ATTEMPT -> 新 fence
```

旧 Worker 失去 fence 后禁止写成功、失败或报告终态。不可取消的外部调用必须通过 `attempt_id + idempotency_key` 抑制重复产物。

## 5. 运行时所有权

| 逻辑 Owner | 唯一可写事实 | 实施约束 |
|---|---|---|
| Control API | command inbox、不可变配置版本 | 只校验、入队、返回 task/run id；不启动引擎 |
| DataWorker | provider observation、DataSnapshot、freshness | 每个 market/provider 分区有明确 owner |
| Research/Decision Worker | ResearchRun、ValidationRun、Qualification、报告索引 | 初期可与 DecisionWorker 同进程，逻辑边界先于进程拆分 |
| AIWorker | AI Task Attempt、AI Artifact、AI Report | 无 decision/order/notification 写权限；持续 heartbeat/fence |
| PaperWorker | Paper Adapter、Order、Fill、Ledger、Paper Reconciliation | `execution:paper:<account_id>` 唯一 lease |
| LiveWorker | Live 本地 ack/fill/ledger/reconciliation | 默认禁用；只能使用稳定 `client_order_id` 查询/恢复 |
| DeliveryWorker | Outbox delivery attempt | 初期可作为 DecisionWorker 的独立循环，不能由 API 直接投递 |
| Projection/Reconcile | 可重建 read model、差异案例 | 不能修改原始 Fill/Ledger，只能写补偿事实 |

**关键区分：逻辑所有权不等于必须立即增加进程。** V2 初期只需要 Dashboard、Research/Decision Worker、PaperWorker 和可选 AI Worker；Delivery/Data 可以按独立逻辑 owner 实现，暂不强制拆成更多服务。

## 6. 交易命令协议

```text
Command accepted (idempotency_key)
  -> Task created
  -> Worker claims Attempt (lease + fence)
  -> load immutable ExecutionRun context
  -> build OrderIntentBatch
  -> latest account/ledger snapshot
  -> final RiskGate + reservation (same transaction)
  -> ExecutionPermit
  -> PaperAdapter / LiveAdapter
  -> Ack / Fill observation
  -> Order + LedgerEntry + AuditEvent + OutboxEvent (transaction)
  -> rebuild projections
  -> Reconciliation status
```

### 风控位置

API 层可以做预检查帮助用户，但只能是提示。权威闸门必须：

- 位于 Paper/Live Worker 内；
- 紧邻 Adapter 调用；
- 使用最新账户、持仓、风险预留和市场规则；
- 对整批意图一次性检查；
- 产生不可变 `RiskDecision` 和一次性 `ExecutionPermit`；
- 任何缺失、过期或不一致都 fail closed。

### Paper 与 Live

二者共用协议，不共用状态目录或适配器：

```text
ExecutionCommand
  -> RiskDecision / ExecutionPermit
  -> PaperAdapter  -> deterministic Fill -> LedgerEntry
  -> LiveAdapter   -> broker ack/fill -> local LedgerEntry -> Reconciliation
```

Live 在 V2 中保持 `live-disabled`。没有 Broker、权限、撤单、断线恢复、幂等下单和对账证据时，不创建可执行的 Live Permit。

## 7. SQLite 最小落地

V2 不引入 Kafka、Kubernetes 或微服务。新增一个执行/运营权威库（可命名 `operations.db`），至少包含：

```text
commands
 tasks
 task_attempts
 worker_leases
 execution_runs
 execution_cycles
 scope_snapshots
 data_snapshots
 strategy_versions
 qualifications
 approvals
 risk_policy_versions
 order_intent_batches
 risk_decisions
 execution_permits
 orders
 adapter_observations
 fills
 ledger_entries
 reconciliations
 audit_events
 outbox_events
 projection_checkpoints
```

约束：

- WAL + `busy_timeout` + 外键 + `CHECK` + `UNIQUE`；
- claim/reserve/commit 使用短事务和 `BEGIN IMMEDIATE`；
- 并发长任务不持有数据库事务；
- `execution_run_id`、`account_id`、`environment` 出现在所有交易事实和唯一约束中；
- JSON 不参与交易启动恢复，只能作为导出或诊断文件；
- 备份以数据库 online backup + artifact manifest/hash 为单位；
- 恢复先 `verify-only`，再隔离恢复，最后进入 `RECONCILIATION_REQUIRED`，禁止直接继续撮合。

研究和 AI 现有数据库可以在迁移期继续保留，但所有进入执行域的引用必须转成不可变 ID + content hash；不允许执行 Worker 直接依赖可变 AI/研究表。

## 8. 前端 V2 信息架构

一级工作区按用户任务，而不是按后端模块：

1. **发现**：市场事实、Universe 定义、候选集合；唯一核心产物是 `ScopeSnapshot`。
2. **研究**：探索/可执行模式显式区分；展示证据来源、数据质量、策略版本和 AI artifact。
3. **验证**：ValidationRun、资格失败原因、重新运行、人工批准。
4. **执行**：账户、环境、ExecutionRun、RiskGate 结果、订单、成交、持仓、暂停和对账；Live 仅显示禁用原因。
5. **运营**：任务、审计、报告、通知、Worker 健康、备份和恢复演练。

`决策中心`降级为跨工作区的只读首页/读模型，不再成为新的状态 owner。AI 变成研究工作区的辅助工具，不成为一级交易入口。

固定上下文按需要显示：

```text
workspace · account · environment · market
ScopeSnapshot · StrategyVersion · Qualification · ExecutionRun
```

按钮只表示命令已接受，页面必须展示 task/run 状态；URL 使用稳定 ID 作为 canonical context，不依赖隐式 Pinia 状态恢复。

## 9. 分阶段迁移和硬门禁

### Phase 0：封堵现有危险路径

- Live 保持关闭；移除/阻断 `--no-risk` 生产路径。
- 禁止新增直接 `PaperEngine` 入口。
- 为手工买/卖/限价、条件单、策略单建立端到端失败测试。
- 将旧 Paper API 标记为 legacy，不再扩展。

硬门禁：缺少最终 RiskGate、账户隔离或幂等键时，不能进入下一阶段。

### Phase 1：单一 Paper owner

- 建立 `operations.db` 和 `execution:paper:<account>` lease。
- Dashboard、CLI 改为提交命令；PaperWorker 成为唯一执行者。
- JSON 降为导出，不再参与恢复。
- 同一账户并发启动只允许一个 owner。

硬门禁：kill/restart、双 Worker、重复命令均不能重复成交；数据库与投影可重建。

### Phase 2：统一执行协议和 RiskGate

- manual/strategy/conditional/stop-loss 全部生成 `OrderIntentBatch`。
- Worker 在 Adapter 前重新检查并预留组合资源。
- Order、Fill、Ledger、Audit、Outbox 原子提交。

硬门禁：现金、单票、行业、总仓位、T+1、限价、暂停和批量部分批准测试全部通过。

### Phase 3：冻结研究和资格链

- 引入 ScopeSnapshot、DataSnapshot、StrategyVersion、ValidationRun、Qualification、Approval。
- ExecutionRun 创建时强制引用完整 hash 集。
- 任一引用变化自动使资格失效。

硬门禁：缺少引用、过期数据、AI-only artifact 或未批准状态都无法生成 ExecutionPermit。

### Phase 4：恢复、对账和备份

- 账本重建 Position/Performance 投影。
- claim、risk、adapter、commit 各关键点故障注入。
- 完成 backup manifest、verify-only、隔离 restore、replay 和 reconciliation。

硬门禁：任何中断点都不能产生重复成交；不一致必须进入 halt/reconciliation，不能自动放行。

### Phase 5：前端状态迁移

- 五个工作区切换为 V2 Context + Task/Run 状态。
- legacy 路由只做兼容重定向。
- 浏览器验证 blocked/retry/paused/halted/reconciling 流程。

硬门禁：用户看到的是持久状态，不是请求返回即成功；workspace/account/environment 隔离测试通过。

### Live 启用条件

Live 不是 V2 交付目标。只有以下全部通过，才另立版本：

- Broker sandbox 幂等下单和稳定 client order id；
- 部分成交、撤单、断线重连和未知状态查询；
- 本地账本与 Broker 对账；
- 权限、kill switch、人工演练和恢复演练；
- 审计、备份和回放证据完整。

## 10. V2 明确不做

- 不拆微服务，不引入 Kafka、Kubernetes、分布式事务或工作流平台。
- 不做全域 event sourcing；只对交易事实、attempt、audit/outbox 使用追加记录。
- 不接真实券商、不开放 Live、不允许无风控执行。
- 不做 Tick/L2、跨市场自动执行、高可用集群或多地域容灾。
- 不允许 AI 自动晋级、审批、下单、修改风险策略或拥有通知状态。
- 不为 Instrument、Universe、Basket、Portfolio 各复制一套研究/回测/执行引擎。
- 在执行可信链路完成前，不继续扩展新策略页面、报告样式或导航入口。

## 11. V2 完成定义

V2 不是“图画完”或“页面能点”，而是同时满足：

```text
没有绕过唯一执行 Worker 的订单路径
+ 没有 JSON/SQLite 双事实源
+ 没有缺少冻结引用的 ExecutionRun
+ 没有只在 API 层生效的 RiskGate
+ 没有无幂等键的副作用命令
+ 没有无法解释的 halted/reconciliation 状态
+ 没有把 AI artifact 当成权威决策
```

在这些条件未满足前，系统只能称为研究/模拟实验系统，不能把“目标架构”描述为已具备实盘安全能力。
