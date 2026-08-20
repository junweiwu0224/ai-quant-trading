# Phase 3 完成报告：冻结研究和资格链

状态：Phase 3 核心完成，Phase 4/5 未开始

## 已交付

- `engine/research_facts.py`：SQLite 原生事实仓库和不可变领域对象。
- `engine/research_snapshots.py`、`engine/qualification.py`：兼容导出入口。
- `engine/risk_gate.py`：最终 Paper RiskGate、账户账本重建和权威 permit 持久化。
- `engine/execution_protocol.py`：OrderIntent emergency 标记、协议序列化/反序列化。
- `engine/adapters/paper_adapter.py`：费用、幂等键、workspace/account/environment 隔离、权威 permit 校验和原子成交事实。
- `engine/paper_worker.py`：手工订单在 Worker 内从最新账本和行情重新评估，旧直接改持仓命令 fail closed。
- `engine/paper_engine.py`：策略和止损路径使用同一 RiskGate，并以 SQLite ledger 作为风控输入。
- `tests/test_phase3_execution.py`：24 个冻结链、执行引用、RiskGate 和权威 Adapter 测试。

## 安全边界

API 产生的 permit 只保留兼容性的 advisory payload。真正可交给 Adapter 的 permit 必须由 RiskGate 在同一数据库写入 `paper_execution_permits`，并匹配当前 batch、账户、运行、workspace、fence 和过期时间。Live 仍由协议和事实仓库 fail closed。

研究事实的 hash 被 ValidationRun、Qualification 和 ExecutionRun 逐层引用。创建或执行运行时会重新计算数据快照 hash，并检查数据新鲜度、Qualification 有效期、人工批准、可执行验证模式和 AI-only 禁止条件。

## 验证

```text
Phase 3 focused: 24 passed
Execution/adapter/worker/paper regression: 75 passed
Full pytest: 1089 passed, 1 warning
compileall: passed
```

## 已知边界

Phase 4 仍需把 `portfolio_state.json` 从恢复事实降为导出，增加可重建 Position/Performance projection、ExecutionRun 恢复状态、ReconciliationCase、backup/restore verify-only 和故障注入。Phase 5 仍需将 Dashboard workspace 全面迁移到持久 Task/Run 状态。
