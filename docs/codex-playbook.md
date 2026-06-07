# Codex Playbook

本文件记录 Codex 在 AI Quant Trading 中长期有效的工作经验。不要重复 `AGENTS.md` 的硬规则，不记录一次性过程细节。

## 什么时候读这个文件

- 第一次处理本仓库中的中大型任务。
- 涉及 Dashboard、Signal/Qlib、OpenClaw、Agentic、模拟盘、前端视觉验证或数据源。
- 之前在本仓库出现过误判、漏测、错误修改或重复踩坑。

## 高价值工作流

- 后端/API 修改：先定位 router 和对应 `tests/test_*.py`，再跑针对性 pytest。
- Context pack 修改：先跑 `.venv/bin/python scripts/verify_context_pack.py`，再视情况补 `rg` 路径检查。
- 前端修改：同时检查 JS 模块、模板 script 顺序、service worker 缓存清单和前端契约测试。
- Signal/Qlib 修改：先读 `docs/decisions/0001-signal-engine-v2.md`，避免把 legacy Qlib 字段当成新语义。
- 数据展示问题：优先使用 `scripts/dashboard_data_health.py` 和 `scripts/frontend_data_render_audit.py` 收集证据。
- E2E：先启动 Dashboard，再用 `scripts/e2e-local.sh smoke|data-health|all`；不要直接跑占位 `npm test`。

## 搜索和定位技巧

- 找 API：`rg "APIRouter|@router|/api/" dashboard/routers dashboard/app.py`
- 找前端入口：`rg "script|static" dashboard/templates/partials/scripts.html dashboard/static`
- 找 Signal/Qlib：`rg "signal|qlib" data dashboard tests docs`
- 找 OpenClaw：`rg "openclaw|OpenClaw" dashboard data tests docs .env.example docker-compose.yml`
- 找测试：`find tests -maxdepth 1 -type f -name 'test_*.py' | sort`
- 找 Superpowers 计划：`find docs/superpowers/plans -type f | sort`

## 常见坑和规避方式

- 坑：`npm test` 是占位脚本，会直接失败。
  - 触发场景：想跑前端/项目默认测试。
  - 正确处理：根据改动选择 pytest、`scripts/e2e-local.sh` 或 `npm run e2e:*`。
  - 相关文件：`package.json`、`docs/commands.md`。

- 坑：当前 shell 没有 `python` 命令。
  - 触发场景：直接运行 `python ...` 验证命令。
  - 正确处理：优先使用 `.venv/bin/python`；如果 `.venv/` 不存在，先用 `python3 -m venv .venv` 建环境。
  - 相关文件：`docs/commands.md`、`docs/testing.md`。

- 坑：`docs/ARCHITECTURE.md` 已存在，大小写不敏感文件系统上不要再创建 `docs/architecture.md`。
  - 触发场景：应用通用 repo context pack。
  - 正确处理：在 `AGENTS.md` 和 docs 中索引现有大写文件。
  - 相关文件：`docs/ARCHITECTURE.md`。

- 坑：Signal Engine v2 与 legacy Qlib 字段并存。
  - 触发场景：机会池、DataHub、估值、OpenClaw 或 AI 信号相关修改。
  - 正确处理：保留兼容字段，新增语义优先使用 Signal Engine。
  - 相关文件：`docs/decisions/0001-signal-engine-v2.md`。

## 待沉淀事项

-
