# Dashboard 前端全量重构

- 状态：Implemented and Verified
- 日期：2026-08-18
- 完成验证：2026-08-19
- 负责人：AI Quant Trading
- 相关规格：[Dashboard 重写与 Pi Agent 执行器迁移](2026-08-18-dashboard-rewrite-pi-agent.md)

## 背景

当前 Vue Dashboard 已覆盖决策、研究、验证、报告、通知、策略、风控、模拟盘与 AI Runtime，但信息架构仍是历史功能入口的集合：桌面侧栏展示十二个同权一级入口，决策中心首屏充满指标和 panel，真正的组合结论、资格与下一步操作位于长页面下方。

实测还发现以下结构性问题：

- 移动端实际渲染六个导航项，但 CSS 按五列布局，第六项主题按钮落到固定底栏外。
- Shell 的侧栏、移动导航、顶部栏和主题规则分散在全局 CSS 和 scoped CSS，存在 `244px/240px`、`60px/64px` 等冲突尺寸。
- 页面将 `pending`、`timeout`、`failed`、`partial`、`not_run`、`invalid` 等不同业务意义混在普通状态文本中。
- `ValidationView` 没有完整恢复 URL 上下文；`MainContent` 使用 `route.fullPath` 作为 key，query 变化可能造成整页重挂载。
- AI、确定性决策、验证、资格与通知的视觉层级不够清晰。
- 当前 Service Worker 对认证 API GET 缓存存在跨 workspace 风险。

视觉方向参考 DeepSeek Harness 的低装饰、高对比、大结构与有目的动态，但不复制其品牌、营销叙事、资产或页面布局。量化工作台需要服务于高频扫描、比较、审计和连续操作，而不是做长篇产品展示。

## 目标

1. 重写认证后 Vue Dashboard 的 Shell、导航、设计系统、核心页面和交互状态。
2. 将主路径收敛为“决策 → 研究 → 验证 → 报告 → 通知审计”。
3. 将确定性结论、AI 研究解释、验证结果与资格状态分开表达。
4. 让桌面、窄桌面、平板与移动端均可完成核心操作。
5. 以 URL 作为跨页上下文恢复来源，确保浏览器刷新、后退和深链接稳定。
6. 动效只服务状态理解、局部反馈与流程连续性，完整支持 `prefers-reduced-motion`。
7. 保留后端 API、legacy 字段、公开报告入口和真实交易禁用边界。

## 非目标

- 不重写 FastAPI、决策引擎、报告存储、风险规则或交易执行语义。
- 不将 AI 输出升级为确定性结论、资格、订单或通知依据。
- 不引入营销首页、全屏 WebGL、粒子、发光边框、渐变 Orb、持续脉冲或无意义 loading 编排。
- 不使用大规模卡片堆叠替代信息层级。
- 不为每个页面单独创造新的按钮、表格、抽屉或状态组件。
- 不删除公共 `/report/:token`、必要兼容字段或未经引用扫描确认的路由。

## 技术决策

### 保留

```text
Vue 3 / TypeScript / Vite / Pinia / Vue Router / lucide-vue-next
```

### 实施取舍

重构复用现有 CSS token、Vue 基础组件和浏览器原生 `inert`、Dialog/焦点管理能力，没有引入
Tailwind CSS、Reka UI、shadcn-vue 或 Motion for Vue。新增一套并行样式和组件系统不会改善当前
验收结果，反而会扩大迁移面；局部状态与空间过渡继续由明确属性的 CSS transition 和
`prefers-reduced-motion` 统一约束。

## 产品语言

### Dark Quant Harness

默认主题为近黑石墨量化操作台：

```text
canvas            #0a0b0d
surface           #111418
raised surface    #171b20
line              #272d34
primary text      #f3f5f7
muted text        #929aa4
operation accent  #68d5c1
positive          #5fd39b
negative          #f47777
warning           #e4b86a
info              #8db9ef
```

最终色值以可访问性与实际页面截图验证为准。

规则：

- 青绿色只表示主要操作、确认与研究入口，不代表 AI。
- 涨跌、风险、资格、数据质量各使用独立语义色。
- AI 使用中性辅助层，不与确定性结论争夺主色。
- 页面通过留白、分隔线、等宽数据、稳定栅格和高对比文本建立秩序。
- 圆角最大 `8px`，圆形/胶囊仅用于状态和少量清晰命令。
- 不使用大面积渐变和厚重阴影。

### 字体与层级

```text
标题：IBM Plex Sans / Noto Sans SC
运行数据：IBM Plex Mono / system monospace
正文：14–16px
面板标题：16–18px
页面标题：28–36px
```

