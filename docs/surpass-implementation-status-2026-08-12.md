# 超越 daily_stock_analysis：第一条可验证纵切

本次实现把核心链路收敛为：

Evidence -> Snapshot/Link -> Signal Ledger -> PromotionPolicy -> Outbox -> Notification Adapter

## 已落地的深模块

- data.evidence：SQLite Adapter 与内存 Adapter。资料以 item 保存，以 snapshot 固定一次运行的观测集，以 link 让信号和日报引用同一份证据。
- agentic.signal_ledger：信号状态转换、来源 provenance 和结果 outcome 分开保存；状态转换要求携带当前状态，过期写入会被拒绝。
- agentic.promotion：纸上交易和实盘资格共用一套 PromotionPolicy。实盘资格额外要求纸上观测、收益、回撤和人工批准；它不会发出真实订单。
- engine.events 与 engine.notifications：DomainEvent 进入 SQLite outbox，按幂等键去重，claim/ack，区分可重试失败与 dead-letter；通知传输只是 Adapter。
- agentic.daily_workflow：把 watchlist、evidence、promotion 和 daily brief 连接成一个确定性的本地纵切，方便后续接入现有新闻采集器与 Dashboard。
- agentic.order_intent：把通过 paper promotion 的信号转换为 paper-only 订单意图，经过人工确认后交给内存 Paper Adapter；没有真实券商调用。
- agentic.order_intent_store 与 agentic.audit_read_model 提供订单意图持久化和 Dashboard/报告可复用的只读审计查询 seam。
- SignalService 现在依赖 Repository seam，可在没有 Web/API 运行时依赖的环境中单独验证；旧的 AgenticRepository 仍可直接注入。AgenticRepository 已提供同一 SQLite 连接上的 `publish_signal_atomically` / `transition_signal_atomically` seam，投影与 Ledger 事件在同一事务中提交或回滚；旧 Fake/兼容 Repository 仍保留回退路径。
- Outbox 增加 stale in-flight reclaim 和每次 claim 的唯一 token fencing；进程崩溃后的消息不会永久卡在锁定状态，旧 worker 不能确认新 worker 的租约；Webhook Adapter 返回结果会保留 event_id。
- AlertEngine 增加可选 Outbox seam；接入时会产生 market.alert.triggered DomainEvent，旧 WebSocket/条件单路径仍保持兼容。
- Audit 路由改为每请求创建只读 SQLite Adapter，避免模块级连接跨 FastAPI 工作线程复用；缺少数据库时使用空的内存 read model，不在 GET 期间创建 schema 文件。
- 行情回调不再假设运行在 asyncio 主线程；告警检查在回调线程执行，广播通过主事件循环的 thread-safe 调度进入 WebSocket；应用生命周期启动专用 alert outbox worker。
- Evidence snapshot 记录采集状态、源错误、原始/去重数量和截断元数据；新闻中的多股票关联使用独立关系表保存。新增 `collection_snapshot_id` 与 `evidence_snapshot_id` 区分可审计采集运行和可引用证据：失败/空采集仍保留运行记录，但不再返回可引用证据 ID；旧 Adapter 缺少 `link_symbol` 时走关系链接兼容路径。

## 仍未宣称完成的能力

- 没有宣称真实券商下单、实盘成交或稳定的外部通知已完成。
- Dashboard 已注册只读 /api/audit 路由，市场新闻已写入 EvidenceStore；审计未知 signal/evidence 返回 404；仍待浏览器验收页面展示和应用完整依赖环境。
- 尚未把所有旧的 Signal/Strategy Candidate 晋级逻辑替换成 PromotionPolicy；迁移期间必须保留只读兼容 Adapter，避免出现两套写模型。
- 没有接入真实通知凭证，也没有在测试中访问外网。
- Outbox 仍是至少一次投递语义；provider 可能在网络超时后已收到请求，因此 exactly-once 通知和跨表一致性事务尚未宣称完成。应用 worker 已接线，但真实外部 Webhook 未在本轮调用。SQLite Outbox 现在明确传入连接由调用方拥有：初始化与普通写入不隐式提交外部事务，claim 在检测到外部活动事务时拒绝嵌套；路径构造器支持无副作用只读模式。跨线程使用传入连接仍要求调用方创建 `check_same_thread=False` 连接，文件路径 Adapter 自行管理 worker 连接。

## 对抗性验收问题

1. 如果删掉 EvidenceStore，证据去重、快照复现和信号引用逻辑会散落到多个调用方，因此它通过 deletion test。
2. 如果删掉 PromotionPolicy，普通 Signal、Paper Candidate 和 OpenClaw 会重新出现各自判断晋级的分叉，因此门禁需要继续收敛。
3. Outbox 不把广播成功误认为事件已可靠送达；只有 Adapter 成功后才 ack，失败会重试或进入 dead-letter。
4. 模拟组件没有被包装成实盘能力；真实交易仍受人工确认和券商 Adapter 门禁约束。

