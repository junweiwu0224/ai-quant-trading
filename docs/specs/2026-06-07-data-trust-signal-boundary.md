# Data Trust and Signal Boundary Spec

状态：Accepted
负责人：Codex
创建日期：2026-06-07
最后更新：2026-06-07
相关链接：`docs/decisions/0001-signal-engine-v2.md`、`data/signals/`、`dashboard/routers/datahub.py`、`dashboard/routers/signals.py`

## 1. 背景和问题

- 当前状态：系统已经接受 Signal Engine v2 作为运行时 AI 信号边界，但 API、前端、测试和用户文案中仍存在大量 legacy `qlib_*` 命名。
- 用户/业务问题：用户需要全量覆盖、可解释、可验证的数据机会发现；如果市场信号、机会池、情报页或估值页把未验证的本地动量缓存包装成 Qlib 预测，会误导决策。
- 为什么现在要做：近期问题集中在全量覆盖、市场情绪数量、新闻价值、机会池超时、qlib 失效和 AI 预测可信度。继续零散修补会让口径更乱。
- 证据来源：`docs/decisions/0001-signal-engine-v2.md` 已明确“Signal Engine v2 replaces Qlib as runtime signal boundary”；`dashboard/routers/datahub.py` 仍在健康接口和 summary 中保留 qlib alias。

## 2. 目标

- 目标 1：所有新增运行时数据可信度展示优先使用 `signal` 语义，legacy `qlib` 仅作为兼容 alias。
- 目标 2：用户能在 UI/API 中看到覆盖数量、缓存新鲜度、验证样本、降权原因和数据来源，而不是只看到“在线/离线”。
- 目标 3：机会池、情报页、估值页和 OpenClaw 入口不得把未验证 AI 信号当作强预测；未验证或样本不足时必须降权并展示风险标签。
- 目标 4：全量市场类功能必须说明统计 universe、有效样本、缺失样本和更新时间。

## 3. 非目标

- 本阶段不接入新的重量级框架，不迁移到完整 pyqlib，不引入 QuantConnect LEAN 作为运行时依赖。
- 本阶段不执行真实全量数据同步、不清库、不做数据库迁移、不修改生产配置。
- 本阶段不删除 legacy `/api/qlib/*` 或 `qlib_*` 字段；只收紧新增语义并保持兼容。
- 本阶段不接入实盘券商、不下单、不改变交易权限。

## 4. 用户和场景

- 主要用户：个人量化研究者，通过 Dashboard 判断市场状态、研究机会池、查看 AI 预测池和估值。
- 次要用户：后续 Codex/agentic worker，需要可靠知道哪些 API 是可信主路径，哪些只是 legacy alias。
- 核心场景：打开情报页能判断市场信号是否来自全市场有效样本；打开机会池能知道 AI 信号是否覆盖、是否已验证、是否已降权。
- 失败/边界场景：预测缓存缺失、缓存过期、样本不足、外部新闻/资金流失败、行情服务停止、stock_daily 不是全量。

## 5. 需求

### 功能需求

- FR-1：`/api/datahub/health` 必须同时返回 `signal` 与 legacy `qlib`，且 `signal` 来自 `_load_signal_health()`，不得直接复用 `_load_qlib_health()`。
- FR-2：`/api/datahub/decision-matrix` summary 必须保留 `signal_*` 主字段；`qlib_*` 只作为兼容字段。
- FR-3：信号验证状态必须包含 `status`、`confidence`、`sample_days`、`metrics` 和用户可理解的降权说明。
- FR-4：机会池评分对未验证 AI 信号必须降权；无 AI 覆盖时必须显示 `AI未覆盖`，有覆盖但未验证时显示 `AI未验证`。
- FR-5：市场情报页展示的市场信号、新闻、热力图、AI 预测池必须显示数据来源、更新时间、覆盖口径和异常/降级状态。
- FR-6：前端文案应逐步从“Qlib 预测”迁移为“AI 信号”；必须保留能解释 legacy 来源的提示。
- FR-7：数据健康检查脚本必须覆盖用户最常看的数据区域：datahub health、decision matrix、market breadth、news、heatmap、signals health/top。

### 非功能需求

- NFR-1 性能：机会池快速模式应避免慢外部估值源；前端下拉和表格不得一次渲染全市场所有股票。
- NFR-2 安全/隐私：不得读取或输出密钥；不得执行生产部署、真实交易、真实数据破坏性操作。
- NFR-3 可用性/可访问性：降级状态必须是显式文本，不只靠颜色；移动端不得出现水平溢出。
- NFR-4 兼容性：legacy `/api/qlib/*`、`qlib_*` 字段和既有策略 id 保留到后续迁移阶段。
- NFR-5 可观测性：新增或调整的数据路径必须有测试或 health/audit 证据证明口径。

## 6. 验收标准

- AC-1：DataHub health 区分 signal 与 qlib。
  - Given：测试替换 `_load_signal_health()` 与 `_load_qlib_health()` 返回不同 provider/status。
  - When：调用 `/api/datahub/health`。
  - Then：响应中的 `signal.provider` 等于 Signal Engine provider，`qlib.status` 等于 legacy qlib 状态，二者不被混用。
- AC-2：机会池未验证信号被降权。
  - Given：候选股票存在 `signal_rank` 但 `signal_confidence=unverified`。
  - When：计算 decision score。
  - Then：原因包含 AI 候选，风险包含 `AI未验证`，不包含 `AI未覆盖`。
