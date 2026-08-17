# DSA 能力选择性吸收规格

状态：Superseded（由 [决策与自动报告平台重构规格](2026-08-14-decision-platform-refactor.md) 取代）  
创建日期：2026-08-13  
参考项目：`ZhuLinsen/daily_stock_analysis` `main`（评估基线：2026-08-10 commit `3b98aa1d779a3525660b5bd95a2b297278808464`）

## 1. 目标

将 `daily_stock_analysis` 的高价值能力吸收到 AI Quant Trading，使系统形成：

```text
市场/个股情报
  -> 证据快照
  -> AI/规则研究报告
  -> 结构化 Decision Signal
  -> T+N 后验验证
  -> 回测/风控门禁
  -> 人工确认的模拟盘
  -> 日报与通知
```

吸收目标是增强现有量化系统的投研入口和信号质量，而不是复制 DSA 的 Web、桌面端、数据库或回测实现。

## 2. 产品边界

### 2.1 第一阶段范围

- A 股优先；保留现有 A 股代码、交易日历和交易规则。
- 每日市场复盘、个股研究报告、新闻/公告/热点证据聚合。
- 结构化决策字段：动作、评分、置信度、周期、入场区间、止损、目标、失效条件、观察条件、风险和催化因素。
- 研究报告引用可复现的 Evidence snapshot，而不是只保存 LLM 文本。
- Decision Signal 接入现有 Signal Ledger、PromotionPolicy、Outbox 和 PaperEngine。
- 增加“AI 建议后验验证”，但不替换已有策略/组合回测。

### 2.2 延后范围

- DSA 的完整 Web/Desktop 工作台和多市场 UI。
- 港股、美股、日股、韩股、台股的完整统一估值和交易语义。
- 自动实盘下单、券商 SDK、复制交易。
- 独立的第二套回测数据库或 DSA `BacktestService`。
- 把 LLM 自由生成的 Python 代码直接投入回测或交易。

## 3. 现有模块复用

| DSA 能力 | AI Quant 现有接缝 | 吸收方式 |
|---|---|---|
| 多源新闻、热点、情绪 | `alpha/news_collector.py`、`alpha/hotspot_attribution.py` | 扩展现有采集器和标准化字段，不复制 DSA provider runtime |
| 证据可追溯 | `data/evidence/` | 作为所有报告和信号的证据真源；报告只引用 snapshot/item ID |
| 多角色研究 | `agentic/research_pipeline.py` | 从当前 signal/market/theme/bear/decision 骨架扩展为可验证角色编排 |
| DecisionSignal | `agentic/models.py`、`agentic/signals.py`、`agentic/signal_ledger.py` | 丰富现有 `TradingSignal` 契约，保持旧 `direction/status` 兼容，不再新增第二套生命周期 |
| 选股策略 | `alpha/screener.py`、`strategy/` | 保持“筛选策略”和“单股分析策略”分离，选择性移植 DSA/AlphaSift 策略定义并保留来源 |
| 后验验证 | Signal Ledger outcome / `agentic/performance.py` | 新增 Decision Signal T+N evaluator；不改写 `engine/backtest_engine.py` |
| 每日任务 | `data/scheduler/`、`agentic/daily_workflow.py` | 在现有调度器接入可取消、可重试、可审计的 daily research run |
| 通知 | `engine/events/`、`engine/notifications/` | 研究完成只写 Outbox，由通知 Adapter 投递；不在研究流程内直接发 Webhook |
| 模拟交易 | `engine/paper_engine.py`、`engine/order_manager.py`、`agentic/order_intent.py` | 仅允许通过现有晋级和人工确认流程进入 PaperEngine |
| 真实回测 | `engine/backtest_engine.py`、`alpha/backtest.py` | 继续作为策略/组合回测唯一真源 |

## 4. 核心数据契约

### 4.1 ResearchContext

研究引擎接收一个冻结上下文，至少包括：

- `stock_code`、`market`、`as_of`、`market_phase`。
- 行情和 K 线摘要、技术指标、基本面、资金流、情绪、热点和宏观上下文。
- `evidence_snapshot_id` 及其来源状态、时间窗口、缺失原因和降级信息。
- 当前 Signal Engine 结果、已有仓位风险摘要和数据质量级别。
- 使用的模型、provider、prompt/strategy profile 版本和预算信息。

研究过程不得偷偷重新拉取未记录的数据；需要新增数据时必须创建新的 collection snapshot。

### 4.2 DecisionSignal

Decision Signal 是研究结果的结构化投影，写入现有 Signal Ledger。建议字段：

- 身份：`signal_id`、`stock_code`、`source`、`research_job_id`、`evidence_snapshot_id`。
- 决策：`action`、`legacy_direction`、`score`、`confidence`、`horizon`、`expires_at`。
- 计划：`entry_low`、`entry_high`、`stop_loss`、`target_price`、`invalidation`、`watch_conditions`。
- 解释：`reason`、`risk_summary`、`catalyst_summary`、`factor_contributions`。
- 质量：`data_quality`、`missing_fields`、`source_health`、`model_metadata`。

