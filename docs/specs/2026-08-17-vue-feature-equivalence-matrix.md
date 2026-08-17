# Vue 功能等价矩阵

> 状态：功能迁移已补齐，Vue-only 交付门禁已通过（2026-08-17）。历史 Jinja/Vanilla
> 页面仅保留在 Git 历史中，不再参与运行时或部署；旧壳 E2E 已按覆盖盘点替换为 Vue
> 路由矩阵和数据健康审计。
>
> 本文以当前分支 `HEAD` 中已删除的 Jinja/Vanilla JS 页面和当前 FastAPI 路由为行为基线。`已等价`只表示新 Vue 页面已经覆盖旧工作流并有对应契约；`部分等价`表示入口存在但仍有旧操作缺失；`有意差异`表示为了确定性决策、通知资格或真实交易安全而保留的边界，不计为回退。

## 判定规则

- 入口、数据读取、写操作、错误/空状态和桌面/移动布局都必须可找到，才可判定为已等价。
- API 存在不等于前端等价；必须同时检查页面调用、人工确认和成功/失败状态。
- AI、Agent、LLM 和结构化报告只能产生 `authoritative=false`、`decision_effect=none` 的研究 artifact；确定性决策、风控、自动推送资格和订单状态由原有服务负责。
- Broker/实盘入口保持只读或禁用。模拟盘操作可以恢复，但每个写操作必须明确显示“模拟盘”、人工确认和错误结果。

## 旧端到新端

| 旧页面/工作流 | 旧行为基线 | 新 Vue 入口 | API/证据 | 当前判定 | 后续动作 |
| --- | --- | --- | --- | --- | --- |
| 认证与工作区 | 登录、注册、会话失效、主题、桌面侧栏、移动底栏 | `AuthView.vue`、`App.vue`、`stores/app.ts` | `/api/account/*`；`tests/test_vue_full_migration_contract.py` | 已等价 | 保持 |
| 监控/overview | 自选池、市场雷达、信号矩阵、研究跳转、覆盖与数据状态 | `DecisionView.vue` | `/api/watchlist`、`/api/market/radar`、`/api/datahub/decision-matrix`、`/api/decisions/*` | 已等价 | 保持数据来源、覆盖率和陈旧状态可见 |
| 市场情报 | 市场情绪、新闻流、板块热力图、热点归因、问财、AI 信号池 | `IntelligenceView.vue`、`ScreenerView.vue` | `/api/market/*`、`/api/llm/iwencai`、`/api/signals/*` | 已等价 | 保持候选结果回到研究/验证流程 |
| 股票详情/研究 | 搜索、K 线/指标、盘口、资金、基本面、公告、新闻、北向、估值、画线、AI 报告 | `ResearchView.vue` | `/api/stock/*`、`/api/valuation/*`、`/api/llm/reports/*` | 已等价 | 继续保留数据来源和不足提示 |
| 选股 | 预设、条件构建、执行、结果搜索/排序、CSV、单只/批量自选、问财导入、AI 模型状态/训练/预测 | `ScreenerView.vue` | `/api/screener/*`、`/api/llm/iwencai`、`/api/alpha/model-status`、`/api/alpha/train-global`、`/api/alpha/screen-ai`；`tests/test_vue_screener_contract.py` | 已等价 | 候选仍需进入研究/验证；不直接改变决策或推送资格 |
| 数据/估值/信号 | 数据健康、PEG/估值、AI 信号质量、可解释矩阵 | `DecisionView.vue`、`ResearchView.vue` | `/api/datahub/*`、`/api/valuation/*`、`/api/signals/*` | 已等价 | 保持 legacy `qlib_*` 字段兼容 |
| 回测与稳健性 | 回测、样本外、Monte Carlo、收益/交易/换手/星期/持仓/归因、组合资格 | `ValidationView.vue` | `/api/backtest/*`、`/api/decisions/*/validate` | 已等价 | 增加历史保存/对比入口的证据覆盖 |
| Alpha/因子/公式/篮子 | 模型、因子、SHAP、衰减、Walk-forward、优化、公式、篮子回测 | `AlphaFactorsView.vue` | `/api/alpha/*`、`/api/factor/*`、`/api/portfolio-opt/*` | 已等价 | 保持运行结果与真实数据状态分离 |
| Agent/LLM/Copilot | Agent 注册、研究任务、对话、provider/model 配置、重试/降级、报告 | `AgentOpsView.vue` | `/api/ai/*`、`/api/agentic/*` | 已等价 | 继续验证 SSE、冻结上下文和结构化 DSA 区块 |
| 结构化报告 | 报告列表、详情、导出、分享、投递记录、AI commentary | `ReportsView.vue`、`SharedReportView.vue` | `/api/decisions/reports/*`、`/api/ai/reports/*` | 已等价 | 保持只读分享和撤销状态 |
| 通知/推送 | 目标、密钥引用、测试、路由、失败队列 | `NotificationsView.vue` | `/api/decisions/targets`、`/api/decisions/routes` | 已等价 | 不展示 secret 正文，不把测试成功当成自动资格 |
| 告警规则 | 告警规则创建、编辑、启停、删除、触发历史、条件列表 | `AlertRulesView.vue`、`DecisionView.vue` | `/api/alerts/rules`、`/api/alerts/conditions` | 已等价 | 与条件单保持独立，错误和触发历史可见 |
| 条件单 | 创建、编辑、启停、删除、事件历史 | `ConditionalOrdersView.vue` | `/api/conditional-orders/rules`、`/api/conditional-orders/events` | 已等价 | 写操作保持显式人工确认和结果反馈 |
| 交易/组合 | 持仓、绩效、风险、行业分布、手动/部分平仓、止损止盈、导出 | `PortfolioRiskView.vue` | `/api/portfolio/*`、`/api/paper/*` | 已等价 | 组合写操作只进入模拟/人工确认边界 |
| 模拟盘 | 启停/重置、手动订单、待单撤销、持仓、止损止盈、绩效、曲线、交易历史、风控事件、导出 | `PaperRiskView.vue` | `/api/paper/*` | 已等价 | 不映射到 Broker，不产生真实订单 |
| 策略管理 | CRUD、模板、代码校验、导入/导出、版本、记录、优化、ensemble 回测、AI 辅助 | `StrategyWorkbenchView.vue`、`ValidationView.vue` | `/api/strategy/*`、`/api/system/strategies/*`、`/api/strategy-version/*` | 已等价 | 内置策略保护和代码校验保持启用 |
| Broker/实盘 | 配置、网关状态、真实下单相关历史入口 | `BrokerLiveView.vue` | `/api/broker/*` | 有意差异 | 只读脱敏、无真实下单/撤单/凭证写入 |
| OpenClaw | 外部 Agent 服务、工具桥接、独立配置和页面 | 已移除运行时代码、路由、静态页面、包和本地状态 | 运行时不存在 `/api/openclaw`；Compose 无 openclaw service | 有意移除 | 使用 `/api/ai/*`、`AgentOpsView.vue` 和结构化报告工作流 |

