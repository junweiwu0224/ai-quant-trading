# V2 Phase 4 完成报告

状态：核心恢复、投影、对账和备份链完成  
基线提交：`d7edd79`  
核心提交：`dadc91a feat(phase4): add SQLite paper projections recovery and reconciliation`

## 已完成

- `paper_ledger` 是 Paper 成交事实源；Position、Trade、Equity、Performance 从 scoped ledger 重建。
- `paper_positions_v2`、`paper_trades_v2`、`paper_equity_curve_v2`、`paper_performance_v2` 和 projection checkpoint 可删除后重建。
- Projection fold 验证账户、workspace、environment、ExecutionRun、价格、数量、现金和 T+1 事实；异常不修改 ledger。
- `paper_reconciliations` 和 `paper_reconciliation_events` 记录投影分歧、lease 丢失、引擎失败、reset 和 restore；状态转换受保护并追加审计事件。
- `PaperWorker` 真正启动受账户 lease/fence 保护的 PaperEngine loop；lease 丢失会停止执行并进入 reconciliation-required。
- `paper_reset` 创建新的 immutable ExecutionRun，保留历史 ledger，并将旧 run 置于 reconciliation 流程；不原地清空事实。
- PaperAdapter 强制 SQLite authoritative permit、ExecutionRun scope、decision/permit/batch coverage、当前 fence；提交前在 `BEGIN IMMEDIATE` 内重算现金和持仓。
- Backup verify-only 校验 Paper ledger scope、幂等键和 projection 表；隔离 restore 后不自动恢复 Paper run，统一进入 `reconciling`。
- Dashboard Paper status、positions、trades、equity、performance、close、stoploss 和 portfolio history 使用 V2 scoped read model 或 durable command；JSON 状态文件只保留导出/诊断兼容用途。
- 研究事实的 Approval、workspace/account/environment 绑定、DataSnapshot 完整 hash、深层 mapping 不可变和 ExecutionRun 生命周期均 fail closed。

## 验证结果

```text
Phase 4 projection/lifecycle/backup/failure tests: 9 passed
Phase 4 authority tests: 3 passed
Phase 3 + adapter + worker + runtime: 59 passed
Dashboard/API/data-health/run-dashboard: 154 passed
API v2 + dashboard data-health: 101 passed
Vue tests: 38 passed
Vue build/type check: passed
compileall: passed
Docker Compose config: passed
context pack verification: passed
full pytest before concurrent Phase 5 edits: 1098 passed, 1 warning
```

## 明确边界

- 当前工作树同时存在 Phase 5 前端上下文改动，未纳入本 Phase 4 提交；Phase 5 必须独立完成审查和测试后再提交。
- 旧 `paper_positions`/`paper_trades` 表仍由少数 legacy 风控/绩效辅助模块引用，已不再作为 PaperEngine 启动恢复或 V2 Dashboard 权威读源；完全删除需要单独兼容清理。
- PaperWorker 在单进程内以 daemon thread 运行 PaperEngine；跨进程所有权由 SQLite lease/fence 保证，长期进程、强制 kill 和断电演练仍需独立运行。
- 当前投影提供成交事实和基础权益曲线；realized P&L 的完整配对投影尚未作为权威事实发布，因此交易统计中的盈亏字段在没有专用 projection 时保持零值，不伪造 legacy 结果。

## 后续门禁

Phase 5 需要完成 V2 Context + Task/Run 前端迁移、兼容路由和 blocked/retry/paused/halted/reconciling 展示，并在不污染当前 Phase 4 文件的前提下运行 Vue build、契约测试、Dashboard API 回归和浏览器验证。
