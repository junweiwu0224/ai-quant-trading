# 0001 Signal Engine v2 replaces Qlib as runtime signal boundary

- 状态：Accepted
- 日期：2026-06-07
- 相关链接：`data/signals/`, `/api/signals/*`, `/api/qlib/*`

## 背景

系统原来把机会池、数据中枢、情报页、估值和部分 OpenClaw 工具都直接绑定到
`Qlib` 命名和预测缓存。当前实现实际并不是完整 pyqlib 训练栈，而是本地
`stock_daily` 生成的轻量动量分数；继续把它称为 Qlib 会误导用户，也会让未验证
信号在决策链路里被过度背书。

用户目标是全市场覆盖、可解释、可验证的机会发现，而不是维护一个容易失效的
Qlib 外壳。

## 决策

我们决定：

- 新增 `data/signals/` 作为运行时 AI 信号边界。
- 新增 `/api/signals/top`、`/api/signals/health`、`/api/signals/validation`、`/api/signals/consistency`。
- 现有 `/api/qlib/*` 保留为 legacy adapter，继续返回旧字段，避免历史前端和策略断裂。
- DataHub、估值、情报页和 OpenClaw 新入口优先使用 Signal Engine 语义。
- 未完成历史验证的信号必须降权，并在风险标签中显示 `AI未验证`。

## 主要取舍

选择 Signal Engine v2 的原因：

- 它准确描述当前能力：本地行情派生信号，而不是完整 Qlib。
- 它允许未来接入多个 provider，例如 local_momentum、LEAN 回测结果、外部模型或人工规则。
- 它把“覆盖”和“验证”分开，避免全量覆盖被误当成有效预测。

放弃和接受的代价：

- 短期内代码里仍有 `qlib_*` 字段、DOM id 和策略 id，这是兼容债。
- 旧预测缓存文件暂时仍放在 `data/qlib/predictions_cache.json`，但运行时语义由 Signal Engine 包装。
- UI/测试需要逐步从 Qlib 文案迁移到 AI 信号文案。

## 影响

- 正面影响：机会池、市场情报、估值和 OpenClaw 工具的用户语义更真实；未验证信号不会再被当成强预测。
- 负面影响 / 风险：旧 `qlib_*` 字段仍可能被新代码误用；未来清理时要保留 API 兼容或提供迁移期。
- 需要同步修改的地方：Agentic 策略候选、模拟盘策略名称、旧 `/api/qlib/train` 训练入口和历史文档。

## 后续

- 为 Agentic 层新增 `signal_top` / `signal_score` 语义，同时把 `qlib_top` 保留为 alias。
- 将 `data/qlib/predictor.py` 输出缓存迁移到 provider 命名目录或统一 signal cache。
- 为全市场信号增加可复跑的验证报告，并在前端展示样本天数、超额收益和 rank IC。