## 验证记录

| 门禁 | 状态 |
| --- | --- |
| `npm run ui:test` | 通过：12 tests |
| Vue 契约测试 | 通过：全量 `tests/test_vue_*_contract.py`，24 passed |
| `npm run ui:build` | 通过：Vite production build |
| `git diff --check HEAD` | 通过 |
| 桌面 `1440x900` 浏览器检查 | 决策中心、市场情报、Agent Ops、选股页无横向溢出；控制台无错误/警告 |
| 移动 `390x844` 浏览器检查 | Agent Ops、选股页无横向溢出；移动导航和触控目标可用 |
| `npm run e2e:vue` / `npm run e2e:docker` | 通过：4 tests；Docker 官方 Playwright image 实跑 |
| Vue 快捷导航 | 通过：桌面/移动入口、Agent 搜索跳转、`Ctrl/⌘K` 打开和 Escape 关闭均由 Playwright 覆盖 |
| Vue 路由/数据健康审计 | 通过：18 个桌面路由、6 个移动路由；无坏值、page error、console error/warning 或横向溢出 |
| 前端静态数据渲染审计 | 通过：高风险 0；medium 95、low 1 均为可解释的动态数据展示提示 |
| Impeccable implementation detector | 通过：0 findings |
| 全量 Python | 通过：807 passed |
| API 数据健康 | 通过：37/37，失败 0，硬问题 0；软问题 3 |
| Docker Compose | 通过：`docker compose config -q`；全量 `ai` + `trading` profile 已部署，`dashboard`、`worker`、`ai-worker`、`paper`、`live` 运行中，`backtest` 正常退出 0；外部投递关闭，未启用 tunnel |

本次真实 Docker/Chrome 复核地址为 `http://127.0.0.1:8001`。Chrome 中决策中心、市场情报、单股研究、Agent 工作台、设置、报告、通知和验证均可进入；核心路由均渲染主内容，日志无错误。provider 当前仅显示配置/就绪状态，未执行真实外部 LLM 调用；`stock_daily` 覆盖仍为 `0/5543` 时，K 线回退只保留人工研究资格，不进入确定性决策或自动推送资格。

只有在“缺口”全部变为已等价或明确的有意差异，并完成后续门禁后，才能把旧前端删除视为已验证的 Vue-only cutover。