## 下一阶段发布门禁

- 现有 alpha/news_collector 必须写入 EvidenceStore，报告和信号只能引用 snapshot id。
- SignalService 的发布和人工进入 paper_pending 已接入 Signal Ledger；生产 Repository 的发布/晋级投影与 Ledger 事件已在同一事务中写入，旧数据库中的信号会在第一次状态操作时被 Ledger seed，投影与历史状态不一致则拒绝写入。
- 现有 alert engine 必须通过 Outbox 发布，WebSocket 只保留为一个通知 Adapter。
- alert outbox 必须有运行中的消费者；停机重启后需通过 stale reclaim 和 token fencing 验收 pending/in-flight/dead 状态。
- 增加查询 seam 后，再进行 Dashboard 浏览器验收；先验收数据可追溯，再验收视觉展示。

## 本轮 2026-08-12 加固与验证记录

- P1 告警线程问题已修复：QuoteService 后台线程直接执行告警检查，WebSocket 广播通过注册的主事件循环 `call_soon_threadsafe` 投递。
- P1 告警消费者已接线：应用 lifespan 启动 `alert-webhook-worker`，按事件类型过滤 `market.alert.triggered`，支持 reclaim 和 retry/dead-letter。
- P1 Outbox lease fencing 已修复：每次 claim 生成唯一 `claim_token`，ack/fail 必须匹配 token；新增跨连接并发 claim 和旧 worker ack 拒绝测试。
- P1 Evidence 关联已修复：市场新闻保留全部关联股票到 `evidence_item_symbols`，snapshot 写入 collection status、源错误、原始/去重数量和截断信息。
- P1 审计只读已修复：已有数据库走 `mode=ro`，缺少数据库时走空内存 read model；未知 signal、孤立 provenance、未知 evidence snapshot 均不产生伪成功结果。
- 定向无仓库级依赖门禁：35 passed；Evidence/Outbox/Audit 门禁本轮 30 passed；信号 Ledger/服务/策略门禁 7 passed；`compileall` 和 `git diff --check` 通过。生产 Repository 的事务故障注入探针验证：发布失败后 projection=0、ledger=0；晋级失败后状态仍为 `new` 且历史只有 `new`。
- 初始系统解释器因缺少 `loguru`、`python-dotenv`、`SQLAlchemy`、`FastAPI` 等依赖无法收集测试；已在仓库忽略的 `.venv` 中补齐运行/测试依赖。恢复后新闻/路由/核心纵切定向测试通过，全量 pytest 通过。

## 2026-08-13 依赖恢复与全量回归

- `.venv/bin/python -m pytest -q`：`798 passed in 139.82s`。
- 新闻、审计与证据路由定向门禁：`17 passed`。
- Agentic/Outbox/Evidence/订单意图/告警/前端契约定向门禁：`101 passed in 14.67s`。
- Dashboard 启动/会话门禁：`9 passed in 35.39s`。
- `scripts/verify_context_pack.py`：`Context pack OK`。
- `git diff --check`、`.venv/bin/python -m compileall -q .`：通过。
- 安装的依赖和 `.venv/` 均被 `.gitignore` 忽略；未修改 requirements 或 lock 文件。

## 本轮对抗性审查新增结论

- P0 双写一致性已在生产 `AgenticRepository` seam 内收口：投影、Ledger event 在同一 SQLite 事务中提交或回滚；故障注入已验证无孤儿。仍未完成的是命令级 `operation_id` 幂等/重放语义，以及所有外部/旧写路径的迁移。
- P1 晋级仍可通过 `decision=None` 绕过 PromotionPolicy；这是历史兼容行为，当前未强制收紧，以免无迁移的 API 破坏既有调用。要超越对标系统，下一阶段应拆成明确的“策略门禁批准”和“人工确认命令”，两者都留下 operation id 与审计结果。
- P1 多进程 single-flight 尚未解决：新闻刷新锁只覆盖单进程；多 worker 仍可能重复采集并创建多个 snapshot。需要 DB lease/idempotency key 或外部 scheduler owner。
- P1 原始源记录仍未完整保存：当前 Evidence 主要保存标准化/展示结果；要宣称可复现研究，需额外保存每个源的 raw payload、请求窗口、源版本和解析器版本。
- P2 目前没有执行真实浏览器页面验收、真实外部 Webhook 联调、真实券商/实盘或生产部署；这些不属于本轮安全范围，因此不能把全量 pytest 解读为生产可用证明。
- Docker 首次构建暴露了部署依赖问题：`pyqlib>=0.9.0` 没有 Apple Silicon/aarch64 Linux wheel，且仓库实际运行的是轻量 `data/qlib` 兼容层。Dockerfile 已在部署镜像中显式排除该未使用的重量级依赖；本地源码 requirements 保持不变，避免改变现有 Python 开发环境契约。
