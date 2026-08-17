# 0005 Vue application replaces the Dashboard surface behind a compatibility window

- 状态：Accepted；兼容窗口已完成，当前运行时 Vue-only（2026-08-17）
- 日期：2026-08-14
- 相关链接：`docs/specs/2026-08-14-decision-platform-refactor.md`

## 背景

当前 Dashboard 是 Jinja2 模板配合大量 Vanilla JS 模块。功能覆盖广，但导航、页面状态、
API 调用、移动适配和跨页面上下文缺少统一边界。只重构后端会保留用户当前感受到的主
要问题：从自选、个股研究、策略验证到报告与推送的路径不连续。

直接替换旧页面又会让研究、回测、模拟盘和高级工具在迁移期间退化。

## 决策

我们决定：

- 新 UI 使用 Vue 3、TypeScript、Vite、Vue Router、Pinia 和类型化 API Client；FastAPI
  继续是唯一 HTTP/API 服务并同源托管生产构建。
- 新路由位于 `/app/*`，主导航固定为决策中心、报告、单股研究、验证/回测、通知、设置；
  高级工具进入可搜索的“更多”。
- 所有已有用户可见能力先进入功能迁移矩阵和契约测试，完成桌面与移动关键流程后才可以
  让新 UI 成为默认入口。
- 旧 Jinja/Vanilla 面板保留一个完整发布周期作为维护者回滚面；旧路径和 hash 链接通过
  显式映射转到对应新路由，不能静默丢失上下文。

## 主要取舍

- Vue 提供统一路由、状态和组件边界，代价是短期内并行维护两套前端壳。
- 分期迁移比一次替换耗时更长，但能把“功能多但不好用”的体验问题和功能不回退的工程
  约束同时满足。
- 使用同源托管减少本机域名、Cookie、WebSocket 和云隧道配置复杂度；Vite 只用于开发。

## 影响

- 前端迁移是本次重构的正式范围，不得因后端模型完成而宣布重构完成。
- 新 API 必须保持 legacy 字段兼容，直到兼容窗口结束；新 Client 使用新语义而不是继续
  扩散 `qlib_*` 命名。
- 退役前需要完成功能映射、API 契约、浏览器流程、移动布局和旧链接测试。

## 后续

- 先交付决策中心、报告和单股研究的完整新流程，再迁移高级研究和模拟盘工具。

## 完成修订（2026-08-17）

本决策的兼容窗口已完成。当前分支已将 Vue production shell 作为 `/` 和 `/app/*` 的唯一
业务前端，旧 Jinja/Vanilla 页面、静态 bundle、旧 OpenClaw 页面和服务端入口不再被
FastAPI、Compose 或 Docker image 装载。历史 hash/页面链接仍通过 Vue Router 映射到功能
等价的新入口，保留代码、市场和来源上下文；回滚依据是 Git 发布物，不再维护第二套运行时
页面。

前端等价以 `docs/specs/2026-08-17-vue-feature-equivalence-matrix.md` 为真源，并由 Vue
契约、TypeScript build、桌面/移动浏览器和 Docker smoke 共同门禁。AI/Agent/LLM 工作流
统一归入 first-party AI Runtime：配置只保存 `secret_ref`，结构化报告明确
`authoritative=false`、`decision_effect=none`，确定性决策、风控、自动推送资格和模拟/实盘
写入边界仍由独立领域服务掌握。