兼容要求：

- 旧调用仍可使用 `buy/sell/hold/risk` 和现有 `status`。
- DSA 的 `buy/add/hold/reduce/sell/watch/avoid/alert` 映射为结构化 `action`，不能只靠中文文本解析。
- `action`、`score`、`confidence`、`horizon` 缺失时，信号只能进入观察状态，不能自动晋级 Paper。
- `evidence_snapshot_id`、`data_quality` 和模型版本必须随信号保留，便于后验复盘和审计。

### 4.3 两类“回测”必须分开

| 类型 | 目的 | 真源 |
|---|---|---|
| 策略/组合回测 | 逐 bar 模拟策略、订单、成本、持仓和净值 | `engine/backtest_engine.py`、`alpha/backtest.py` |
| Decision Signal 后验 | 验证某次 AI 建议在 T+N 交易日后的方向、止盈止损和可执行性 | 新增 evaluator，结果写入 Signal outcome |

任何产品文案、API 和报告都必须标明属于哪一种，不能把 AI 建议后验准确率称为策略收益。

## 5. 分阶段实施

### P0：每日投研纵切

实现：市场上下文、个股新闻/公告、Evidence snapshot、研究报告、Decision Signal、daily brief、Outbox。

验收：

- 同一研究运行能查询到唯一 context/evidence snapshot。
- 新闻为空、源失败、缓存陈旧和部分字段缺失都有明确状态。
- 报告和信号能反查证据、provider、时间窗口和模型版本。
- LLM 失败时保留确定性行情/因子结果，不能伪造完整 AI 结论。
- 重试不会创建重复报告、信号或通知事件。

### P1：DSA 风格选股与候选池

实现：全市场快照、策略 YAML、硬过滤、因子评分、风险调整、可选 LLM 重排、候选池历史和 source health。

原则：

- 复用 `alpha.screener` 接缝，不能建立第二个 screening runtime。
- 筛选策略与单股分析策略使用不同命名空间和 schema。
- LLM 重排不可用时保留确定性排序，并标记降级。
- 候选池结果要能直接生成回测草案、研究任务和 Paper 观察项。

### P2：后验反馈与通知产品化

实现：Decision Signal T+N outcome、按来源/策略/市场阶段的聚合、日报模板、企业微信/飞书等通知 Adapter。

原则：

- 只读结果先落地；通知写入必须经过 Outbox。
- 后验样本不足时显示样本不足，不排名、不自动调高权重。
- 外部通知失败不能阻断研究、信号和回测结果保存。

### P3：Agent 问股和策略 profile

实现：把 DSA 的策略问股能力转成受限 strategy profile/Agent tool，输出研究假设、筛选条件、回测草案和风险检查，而不是直接喊单或生成任意代码。

### P4：多市场 Adapter

只有在 A 股契约稳定、至少存在两个真实数据 Adapter 后，才增加 `MarketAdapter`。不同市场的交易日历、货币、费用、公司行动和数据质量不能被强行塞进 A 股模型。

## 6. 安全与运行边界

- 所有外部数据源调用必须设置超时、限流、重试上限和 source health。
- 研究、选股和通知默认不触发真实交易。
- Paper 订单必须经过现有 PromotionPolicy、人工确认和 operation id 幂等保护。
- 不读取或提交 `.env`、API key、券商凭证、真实账户和生产数据库。
- 不在默认测试门禁中调用外部 LLM、外部搜索、真实 Webhook、真实数据同步或实盘接口。
- 真实浏览器验收使用本地测试数据；真实外部联调单独执行并记录影响范围。

## 7. 许可证与归因

DSA 根项目为 MIT。DSA 选股实现文档声明其参考并衍生自 AlphaSift，相关文件采用 Apache License 2.0；如果选择性移植实现或策略文件，必须：

- 固定来源项目和 commit。
- 保留原文件许可证和来源头。
- 更新 `THIRD_PARTY_NOTICES` 或本项目对应归因文档。
- 优先吸收行为契约和数据字段，避免无必要的代码复制。

## 8. 回滚

- P0 业务开关：关闭 daily research/notification schedule，已有行情、回测和 PaperEngine 不受影响。
- P1 业务开关：关闭 screening 入口，保留历史候选只读查询。
- 代码回滚：按阶段 revert，不删除 Evidence、Signal outcome 和 Outbox 历史数据。
- 数据迁移必须幂等、向前兼容，禁止通过回滚删除用户研究记录。

## 9. 完成定义

“吸收完成”不等于功能数量对齐 DSA，而是满足：

1. 每日投研链路可重复运行、可追溯、可降级。
2. Decision Signal、策略回测、模拟交易三者语义和数据真源清晰分离。
3. 新闻/公告/热点能从证据进入研究、信号、回测和日报。
4. LLM 失败、数据缺失、通知失败和 Paper 重试不会破坏主流程。
5. 所有 Paper 写操作有人工确认、审计和幂等恢复。
