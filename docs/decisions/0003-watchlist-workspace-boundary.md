# 0003 Watchlist API is current-workspace scoped

- 状态：Accepted
- 日期：2026-06-09
- 相关链接：`dashboard/routers/watchlist.py`, `workspace_watchlist`, `user_watchlist`, `dashboard/static/watchlist.js`, `dashboard/static/search.js`

## 背景

自选股是多个研究、估值、篮子和模拟交易下拉框的默认股票范围。系统同时存在新的
`workspace_watchlist` 和旧的 `user_watchlist`，历史实现会在没有当前账号时静默回退
到 legacy 表。

这个回退会制造错误信任：用户在某个账号或工作区看到“自选股为空”时，系统可能又从
旧表拿到另一套股票；反过来，旧表里有股票也不能说明当前 workspace 已经配置完成。
在测试环境或临时账号下，这会让前端下拉框、机会池和研究页面看起来像数据丢失或重复。

## 决策

我们决定：

- `/api/watchlist` 的运行时读写删除只使用当前登录账号的当前 workspace。
- 没有当前账号时返回认证错误，不再静默读取 `user_watchlist`。
- `user_watchlist` 只保留为迁移、导入或兼容数据源，不作为 Dashboard 运行时 fallback。
- 自选股为空时，前端必须显示当前账号和 workspace 提示，帮助用户判断是否切到了错误工作区。
- 需要全市场搜索的入口必须显式输入代码或名称后再查询，避免空下拉框加载全市场。

## 主要取舍

选择 current-workspace only 的原因：

- 自选股是用户决策上下文，账号和 workspace 边界比“尽量显示一点股票”更重要。
- 运行时 fallback 会掩盖认证、workspace 切换和数据迁移问题。
- 下游下拉框可以安全默认展示当前自选股，性能和语义都更稳定。

接受的代价：

- 旧表中已有但尚未迁移的股票不会自动出现在新 workspace 中。
- 测试和本地调试必须显式建立账号/workspace 上下文，不能依赖 legacy fallback。
- 如需迁移旧数据，需要单独的导入或同步流程，而不是在 API 请求时混用。

## 影响

- 正面影响：自选股、研究页面下拉框、模拟盘选择器和工作流中的股票范围更可信。
- 负面影响 / 风险：用户切到新 workspace 时可能看到空自选，需要 UI 明确提示当前身份。
- 需要同步修改的地方：任何新增股票选择器都应先判断是否是“自选优先”还是“全市场搜索”，不要默认空查询全量加载。

## 后续

- 如果需要把 legacy `user_watchlist` 迁移到 workspace，应提供显式迁移入口并显示迁移来源。
- 新增股票选择控件时，优先复用 `SearchBox` / `MultiSearchBox` 的 `emptyScope: 'watchlist'` 语义。
- 对 watchlist API 的测试应覆盖未登录 401、当前 workspace 隔离和新增/删除不污染其他 workspace。
