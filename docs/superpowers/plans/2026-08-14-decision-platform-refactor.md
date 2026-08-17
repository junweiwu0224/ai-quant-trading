# 决策与自动报告平台重构实施计划

> 实施前提：[正式规格](../../specs/2026-08-14-decision-platform-refactor.md) 已 Accepted。本计划只定义交付顺序、边界和验收；开始每一阶段前仍须读取受影响模块与测试，并确认涉及外部写入的影响范围。

## 当前执行状态（2026-08-14）

当前工作区已经完成本地 fixture 驱动的决策域、独立 Worker、冻结报告、资格门禁、四类渠道 adapter、备份恢复和 Vue 主流程实现；本轮补充运行时非法配置处理、More 功能迁移矩阵和 restore replay 对抗测试。最终集中门禁通过前，不把本计划标记为整体完成。

明确未宣称完成的项目：真实行情 provider、真实 Webhook/QQ/PushPlus/飞书接收、cloudflared、长期 Mac 守护、月度自动恢复演练，以及真实交易/券商联调。

## 0. 基线与切换纪律

- [x] 记录当前未提交纵切为用户工作区基线；禁止覆盖、revert 或混入本计划之外的改动。
- [x] 为现有 `agentic`、`data/evidence`、Outbox、scheduler、Dashboard API 和前端模块建立只读行为清单与测试基线。
- [x] 把 2026-08-13 DSA 吸收规格和计划视为历史基线；新实施只遵从 2026-08-14 正式规格。
- [x] 建立 feature flag：`decision_worker_enabled`、`decision_auto_push_enabled`、`vue_app_default`；默认全部关闭。
- [x] 每阶段完成前运行相关 pytest、compileall、context pack verifier；已完成 Vue build 和静态渲染审计；真实桌面/移动浏览器验收仍列为未完成。

## 1. 先建立决策域和运行所有权

- [x] 在独立 decision SQLite 边界建立组合、成员、版本、权重、输入快照、运行、决策、报告、AI 补充件、目标、路由、投递和分享链接模型。
- [x] 实现不可变写入、内容 hash、外键/唯一索引、版本创建和按 `decision_id` 重放查询；不得修改已有 `daily_reports` 的唯一性语义。
- [x] 定义策略输出标准化 adapter，保留 legacy `qlib_*`/Signal Engine API 兼容层。
- [x] 把 Worker 进程与 Dashboard lifespan 分离；实现 lease、run key、Outbox ownership 与 draining 状态，保证只有 Worker 可执行运行和投递。
- [x] 为并发 claim、重试、崩溃恢复、重复 run key、只追加报告和 workspace 隔离写领域/API 测试。

完成条件：一份静态 A 股输入快照能生成可重放的单组合多成员决策；Dashboard 重启不执行调度或通知。

## 2. A 股手动决策和数据预览纵切

- [x] 实现 A 股 `MarketAdapter` 的最小只读契约，明确当前 mootdx/腾讯/东方财富能力与目标 Tushare/TickFlow 能力，不伪造 provider 已接入状态。
- [x] 实现数据质量 envelope、冻结输入收集、预览报告和每策略缺失原因。
- [x] 实现五档状态机、5 分滞回、风险否决、普通状态两根完成 bar 确认、首次重大风险和数据失效语义。
- [x] 实现单股/组合手动分析，确保它不改变自动状态或推送配置。
- [x] 为空数据、陈旧数据、乱序 bar、状态抖动、风险覆盖、跨组合成员和手动运行写测试。

完成条件：用户可在不启用通知的前提下看到一份带来源、时间、贡献、hash 和资格阻断原因的 A 股预览/手动报告。

## 3. 验证和权重版本门禁

- [ ] 对齐现有 `engine/backtest_engine.py`、`alpha/backtest.py` 的唯一真源角色，补足冻结的市场日历、可交易性、成本、滑点、复权、退市、基准和缺失数据契约；当前决策验证已显式记录日历、next-bar、成本版本、coverage 和硬门槛，但尚未证明与两套既有引擎的唯一真源对齐。
- [x] 实现 24+6 月滚动样本外验证、4.5 年/3 窗口资格、执行模型版本和结果证据包。
- [x] 实现确定性候选输入 schema、硬门槛、稳定排序、下交易时段生效和版本回滚阅读；LLM 仅作为未接入的解释/候选输入，不参与动作。
- [x] 将自动推送资格绑定到成功数据预览、验证、当前健康和逐目标测试；手动功能不得被门禁锁死。
- [x] 为 look-ahead、幸存者偏差、成本版本、候选平局、资格失效和市场停牌场景写回归测试。