- AC-3：机会池无信号覆盖时明确提示。
  - Given：候选股票没有 signal/qlib rank。
  - When：计算 decision score。
  - Then：风险包含 `AI未覆盖`，next action 包含等待 AI 覆盖。
- AC-4：信号 API 暴露验证证据。
  - Given：本地预测缓存和 stock_daily 有重叠数据。
  - When：调用 `/api/signals/health` 或 `/api/signals/validation`。
  - Then：响应包含 validation confidence、sample_days、1d 指标和 provider。
- AC-5：数据展示审计覆盖关键数据路径。
  - Given：运行 dashboard data health audit。
  - When：审计 SAFE_GET_PATHS。
  - Then：包含 datahub health、decision matrix、market breadth/news/heatmap、signals health/top，并拒绝 `undefined`、`NaN`、`Infinity` 等坏展示值。
- AC-6：前端真实浏览器 smoke。
  - Given：Dashboard 在 `127.0.0.1:8001` 运行。
  - When：打开 intelligence、overview、research 关键页面。
  - Then：无空白页、无控制台错误、无明显文字重叠或水平溢出，数据卡片展示来源/更新时间/降级说明。

## 7. 当前系统影响

- 相关模块：`data/signals/`、`dashboard/routers/datahub.py`、`dashboard/routers/signals.py`、`dashboard/routers/qlib.py`、`dashboard/static/intelligence-*.js`、`dashboard/static/research-datahub.js`、`scripts/dashboard_data_health.py`。
- API/接口：新增语义优先走 `/api/signals/*` 和 `/api/datahub/*` 的 `signal_*` 字段；`/api/qlib/*` 保留兼容。
- 数据模型/存储：本阶段不改表结构；继续读取 `stock_daily`、`stock_info` 和 legacy prediction cache。
- 前端/UX：优先修复误导性文案、覆盖状态、降级状态和慢下拉；不做大视觉重写。
- 后台任务/队列：不新增后台同步任务；真实全量同步需要单独确认。
- 配置/部署：不改生产配置，不启用新外部服务。
- 文档/支持：更新规格、计划、必要时补充 ADR/Playbook。

## 8. 技术约束和原则

- 必须遵守：`docs/decisions/0001-signal-engine-v2.md`，Signal Engine 是运行时 AI 信号主边界。
- 推荐方向：先补测试和 health 证据，再做 UI 文案和性能优化。
- 禁止方向：把 local_momentum 继续包装成“完整 Qlib”；无验证样本时显示强预测结论。
- 需要沿用的现有模式：FastAPI router、pytest、前端契约测试、`scripts/e2e-local.sh smoke`、DataStorage helper。

## 9. 风险

- 安全/权限：health 和 audit 只读；不得引入凭证输出。
- 数据一致性：legacy prediction cache 与 Signal Engine 语义并存，需保持 alias 兼容。
- 迁移/回滚：每批改动应小步提交；legacy qlib API 不删除即可回滚 UI 文案。
- 性能/容量：全量股票下拉和机会池外部估值源是已知慢点；需限制默认渲染范围。
- 兼容性：旧测试或策略仍可能依赖 `qlib_*`；迁移时保留 alias。
- 依赖/外部服务：新闻、资金流、东方财富等外部源可能失败；UI 必须显示降级而不是假装 0。

## 10. 验证计划

- 单元测试：`tests/test_signal_engine.py`、`tests/test_signal_api.py`、`tests/test_dashboard.py` 中的 DataHub/Signal 相关测试。
- 集成/API 测试：`.venv/bin/python scripts/dashboard_data_health.py`，以及 `/api/datahub/health`、`/api/signals/health`、`/api/signals/top`。
- E2E/用户流程：`scripts/e2e-local.sh smoke` 覆盖 overview/intelligence/research 核心路径。
- 前端视觉验证：Browser/Playwright 检查桌面和移动端无空白、无溢出、无控制台错误。
- 性能/负载：机会池快速模式和下拉搜索必须避免全量 DOM 渲染。
- 安全/权限：只读接口和测试账户 override，不读取 `.env` 秘密。
- 手动 smoke test：浏览器打开 `http://127.0.0.1:8001/#intelligence`、`#overview`、`#research`。

## 11. 发布、迁移和回滚

- 发布策略：按小批次提交，先 health/API，再前端文案，再性能优化。
- 数据迁移：本阶段无数据库迁移。
- Feature flag：不新增；使用现有 `signal` 主字段与 `qlib` alias。
- 监控指标：API health 中的 provider/status/cache age/sample_days/coverage。
- 回滚方案：回滚对应提交即可；legacy qlib 字段和 API 保持可用。

## 12. 开放问题

- Q1：后续是否彻底移除 qlib 命名，还是长期保留 legacy alias？本阶段默认长期兼容、逐步淡化。
- Q2：是否引入 QuantConnect LEAN 作为离线回测/验证 provider？本阶段不引入，待 Signal Engine provider 边界稳定后另立规格。

## 13. 决策记录

- 已决定：Signal Engine v2 是运行时 AI 信号边界，legacy Qlib 只作为兼容 adapter。
- 待 ADR：如后续引入 LEAN、PostgreSQL/ClickHouse、任务队列或新数据供应商，需要单独 ADR。
- 被拒绝方案：本阶段拒绝“重写整个系统”和“直接接入重量级新框架”作为第一步，因为当前最大风险是数据可信口径不清，不是缺少框架。
