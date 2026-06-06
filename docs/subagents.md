# Subagents

本文件记录 AI Quant Trading 中 subagents 的并行边界、任务拆分规则和集成验证方式。

## 适用场景

可以并行：

- 多个独立 pytest 文件失败，根因可能不同。
- 后端 API、前端契约、样式/E2E 分属不同文件且边界清楚。
- 不同数据域的只读影响分析，例如 Signal、OpenClaw、Portfolio、Alpha。
- 已有 Superpowers 实施计划，任务之间不会修改同一文件或同一状态。

不要并行：

- 同一 `dashboard/static/style.css` 或同一 JS bundle 的竞争性修改。
- 同一 API contract、同一数据库 schema、同一数据迁移链。
- Signal/Qlib 语义迁移这种需要整体一致性的架构判断。
- 实盘、交易、权限、凭证、生产配置、外部服务写操作。

## 推荐工作流

- 有实现计划且任务独立：使用 Superpowers `subagent-driven-development`。
- 多个独立失败或独立调查：使用 Superpowers `dispatching-parallel-agents`。
- 计划不清楚或边界不稳：主 agent 先调查，不急于 dispatch。

## Prompt 要求

给 subagent 的 prompt 必须包含：

- 目标和非目标。
- 相关文件、测试、错误输出。
- 可修改范围和禁止修改范围。
- 必须遵守的安全边界。
- 需要运行的验证命令。
- 返回格式：状态、改动、验证、风险、需要主 agent 集成检查的点。

不要把完整会话历史交给 subagent；只给完成子任务所需的最小上下文。

## 集成检查

主 agent 收到结果后：

1. 阅读摘要和改动。
2. 检查文件冲突和语义冲突。
3. 回读关键源码和测试，不把 subagent 结论当作事实。
4. 运行相关集成验证。
5. 必要时进入 `debug-loop`。

## 待确认

- 本仓库是否有稳定的子系统 owner 或推荐并行分组。
