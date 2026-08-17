# 0004 Worker owns decision execution and decision artifacts are immutable

- 状态：Accepted
- 日期：2026-08-14
- 相关链接：`docs/specs/2026-08-14-decision-platform-refactor.md`

## 背景

当前 Dashboard 的 FastAPI lifespan 同时启动数据调度器、行情服务和通知 Outbox
consumer。这样的结构适合本地演示，但不能可靠地区分用户控制面与后台执行面；当
Dashboard 重启、横向运行或手动调用 API 时，定时计算和消息投递都有重复执行的风险。

新产品还要求能够按历史输入、策略权重和 AI 版本复现一份已经发送的决策报告。允许
后续运行覆盖过去的分数、报告正文或投递结果，会使“可复现”失去意义。

## 决策

我们决定：

- 独立 Worker 是决策运行、定时准备、信号确认、报告生成、Outbox 消费和通知投递的
  唯一执行者；Dashboard 只提供控制面 API 和只读查询。
- 每个运行、报告投影和投递都有稳定的幂等键；Worker 崩溃或重试不能重复创建状态变化
  或外部消息。
- `DecisionInputSnapshot`、`PortfolioVersion`、`Decision`、`DecisionReport`、AI 解释补充件
  和 `DeliveryAttempt` 只追加，不更新历史业务事实。更正通过新运行、新版本或撤销状态
  表达，不能改写既有记录。
- AI 只能产生独立的报告解释补充件；它不得改变确定性动作、分数、风险否决或通知条件。

## 主要取舍

- 选择独立 Worker 是为了让 Web 重启不等于任务重启，并使单一执行所有权和故障恢复可
  审计。
- 选择追加式事实而非可编辑报告，是为了使发送后的报告、权重和证据可以精确复现。
- 代价是本机部署多一个常驻进程，存储量会持续增长，配置更新要通过创建版本而不是
  原地编辑来完成。

## 影响

- 现有在 `dashboard/app.py` 内启动的调度和通知循环必须迁移到 Worker，切换期不得同时
  运行两个 consumer。
- 现有 Outbox 的 claim/ack 语义可复用，但需要扩展路由、目标、投递尝试和幂等关联。
- 备份必须覆盖所有 SQLite 文件和不可变附件，且恢复演练必须能重放指定决策。

## 后续

- 按正式规格先实现运行所有权和只追加存储，再开放自动推送开关。