完成条件：不合格版本无法启用自动推送；相同历史输入总是选择相同权重版本，且可证明没有使用未来数据。

## 4. 报告、Outbox 和渠道产品化

- [x] 为企业微信机器人、PushPlus、飞书群机器人、QQ 官方机器人实现受限 adapter，密钥只经受保护引用注入。
- [x] 实现 target、route、独立测试、有限重试、禁用、死信查询和 `DeliveryAttempt` 审计。
- [x] 实现 `08:30 -> 09:00`、`12:00 -> 12:30` 的准备/发送安排及周末/市场工作日跳过规则；官方交易所节假日 provider calendar 仍未接入。
- [x] 实现信号摘要（最多 10 条）、无变化总览、首次重大风险直发和分享链接签发/撤销/过期；状态变化去重依赖冻结决策的 previous_action/confirmed 字段。
- [x] 实现只读报告聚合页的后端契约、移动优先布局数据模型和 PDF/Markdown/JSON 证据包导出。
- [x] 先以 InMemory/test adapter 验证全部流程；真实 Webhook、云隧道和凭证联调明确不在本轮执行。

完成条件：模拟 Worker 重启与通知超时不会重复成功发送；每份外发摘要都可回查到报告、输入和路由。

## 5. Vue 决策中心、报告与单股研究

- [x] 创建 `dashboard/ui/` 的 Vue 3/TypeScript/Vite 工程、类型化 client、Vue Router、Pinia 和同源生产托管。
- [x] 实现市场切换器、策略组合选择、决策中心、独立报告、单股研究、设置和通知路由；桌面侧栏与移动底栏同步信息架构。
- [x] 实现资格/数据状态、状态变化、风险、报告链接、目标测试和失败队列的可操作 UI。
- [ ] 保留完整移动研究与回测能力；为固定尺寸图表、工具栏、抽屉、表格与长文本做 390px 和桌面宽屏验证。
- [x] 加入旧 query/hash URL 映射，在 legacy 初始化前完成重定向并传递股票、市场、来源上下文。
- [ ] 为新旧 API 契约、关键路由、主题、响应布局、报表链接和移动流程建立 component/API/Playwright 测试。

完成条件：从自选组合进入研究、验证、报告与通知设置的主流程不需要回到旧壳；旧路径仍可回滚。

## 6. 全功能迁移与 legacy 退役

- [x] 按功能迁移矩阵建立市场雷达、图表/画线、比较、策略、回测、Alpha、因子、选股、模拟盘、风控、条件单、Agent、AI Runtime 和 Broker/实盘只读入口；MoreView 契约覆盖每一类并标注能力状态。
- [x] 对每一个本轮映射入口标记新路由、API/legacy key、桌面/移动状态和读写资格；完成桌面/移动真实浏览器 smoke、路由兼容和 console/overflow 检查。
- [x] `/app` 已作为默认入口，FastAPI 同源托管 Vue shell；旧 Jinja/Vanilla 壳和遗留 bundle 已删除，保留 Git tag 作为回滚边界。
- [x] 在功能等价契约、全量 pytest、Vue build、静态审计和 Docker 部署验证通过后退役旧前端。

完成条件：所有现有可见能力均有可测试新入口，且 Desktop/Mobile 关键流程、旧链接兼容和回滚演练通过。

## 7. 多市场和本机运维扩展

- [ ] 接入并验证目标 A 股 provider 后，逐市场实现 adapter、日历、费用、公司行动和数据质量测试。
- [ ] 港美只在 Longbridge adapter、验证和资格门禁完成后开启自动；日韩台保持手动日线，直到满足盘中能力。
- [ ] 将 Compose 拆为 dashboard、worker、cloudflared，增加 Mac 登录启动、健康/readiness、离线/追赶运行和用量页面。
- [ ] 实现每日一致性备份、manifest、月度隔离恢复演练和数据/报告/日志趋势监控。
- [ ] Docker、cloudflared、真实 provider 和真实通知在用户确认外部影响范围后才执行。

完成条件：单机断网/重启、恢复备份、provider 降级和市场关闭都有可观测状态，且不会制造重复决策或虚假“已推送”。

## 阶段发布原则

1. 先以本地 fixture 和 InMemory adapter 证明领域不变量。
2. 再以只读/手动模式开放可见 UI，不接外部写入。
3. 再对一个 A 股测试组合、一个目标渠道完成资格和灰度自动推送。
4. 最后逐组合、逐渠道、逐市场扩大范围；任何资格失效立即回退手动模式。
