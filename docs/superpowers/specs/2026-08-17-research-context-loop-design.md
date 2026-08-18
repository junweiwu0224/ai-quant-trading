# 研究对象驱动的决策到模拟盘闭环设计

## 目标

将 Dashboard 从“页面和路由集合”调整为围绕当前研究对象工作的连续流程：

```text
决策中心选择股票 → 单股研究 → 回测验证 → 模拟盘预览
```

页面之间继承市场、股票、策略、回测参数、研究快照和风险状态。只展示真实后端数据；数据缺失、过期、失败和资格阻断必须给出原因与下一步，不使用固定 mock 或永久占位。

## 架构边界

### 研究上下文

新增 `useResearchContextStore`，只保存跨页面上下文，不承载页面私有数据：

- `market`, `symbol`, `name`
- `strategy`
- `backtestRequest`, `backtestResult`
- `researchSnapshot`
- `riskStatus`, `eligibility`
- `lastUpdatedAt`

路由是可恢复来源，Pinia 是跨页面共享状态。刷新研究页时从 `/:market/:symbol` 恢复；直接进入验证页或模拟盘且没有上下文时显示引导，不写死股票代码。

### 研究页

复用现有后端接口：

- `/api/stock/kline/:symbol`
- `/api/stock/multi-timeframe/:symbol`
- `/api/stock/news/:symbol`
- `/api/llm/reports/:symbol`
- `/api/datahub/health`

K 线和技术指标并行加载。证据来源分开处理，单一来源失败不阻断其它来源。数据质量显示当前市场/标的的能力和时间，不能用全局健康替代标的状态。

### 验证页

复用现有回测和 Decision Worker 接口：

- `/api/backtest/run`
- `/api/backtest/out-of-sample`
- `/api/backtest/monte-carlo`
- `/api/decisions/portfolios/:id/validate`

参数默认来自研究上下文；无上下文时显示“先选择研究对象”的引导。回测结果写回上下文，只有存在真实结果且风险/资格允许时才可进入模拟盘预览。

### 模拟盘

复用真实 `/api/paper/*` 和 Paper Engine，移除前端 mock 数据与随机成交。订单路径为：

```text
UI → Paper API → Paper Engine → QuoteService / Risk Policy → 撮合结果
```

订单提交前显示标的、方向、数量、价格来源、数据时间、风险状态和执行环境；成功或失败结果回写账户、持仓和交易记录。实盘入口继续硬禁用。

### 系统运行语义

- `QuoteService → Paper Engine` 是实时行情输入；
- `Risk Policy` 横向作用于 `BacktestEngine`、`PaperEngine` 和条件单执行；
- `Decision Worker` 独立负责决策快照、不可变报告、Outbox、lease 和投递，不放在回测主链路上；
- SQLite 按 market data、agentic、evidence、decisions、events、worker leases、paper trading 等存储边界处理，不假设单一数据库所有权。

## 交互设计

### 决策中心

显示当前研究对象、机会池和自选池。候选统一提供“研究”和“加入自选”。没有当前对象时给出“从自选池选择、查看机会池、搜索股票”三个入口；有对象时显示继续研究、运行回测和加入自选。

### 单股研究

按“事实 → 分析材料 → 研究结论”组织。显示股票事实、K 线、技术指标、来源和数据时间，再显示新闻/研报等证据，最后显示真实决策结果和风险。没有真实结论时显示无法判断的原因，不显示固定置信度。页面底部提供由状态决定的下一步操作。

### 验证和模拟盘

验证页保留研究对象、策略、日期、成本和风控上下文，并明确参数来源。模拟盘显示回测来源、风险限制和 Paper Engine 执行环境；风险阻断时显示原因并禁止继续，不用 alert 或静态假账户掩盖失败。

### 导航

页面顶部显示 `决策中心 / 股票 / 回测验证` 面包屑。切换股票时清除旧股票的临时 K 线、证据、回测和资格结果；有未保存回测时要求确认。

## 请求与状态

统一 API client 的 JSON headers、错误传播和 AbortSignal。研究请求使用 request key 和 AbortController；旧股票的慢响应不得覆盖新股票。

所有模块使用明确状态：

- `loading`: 显示具体模块；
- `empty`: 显示原因和下一步；
- `stale`: 显示更新时间和刷新；
- `unavailable`: 显示后端原因并阻断依赖能力；
- `ready`: 显示来源和可执行下一步。

禁止以 `0`、空白、永久“计算中”、固定推荐或随机 mock 表示未知状态。

认证页面必须支持 `/auth`、深链接和会话过期后的回跳；后端 history fallback 与前端路由保持一致。

## 验收

### 桌面主流程

1. 登录；
2. 决策中心选择股票；
3. 研究页显示真实 K 线或明确不可用原因；
4. 证据按来源加载并显示真实状态；
5. 进入验证，股票和策略自动继承；
6. 运行回测并显示结果或可解释错误；
7. 进入模拟盘预览，显示订单摘要、价格来源和风险状态。

### 边界流程

- 未登录直接访问研究深链接；
- 快速切换两个股票；
- K 线为空；
- 单一证据源失败；
- 回测失败；
- 刷新验证页；
- 无上下文直接进入验证/模拟盘；
- 非法订单数量；
- 风控阻断；
- 移动端完成核心流程。

### 完成标准

- 核心流程不依赖固定 mock；
- 没有永久禁用的主流程按钮；
- 上下文在页面间可靠继承；
- 成功、失败、空、过期均可解释；
- 桌面主流程端到端可操作；
- 移动端可完成核心操作；
- 前端构建、相关契约测试和真实浏览器验证通过。