禁止视口宽度驱动的字体缩放和负字距。紧凑面板使用紧凑标题，只有真正的页面主标题使用更大字号。

## 信息架构

### 一级工作区

一级导航代表用户正在处理的业务对象和阶段，而不是所有功能的平铺清单：

```text
决策 / 研究 / 验证 / 组合 / 报告
```

每个工作区在全局上下文栏下提供固定的模块导航：

```text
决策：今日决策 / 市场情报
研究：单股研究 / 条件筛选 / Alpha 与因子 / 公式与篮子 / AI 研究
验证：验证与回测 / 策略工作台
组合：持仓与风控 / 持仓优化 / 模拟盘 / 条件单
报告：报告审计 / 通知路由 / 告警规则
```

AI 保留顶部全局入口，同时作为研究工作区的明确模块；设置、Broker 安全和工作流地图属于系统工具，进入账户/系统菜单或 Command Palette。`/app/workflows` 只做完整索引，不能成为业务功能的唯一入口。

桌面和移动端共享这五个一级工作区；移动底栏固定五项，当前工作区的二级模块显示在页面标题下方，移动抽屉还提供完整分组导航。

### 全局上下文栏

所有核心页共享一个 Workspace Bar：

```text
当前工作流 / workspace / market / instrument or portfolio / data freshness /
run status / qualification / quick search / account actions
```

窄桌面隐藏次级字段但保留工作区和当前模块。移动端保留菜单、页面标题、核心上下文、AI 全局入口和当前工作区模块导航。

### 上下文协议

```ts
interface WorkspaceContext {
  workspaceId?: string
  market?: string
  symbol?: string
  portfolioId?: string
  strategyId?: string
  runId?: string
  reportId?: string
  tab?: string
}
```

优先级：

```text
route params/query > backend current context > Pinia > sessionStorage fallback
```

URL 是可恢复、可分享和可后退的来源。Pinia 不是权限来源；登出或账户切换必须清理 workspace 相关 research context、运行状态、报告缓存和 WebSocket 订阅。

## 页面规格

### 决策中心

首屏只回答四个问题：

```text
当前结论是什么？
结论是否有效？
有什么阻断或风险？
下一步允许做什么？
```

结构：

```text
DecisionHeader
DecisionOutcome
DecisionTrace
ActionQueue
CandidateQueue
DecisionContextRail
```

`DecisionOutcome` 是视觉主区域，显示确定性结论、数据/资格状态、关键阻断原因和一个下一步操作。AI 只在可折叠的“研究解释”层展示。

`DecisionTrace` 节点固定为：

```text
输入快照 → 数据质量 → 策略版本 → 验证 → 资格 → 冻结结论 → 报告 → 投递
```

每个节点显示时间、版本、hash、状态和可查看证据。候选池只作为进入研究的入口，不能渲染成成立的决策。

### 单股研究

结构：

```text
InstrumentHeader
PriceAndMarketContext
ResearchTabs
ResearchCanvas
ResearchContextRail
```

ResearchTabs：概览、信号、因子、新闻、风险、证据。优先展示行情更新时间、数据来源、质量和风险；缺失 provider、过期数据、部分字段或标的不可用必须显式显示，不能用 `0`、空白图或成功状态替代。

从研究进入验证必须携带 `market`、`symbol`、`strategyId`。返回决策必须保留组合/标的上下文。

### 验证与回测

结构：

```text
ValidationHeader
InputSnapshot
ValidationWorkflow
ValidationResult
RunTimeline
ValidationActions
```

高频参数放首屏：策略、标的、时间范围、初始资金、周期。基准、佣金、税、滑点、样本外比例、Monte Carlo 和风控收进高级设置。

流程：

```text
准备参数 → 校验输入 → 回测 → 样本外 → Monte Carlo → 成本 → 资格 → 报告
```

运行状态必须显示阶段、已耗时、运行 ID 和日志摘要。`timeout` 不能显示为成功或失败；`partial` 必须列出完整和缺失部分。验证尚未通过时不能启用报告或投递操作。

### 报告与通知审计

报告中心使用可扫描表格而不是重复文章卡片：

```text
报告 / 对象 / 生成时间 / 输入 hash / 数据 / 验证 / AI / 决策数 / 投递 / 分享 / 操作
```

移动端使用可展开分层列表。报告详情必须包含结论、证据、冻结输入、验证、AI 解释、投递审计、导出、分享与撤销状态。

通知页展示完整链路：

