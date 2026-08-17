# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

当前 workspace 内的个人量化研究者。用户在开盘前、午间和盘中检查自选组合，判断哪些标的
值得研究、验证或注意风险，并希望只在有意义的状态变化时收到报告。

## Product Purpose

AI Quant Trading 将行情、研究、策略回测、模拟盘和 Agent 能力组织为可复现的决策与报告
闭环：自选池经过策略组合和验证得到确定性研究动作，AI 只能解释结论，摘要通过用户选择
的渠道发送，完整报告可在手机或电脑上阅读。

## Positioning

系统的差异是每一份自动或手动决策都能反查冻结的输入、策略/权重版本、数据质量、确定性
贡献、AI 解释和投递记录，而不是把 AI 文本或实时数据直接包装成不可验证的喊单。

## Operating Context

用户以当前 workspace 的自选股为起点；同一标的可属于不同策略组合。常用流程是：在决策
中心筛选市场和组合，进入单股研究核验 K 线、指标和证据，使用验证/回测检查策略资格，
在通知设置中管理渠道，然后通过报告链接阅读完整结果。系统先在保持开机的本机 Docker
环境运行；没有服务器不阻止出站推送，但关机和断网会延迟任务。

## Capabilities and Constraints

- 当前数据主路径是 A 股的 mootdx、腾讯和东方财富。Tushare Pro、TickFlow、Longbridge 是
  目标 provider，必须在接入和验证后才可声明为可用。
- A 股是默认市场；港、美、日、韩、台按市场能力独立开启。日韩台在没有合格盘中 provider
  前只支持手动研究和定时日线报告。
- 自动推送必须经过完整数据预览、历史验证、当前健康和每个通知目标的测试。手动分析不受
  自动资格限制。
- 动作是研究状态：买入候选、关注、观望、减仓候选、重大风险。系统不执行真实下单；未来
  实盘仍需要人工确认、券商权限和独立验收。
- 现有研究、回测、模拟盘、Agent、AI Runtime 和 Dashboard 能力不能因前端重构回退。
- 凭证仅允许来自环境变量、密钥链或受保护的引用；不得写入仓库、数据库展示内容或报告。

## Evidence on Hand

- 正式产品与工程规格：`docs/specs/2026-08-14-decision-platform-refactor.md`。
- 当前系统架构和运行边界：`docs/ARCHITECTURE.md`、`docs/commands.md`、`docs/testing.md`。
- 现有数据、策略、回测、模拟盘、Agentic、Outbox 和 Dashboard 实现都在本仓库中；不能将
  fixture、空状态或未配置 provider 呈现为真实行情或已发送消息。

## Product Principles

1. 确定性动作和 AI 解释分离，AI 不拥有决策权。
2. 自动化只建立在可验证的数据、版本、健康和投递资格之上。
3. 一个结论必须能回放；一个失败必须能被看见。
4. 功能迁移必须改善从自选到报告的连续工作流，不能只替换技术栈。
5. 交易相关入口默认克制且安全，未配置时明确禁用而非暗中降级。

## Accessibility & Inclusion

Dashboard、报告和核心研究流程在桌面及移动 Web 都可用。状态不能只依赖颜色；关键交互
保持键盘可达、具备可见焦点和不小于 44px 的移动触控目标。
