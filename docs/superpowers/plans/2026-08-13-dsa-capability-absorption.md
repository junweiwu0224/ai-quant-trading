# DSA 能力选择性吸收实施计划（已取代）

> 状态：Superseded。请使用 [决策与自动报告平台重构实施计划](2026-08-14-decision-platform-refactor.md)。本文件保留为 2026-08-13 纵切的历史基线，不得与新规格并行实施。

> 目标：把 `daily_stock_analysis` 的投研、情报、结构化决策和自动推送能力吸收到 AI Quant Trading；保留现有回测、风控和模拟盘为唯一真源。

## 0. 前置冻结

- [ ] 记录 DSA 参考 commit、许可证和本项目吸收范围。
- [ ] 以当前 `agentic`、`data/evidence`、`engine.notifications` 未提交纵切为现状基线，不覆盖用户改动。
- [ ] 确认默认只做 A 股，不引入 DSA 的多市场 UI 和第二套数据库。

## 1. P0 每日投研纵切

- [x] 定义冻结的 `ResearchContext`、`ResearchReport` 和 `DecisionSignal` 兼容字段。
- [x] 将研究输入绑定到 Evidence snapshot/link/raw payload；空快照显式为不可引用。
- [x] 扩展 `ResearchPipeline`，区分市场、技术、基本面、情绪/主题、风险和决策角色。
- [x] 研究结果通过现有 Signal Ledger 发布，报告和信号携带 evidence、source health 和 data quality。
- [x] 复用 daily workflow 生成 daily brief，通过 Outbox 产生通知事件并提供可选 Webhook Adapter。
- [x] 增加 API/领域测试：重复运行、空结果、LLM 降级、证据反查和 T+N 样本不足。
- [ ] 完成对应 Dashboard 本地浏览器 smoke；当前已完成契约测试，浏览器门禁仍待跑。

## 2. P1 DSA 风格选股

- [ ] 在 `alpha.screener` 现有接缝中加入快照 source priority、last-good cache 和 source health。
- [ ] 增加“筛选策略”YAML 命名空间，和现有单股策略保持隔离。
- [ ] 加入硬过滤、评分、风险调整和可选 LLM 重排；LLM 不可用时确定性降级。
- [ ] 持久化 screening run 摘要和候选来源，不新增独立 screening 数据库。
- [ ] 候选池提供“研究、回测草案、加入观察、生成 Paper 申请”的后续动作。
- [ ] 增加 source fallback、字段标准化、候选稳定排序和历史查询测试。

## 3. P2 后验与通知

- [x] 新增 Decision Signal T+N evaluator，复用本地日 K 和 Signal outcome，不改策略回测引擎。
- [ ] 区分方向命中、止盈止损命中、模拟建议收益和策略净值收益。
- [ ] 增加按 source/profile/horizon/market phase 的样本统计，样本不足不排名。
- [ ] 增加 daily brief Markdown/通知渲染器，所有外部投递继续经过 Outbox Adapter。
- [ ] 只在用户确认凭证范围后做真实 Webhook 联调。

## 4. P3 Agent 与策略 profile

- [ ] 将 DSA 策略问股映射到受限策略 profile 和现有 Agent tool registry。
- [ ] 自然语言输出先落成研究假设、筛选条件、回测草案和风险检查。
- [ ] 禁止 LLM 绕过 DSL、PromotionPolicy 或人工确认直接产生 Paper 订单。

## 5. P4 多市场扩展

- [ ] 先定义 `MarketAdapter`，明确行情、公司行动、交易日历、货币和费用契约。
- [ ] 至少完成两个真实 Adapter 后再开放多市场统一页面。
- [ ] 每个市场单独报告覆盖率和不可用能力，不把 A 股字段硬填到其他市场。

## 6. 每阶段验证

- [ ] `.venv/bin/python -m pytest <受影响测试> -q`
- [ ] `.venv/bin/python -m compileall -q .`
- [ ] `.venv/bin/python scripts/verify_context_pack.py`
- [ ] 前端改动运行对应契约测试和 `scripts/frontend_data_render_audit.py`
- [ ] Dashboard 页面改动完成后运行本地 browser smoke
- [ ] 外部数据、LLM、通知、Docker、Paper/Live 相关验证单独确认，不放入默认 hooks
