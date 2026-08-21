# V2 重构完成报告

日期：2026-08-21
分支：`codex/surpass-dsa`
HEAD：`bd6986a` + 收尾修复（未提交）

## 总览

V2 重构完成了 Paper 执行从"多路径、多事实源、无冻结引用"到"唯一 Worker、SQLite 权威 ledger、冻结研究链、durable 前端状态"的迁移。Live 不是 V2 交付目标，保持永久关闭。

## 已提交的 Phase 记录

| Phase | 提交 | 核心内容 |
|-------|------|---------|
| Phase 0 | `e8f369d` | 封堵 Dashboard/CLI 直启 PaperEngine，关闭 `--no-risk` |
| Phase 1 | `e8f369d`, `470fa2d` | PaperWorker 唯一 owner，Lease/Fence，Task/Attempt |
| Phase 2 | `b495bbb`→`7da72dd` | 手工单/条件单/策略信号/止损止盈统一 OrderIntent 协议 |
| Phase 3 | `d7edd79` | 冻结研究链、RiskGate 权威、PaperAdapter 只接受 SQLite permit |
| Phase 4 | `dadc91a`, `5f6e640` | SQLite projections、恢复、对账、备份/恢复、durable read model |
| Phase 5 | `bd6986a` | V2 Context API、Pinia 状态、前端 fail-closed、Task/Run 展示 |

## 本轮收尾修复（未提交）

1. **`ConditionalOrderEngine` account_id 参数化**：`_execute_rule()` 不再硬编码 `account_id="default"`，改为使用构造器注入的 `self.account_id` / `self.workspace_id`。
2. **`get_v2_context()` endpoint-level 授权测试**：新增 3 个测试覆盖 default→owned workspace 解析、命名 workspace 绑定通过、account_id 不匹配拒绝。
3. **V2 完成报告最终版**。

## V2 完成定义对照

| 条件 | 状态 | 证据 |
|------|------|------|
| 没有绕过唯一执行 Worker 的订单路径 | ✅ | 手工单/条件单/策略信号/止损止盈全部经 `PaperCommandClient` → `PaperWorker` → `PaperAdapter` |
| 没有 JSON/SQLite 双事实源 | ✅ | `paper_ledger` 是唯一执行事实源；positions/trades/equity/performance 是 SQLite projection |
| 没有缺少冻结引用的 ExecutionRun | ✅ | `ResearchFactsStore.ensure_paper_run()` 强制 hash 验证 |
| 没有只在 API 层生效的 RiskGate | ✅ | `RiskGate` 在 Worker/PaperEngine 内、Adapter 前执行；API permit 是 advisory |
| 没有无幂等键的副作用命令 | ✅ | 所有命令经 `OperationsStore.accept_command()` 幂等 |
| 没有无法解释的 halted/reconciliation 状态 | ✅ | 前端 `v2Context` 对 halted/reconciling/reconciliation-required 阻断并展示原因 |
| 没有把 AI artifact 当成权威决策 | ✅ | `ai_authority: non_authoritative`，AI 不能创建 Approval/Permit/Order |

## 七条件全部满足 → V2 Paper 系统可交付

**但以下边界仍然存在**（不阻止 V2 交付，记录为已知限制）：

1. **多 workspace Paper account 绑定**：当前账户模型没有独立的持久 `paper_account_id` 字段。默认 workspace 使用 `paper-default`；命名 workspace 必须在 `workspace.settings.paper_account_id` 中显式绑定，否则返回 `unbound`。
2. **条件单 router 单例**：`ConditionalOrderEngine` 是全局单例，`account_id`/`workspace_id` 在实例化时固定。多 workspace 隔离依赖 Worker 端的 lease/fence 检查。
3. **`_task_rows()` 查询范围**：当前查询全局最新 100 条 task 再按 account/workspace 过滤。极端情况下，繁忙 workspace 的旧 task 可能被截断。
4. **浏览器登录验证**：本轮未使用真实登录凭证验证 Paper 执行页；已验证未登录路由重定向和本地 mock/契约路径。
5. **legacy 兼容路由**：`/api/paper/*` 仍保留作为兼容层；完整 workspace-aware Paper command 写路径需账户绑定方案确定后迁移。

## 验证证据

```text
Python pytest:   1108 passed, 1 warning
Vue/Vitest:      43 passed
Vue build:       passed (vue-tsc --noEmit + Vite production)
compileall:      passed
Compose config:  passed
Context pack:    passed
git diff --check: passed
```

## 文件清单

### 新增
- `engine/research_facts.py` — 不可变研究事实对象
- `engine/research_snapshots.py` — 快照管理
- `engine/qualification.py` — 资格记录
- `engine/risk_gate.py` — 权威风控门禁
- `engine/paper_projection.py` — SQLite projections
- `engine/paper_read_model.py` — durable read model
- `engine/paper_runtime.py` — Paper runtime store
- `engine/paper_worker.py` — 唯一 Paper 执行 owner
- `engine/operations_store.py` — 命令/任务/幂等存储
- `dashboard/routers/v2_context.py` — V2 Context API
- `dashboard/ui/src/stores/v2Context.ts` — Pinia V2 状态
- `scripts/run_paper_worker.py` — PaperWorker 独立启动

### 修改
- `engine/paper_engine.py` — 统一 OrderIntent 协议
- `engine/adapters/paper_adapter.py` — 只接受 SQLite permit
- `engine/conditional_order.py` — account_id 参数化
- `dashboard/routers/paper_control.py` — V2 控制接口
- `dashboard/routers/paper_trading.py` — durable read model
- `dashboard/routers/portfolio.py` — V2 projection reads
- `dashboard/ui/src/views/PaperRiskView.vue` — V2 状态闸门
- `dashboard/ui/src/components/MainContent.vue` — V2 状态展示

### 测试
- `tests/test_phase3_execution.py` — Phase 3 聚焦
- `tests/test_paper_phase4_*.py` — Phase 4 projections/recovery/authority
- `tests/test_v2_context.py` — V2 Context API 授权
- `tests/test_vue_paper_contract.py` — Paper 前端契约
- `dashboard/ui/src/stores/v2Context.spec.ts` — Pinia 状态
- `dashboard/ui/src/client.spec.ts` — API client URL 契约