```text
规则 → 资格条件 → 触发 → 待投递事件 → 投递尝试 → 渠道响应 → 最终状态
```

“已生成报告”不能被显示成“已通知”。

### AI 工作台

AI 工作台展示 Pi Agent 的 task、运行拓扑、冻结 context、结构化 artifact、provider readiness 和会话。始终标记：

```text
human_review_only
authoritative=false
decision_effect=none
```

AI 不进入决策主操作区，不获得真实交易、模拟盘、资格或通知控制权。

## 状态模型

```ts
type AsyncStatus =
  | 'idle'
  | 'loading'
  | 'running'
  | 'completed'
  | 'partial'
  | 'rejected'
  | 'failed'
  | 'timeout'
  | 'cancelled'

type DataStatus =
  | 'unknown'
  | 'fresh'
  | 'stale'
  | 'invalid'
  | 'missing'
  | 'unavailable'

type QualificationStatus =
  | 'not_checked'
  | 'checking'
  | 'qualified'
  | 'blocked'
  | 'expired'
  | 'unknown'
```

状态不可混用。`validation`、`qualification` 和 `data quality` 由不同组件展示。旧 API 字段在 adapter 层归一化，新组件只消费规范内部类型。

## 动效规格

### 决策冻结

触发：验证完成且资格检查得出明确结果。

行为：当前验证节点完成，后续资格/报告节点更新，结果区域短暂稳定，版本和 hash 出现，合法下一步操作启用。

时长：`220–300ms`；只播放一次；无持续 glow、数字滚动或“AI 思考”动画。

### 常规反馈

```text
buttons and fields: 100–140ms
tabs and local view changes: 140–180ms
drawers and command palette: 200–260ms
list filtering: layout transition only
high-frequency quote: changed cell only
```

### Reduced Motion

在 `prefers-reduced-motion: reduce` 下，禁用位移、缩放、循环、shimmer 和编排动画，保留文字、颜色、边框、aria-live 和状态图标变化。

## 响应式与可访问性

验证视口：

```text
1440×900
1180×720
1024×768
768×1024
390×844
320×740
```

要求：

- 移动底栏永远单行、恰好五项，包含 safe-area inset。
- 触控目标至少 `44×44px`。
- 无横向滚动、文字遮挡或固定栏遮挡内容。
- Drawer/Dialog 打开后焦点被隔离，Esc 可关闭，关闭后焦点返回触发控件。
- 所有图标按钮有可读 label 或 tooltip。
- 核心操作可用键盘完成。
- 深色和浅色主题都达到可读对比度。

## 路由策略

保留：

```text
/auth
/app/decision
/app/research
/app/research/:market/:symbol
/app/validation
/app/reports
/app/reports/:id
/app/notifications
/report/:token
```

继续承载但移入更多：

```text
/app/intelligence
/app/research/screener
/app/research/alpha
/app/strategy
/app/portfolio-risk
/app/paper
/app/ai
/app/settings
/app/workflows
```

删除候选仅在引用扫描后处理：

```text
/app/more/*
/app/screener
/app/alpha
/app/strategies
/app/agent-ops
/app/ai-runtime
/app/broker-live
```

扫描范围：`dashboard/`、`tests/`、`docs/`、`scripts/`、后端生成链接、PWA 缓存规则和公开入口。外部使用无法确认的路径保留一次性兼容重定向，不能维护多层 alias。

## Service Worker 与 WebSocket

Service Worker：

- 只缓存静态资源和明确公开的内容。
- 不缓存认证 `/api/` GET 响应。
- 按版本清理旧缓存。
- 账户切换清理用户相关缓存。
- 离线页面显示 stale/unknown，不能显示 fresh。

WebSocket：

- 先冻结 `/ws/quotes` 协议、订阅、退订、批量更新、重连与取消策略。
- 组件卸载、workspace 切换和登出时关闭连接并清理订阅。
- 高频更新只写入变化字段，不造成页面整体重绘。

## 实施顺序

### Phase 0：基线

- 保存当前桌面、窄桌面、移动、浅深主题截图与录屏。
- 清点路由、API、legacy 字段、Service Worker、WebSocket、测试和外部入口。
- 为已知移动导航、query 重挂载和状态问题建立回归测试。

### Phase 1：设计系统

- 复用并收敛 `variables.css`、`base.css`、`shell.css` 和现有 Vue 基础组件，不引入第二套样式或组件运行时。
- 统一 token、theme、motion、Button、Badge、Input、Tabs、Dialog/Drawer、Table 和异步状态表达。
- 在业务迁移中同步完成键盘、触控、主题和 reduced-motion 验证。

