# Dashboard 重写与 Pi Agent 执行器迁移

- 状态：Frontend Implemented; Pi Agent Release In Progress
- 日期：2026-08-18
- 前端完成验证：2026-08-19
- 负责人：AI Quant Trading
- 相关链接：[Pi](https://github.com/earendil-works/pi)、[前端全量重构](2026-08-18-dashboard-frontend-rewrite.md)、[决策平台重构](2026-08-14-decision-platform-refactor.md)

## 背景

现有 Dashboard 的信息架构将十二个一级入口、多个同权卡片和异步状态混在同一视觉层级中。核心流程“决策 → 研究 → 验证 → 报告 → 通知审计”被拆散，移动端实际渲染六项导航但样式只提供五列。

系统已经拥有独立 AI 任务队列、冻结输入、SSE 事件、workspace 隔离和结构化报告，但执行器是通用的 `ai-worker` 与 provider router。产品目标调整为由 Pi Agent 取代该独立 AI Worker 的智能执行职责，并与 Dashboard 全量重写同步交付。

## 目标

1. 重建 Vue Dashboard 的 Shell、导航、设计系统和核心决策链路。
2. 将 Pi Agent 作为 AI 任务的唯一生产执行器，而不是再增加一个普通 provider。
3. 保留 `ai_runtime` 中已经验证的任务持久化、冻结快照、workspace 隔离、SSE、审计和报告结构。
4. 让 Pi Agent 只能生成研究 artifact，不能修改确定性动作、资格、通知、模拟盘或真实交易。
5. 清理确认无用的旧 UI、重复样式和历史路由；公共报告入口与必要兼容字段继续保留。

## 非目标

- 不将 Pi Agent 直接嵌入 FastAPI Web 进程。
- 不向 Pi Agent 开放 Shell、文件编辑、网络、交易、通知或 broker 工具。
- 不允许 AI 输出成为订单、确定性决策、资格或外部投递的依据。
- 不在本轮改变决策 Worker、通知 Worker、数据库恢复或真实交易边界。
- 不复制 DeepSeek Harness 的品牌、文案或页面实现；只借鉴其低装饰、高层级和结构化动态语言。

## 架构决策

### Pi Agent 替代 AI Worker

```text
Dashboard API
  -> ai_runtime task queue / frozen context / SSE / audit
  -> PiAgentWorker lease owner
  -> Pi CLI one-shot agent process
  -> schema validation
  -> non-authoritative AI report artifact
```

`PiAgentWorker` 是唯一消费 AI 队列的生产进程。它复用当前 SQLite lease/fence、worker heartbeat、任务取消、失败持久化、workspace 隔离和报告仓储；旧 AI Worker 兼容层已删除。

Pi 在第一期通过 CLI 单任务运行：

```text
pi --print --no-session --no-tools --no-extensions --no-skills \
   --no-prompt-templates --no-context-files
```

每次运行只接收已经冻结且已 hash 的 JSON 上下文。默认不发现项目文件、不加载项目扩展、不保存 Pi session，也没有内建或自定义工具。模型认证仍由 Pi 的 provider 配置或环境变量处理，不写入项目数据库。

后续只有在明确需要受控数据查询时，才新增独立 Node sidecar 和 allowlist custom tools；不能把 Pi 的默认 coding tools 暴露给量化业务任务。

### AI 安全边界

- AI report 固定为 `authoritative=false` 与 `decision_effect=none`。
- `action`、`order`、`buy`、`sell`、`trade`、`execute` 等字段继续在 schema 校验阶段拒绝。
- Pi 进程不得获得数据目录写权限、broker 凭据、通知 webhook 或生产数据库写能力以外的 task artifact 通道。
- 真实交易仍默认禁用；Pi 不能调用模拟盘或实盘 API。
- 自动投递资格仅来自冻结数据、版本、验证、provider health 和资格规则，不能从 Pi 输出推导。

## Dashboard 目标形态

### 导航

桌面 Rail 与移动端使用同一五个一级工作区：

```text
决策 / 研究 / 验证 / 组合 / 报告
```

市场情报归入决策；筛选、因子、公式和 AI 归入研究；策略归入验证；风控、优化、模拟盘和条件单归入组合；通知和告警归入报告。每个工作区在页面标题下显示固定模块导航。AI 另外保留顶部全局入口；设置、Broker 安全和工作流地图进入系统菜单。移动底栏固定五项，不再以“更多”承载业务功能。

### 全局上下文

所有核心页共享：

```text
workspace / market / instrument or portfolio / data freshness / run status / qualification
```

URL 是 `market`、`symbol`、`portfolioId`、`runId`、`reportId` 的主恢复来源；Pinia 只作临时 fallback，登出或账户切换时必须清理。

### 核心页面

- 决策：结果、阻断原因、下一步、决策轨迹、待处理队列。
- 研究：标的上下文、行情和数据质量、证据、信号、风险、AI 解释。
- 验证：输入快照、回测、样本外、Monte Carlo、成本、资格和运行轨迹。
- 报告：证据索引、冻结输入、验证状态、hash、分享与投递审计。
- AI：Pi Agent 运行状态、任务、报告和研究会话；不显示为决策执行面板。

## 动效原则

- 核心动效是验证完成后的“决策冻结”：输入 → 验证 → 资格 → 报告的状态线在 220–300ms 内稳定更新。
- 局部 Drawer、Tab、筛选和报告新增使用短促过渡；不做全屏编排、持续脉冲、粒子、Orb 或发光边框。
- 高频行情只更新发生变化的字段。
- `prefers-reduced-motion` 下关闭位移、缩放、循环和 shimmer，保留状态文字与颜色。

## 实施阶段

### Phase 0：基线与契约冻结

- [x] 审查桌面、移动、决策、研究、验证、报告和 AI 工作台。
- [x] 记录导航、路由、状态、Service Worker、WebSocket 和 AI Runtime 风险。
- [x] 确认 Pi SDK、CLI 与 RPC 的官方集成边界。
- [x] 补充登录态完整流程截图作为视觉回归基线；截图位于 `.impeccable/review/auth-final/`。

### Phase 1：Pi Agent Worker 迁移

- [x] 新增 `pi_agent` provider protocol，强制无工具、无 session 的 Pi CLI 调用。
- [x] 将生产 AI 队列消费者改为 `PiAgentWorker`，保留 fence/lease 语义。
- [x] 新增 `scripts/run_pi_agent_worker.py`，旧兼容入口已移除。
- [x] Docker Compose 仅保留 `pi-agent` AI worker 服务，使用含 Pi CLI 的专用 image target。
- [x] API 和 UI 明确显示 Pi Agent worker 状态。
- [x] 增加 provider、worker、配置与安全 flag 定向测试。

实现验证：Pi provider/worker/runtime 定向测试 `24 passed`，AI API 契约 `6 passed`，Vue build、Compose config、Python 编译和 context pack verifier 通过。`docker build --target pi-agent` 尚未完成，因为 Docker Hub 拉取 `node:22-slim` 的认证请求超时；Dockerfile 与 Compose 语法已通过。

### Phase 2：设计系统与 App Shell

- [x] 复用现有 Vue/CSS token 和基础组件；不引入 Tailwind、Reka UI/shadcn-vue 或 Motion for Vue，避免并行设计系统。
- [x] 建立 graphite/teal 语义 token、浅深主题、44px 触控目标和 reduced-motion token。
- [x] 重写 App Shell、Desktop Rail、Workspace Bar、工作区模块导航、AI 全局入口、Drawer、Command Palette 和移动五项导航。
- [x] 删除旧 Shell 的重复 `244px/240px` 侧栏和 `60px/64px` 移动导航规则。

### Phase 3：上下文与状态模型

- [x] 统一 URL context 和 Pinia 单写入者。
- [x] 定义并区分 `idle/loading/running/completed/partial/rejected/failed/timeout/cancelled`。
- [x] 分离 data quality、validation 和 qualification 状态。
- [x] 修复 query 变化导致的整页重挂载、登出上下文残留和认证 API 缓存。

### Phase 4：核心工作流页面

- [x] 重写决策、研究、验证、报告和通知审计。
- [x] 将 Pi Agent artifact 显示为“人工复核研究”，与确定性结论分离。
- [x] 增加决策轨迹、报告生成和局部数据刷新反馈。

### Phase 5：辅助工作台与清理

- [x] 迁移筛选、因子、策略、组合风控、模拟盘、设置和 AI 配置。
- [x] 删除无引用的重复历史视图；保留 `/report/:token` 和验证过的兼容重定向。
- [x] 收紧 Service Worker 认证缓存边界、页面生命周期和离线状态表达。

### Phase 6：验收与发布

- [x] `npm run ui:build`、Vue 契约、全量 pytest、布局和 Vue E2E 通过。
- [x] 1440×900、1180×720、390×844、浅/深色、键盘和 reduced-motion 验收。
- [ ] Pi Agent 无工具运行、取消、超时、worker lease、多 workspace 和 provider 失败的发布环境验收。
- [ ] Docker `ai` + `trading` profile 通过；不触发真实交易或外部投递。

前端完成证据（2026-08-19）：UI `46 passed`，Vue/研究契约 `107 passed, 1 skipped`，
全量 pytest `979 passed, 1 skipped`，Playwright Vue E2E `4 passed`。Docker Dashboard
认证态桌面/移动 25 条路由共 50 次检查全部通过，无横向溢出、控制台错误或容器重启；
静态数据渲染审计 `high=0`，Impeccable 检测无发现。完整 `ai` 与 `trading` profile
仍是本规格保持 In Progress 的原因。

## 配置

新配置：

```text
PI_AGENT_WORKER_ENABLED=true
PI_AGENT_WORKER_LEASE_TTL_SECONDS=30
PI_AGENT_WORKER_POLL_INTERVAL_SECONDS=2
PI_AGENT_WORKER_BATCH_SIZE=4
PI_AGENT_COMMAND=pi
PI_AGENT_MODEL=<optional provider/model>
PI_AGENT_TIMEOUT_SECONDS=90
```

`AI_INLINE_EXECUTION` 仅用于明确的开发环境测试，生产环境始终由 Pi Agent worker 消费队列。

## 验收标准

1. `pi-agent` 是生产 compose 中唯一的 AI 任务消费者，旧 `ai-worker` 服务不再启动。
2. Pi 子进程命令包含 `--no-tools`、`--no-session`、`--no-extensions`、`--no-skills`、`--no-prompt-templates` 和 `--no-context-files`。
3. Pi 不可用、超时或产生无效 JSON 时，任务降级并记录脱敏诊断，不伪造成功。
4. Pi output 无法通过 schema 创建可执行动作或自动投递资格。
5. 现有 workspace、lease/fence、task cancellation、SSE、report hash 与审计测试继续通过。
6. 新 Shell 在移动端恰好五项导航，且不存在横向滚动或底栏第二行。
7. AI 输出始终明确标识为研究 artifact 与人工复核内容。

## 发布与回滚

发布前：构建 `pi-agent` target，使用开发 workspace 和非生产 provider 跑一个冻结 fixture。生产发布保持 `DECISION_EXTERNAL_DELIVERY_ENABLED=false`，不运行真实交易。

回滚时：停止 `pi-agent` 服务，设置 `PI_AGENT_WORKER_ENABLED=false`。任务留在队列中，不自动改写为成功或失败。