### Phase 2：App Shell

- 重写 AppShell、Desktop Rail、Workspace Bar、Workspace Module Navigation、Mobile Navigation、Command Palette、AI 全局入口和 Account Menu。
- 移除旧侧栏、移动底栏和重复 scoped Shell 样式。
- 移动端固定五个一级工作区；不再用“更多”承载业务功能。

### Phase 3：上下文与状态

- 收敛 URL context、Pinia 单写入者、登出清理和页面局部更新。
- 移除 `route.fullPath` 整页 key。
- 引入统一异步、数据质量和资格状态模型。
- 收紧 Service Worker 与 WebSocket 生命周期。

### Phase 4：核心链路

- 重写决策中心。
- 重写单股研究。
- 重写验证与回测。
- 重写报告列表、详情和通知审计。
- 接入决策冻结和报告生成反馈。

### Phase 5：辅助 Workbench

- 迁移情报、筛选、因子、策略、组合风控、模拟盘、设置和 AI 工作台。
- 统一表格、筛选、详情抽屉、空状态、错误与运行状态。
- 清理不再被使用的 legacy view、CSS 与路由。

### Phase 6：集成验收

- 构建、组件测试、Vue 契约、Python API 契约、布局测试、E2E、Docker 和浏览器回归。
- 多 workspace、登出、离线、网络超时、键盘和 reduced-motion 验收。

## 验收标准

### 视觉和布局

- `1440×900` 首屏可以看到当前结论、资格、阻断原因和下一步。
- `1180×720` 侧栏、主画布和上下文不重叠。
- `390×844` 无横向滚动，固定底栏只显示一行五项。
- 没有全屏渐变、发光边框、粒子、Orb、持续动画或嵌套卡片。
- AI 解释不会压过确定性结论。

### 功能和状态

- 决策 → 研究 → 验证 → 报告 → 通知保持对象与运行上下文。
- `loading/running/completed/partial/rejected/failed/timeout/cancelled` 可准确区分。
- `data quality`、`validation` 和 `qualification` 不混用。
- 空数据、缺失 provider、过期数据和失败不会显示为 `0` 或成功。
- 报告 token、导出、认证原始数据、分享/撤销/过期行为不退化。
- AI 仍为研究 artifact，不能改变决策、资格、通知、模拟盘或真实交易。

### 工程

```bash
npm run ui:build
npm run ui:test
.venv/bin/python -m pytest tests/test_vue_*_contract.py -q
.venv/bin/python -m pytest tests/test_vue_layout.py tests/test_vue_visual_spec.py -q
scripts/e2e-local.sh smoke
scripts/e2e-local.sh data-health
```

Docker 浏览器验收在 `http://127.0.0.1:8001` 上执行。任何真实数据同步、外部 LLM、外部通知或交易脚本必须单独确认后才可运行。

## 完成证据

2026-08-19 的前端发布门禁：

- `npm run ui:build` 通过，生产 CSS `88.80 kB`、入口 JS `180.68 kB`。
- `npm run ui:test`：`46 passed`；Vue/研究契约：`107 passed, 1 skipped`。
- 全量 pytest：`979 passed, 1 skipped`；正式 Playwright Vue E2E：`4 passed`。
- 静态数据渲染审计 `high=0`（`104 medium / 3 low`）；Impeccable 机械检测无发现。
- Docker Dashboard 在 `http://127.0.0.1:8001` 健康；认证态桌面/移动 25 条路由共
  50 次检查全部通过，无横向溢出、控制台错误或容器重启，兼容入口均落到 canonical 页面。
- `1440×900`、`1180×720`、`1024×768`、`768×1024`、`390×844`、`320×740` 已覆盖；
  浅/深主题、reduced-motion、移动 Drawer、Command Palette、焦点恢复和五项底栏已验证。
- 最终认证态截图位于 `.impeccable/review/auth-final/`。完整 Pi Agent 与 trading profiles
  发布仍由相关组合规格跟踪，不属于此前端规格的完成声明。

## 风险与回滚

- 新旧 CSS 共存时间越长，视觉漂移风险越高；每迁移一个区域即删除对应旧 Shell 样式，不维护长期双系统。
- 旧路由删除可能破坏书签和测试；必须完成引用扫描和兼容评估后再删。
- API 字段改动通过 adapter 保持 `qlib_*` 与报告契约兼容。
- 动画仅位于局部组件，必要时可通过 reduced-motion 和 motion token 一次性关闭。
- 每个阶段保持可构建、可测试、可回滚；不等待全部页面完成后才第一次集成。
