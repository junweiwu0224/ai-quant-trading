# Quality Gates

本文件记录 AI Quant Trading 的质量门禁和 hooks 策略。默认先文档化，不自动启用阻断型 hooks。

## 当前状态

- Codex hooks：未启用。
- Git hooks / pre-commit：未启用项目级阻断 hooks；启用前需按本文候选集逐条确认。
- CI required checks：未在本阶段调整。
- 本地质量门禁脚本：context pack verifier、pytest、compileall、dashboard data health、frontend render audit、Playwright E2E。
- 本地交付预检：`scripts/release_preflight.py`，用于顺序运行标准本地门禁；它不是部署或生产发布批准。

## 门禁分层

### Level 0：文档化门禁

适用于所有任务。Codex 根据 `AGENTS.md`、`docs/commands.md`、`docs/testing.md` 和本文选择验证命令。

### Level 1：快速本地门禁

适合在明确成本后前移到 hooks。默认只考虑无网络、无外部服务、无业务数据写入、不会生成大量产物的命令。

可作为默认阻断候选：

- `.venv/bin/python scripts/verify_context_pack.py`
- 针对性 pytest，根据受影响范围选择，不要求每次全部运行：
  - Context pack verifier / repo 规则：`.venv/bin/python -m pytest tests/test_verify_context_pack.py -q`
  - Dashboard 启动脚本和环境变量路由：`.venv/bin/python -m pytest tests/test_run_dashboard.py -q`
  - Intelligence 市场前端契约：`.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py -q`
- 文档路径和引用检查。

不作为默认阻断 hook，但可人工触发：

- `.venv/bin/python -m compileall -q .`：会写 `__pycache__/`，适合标准交付门禁，不适合严格无写入 hook。
- `.venv/bin/python scripts/frontend_data_render_audit.py`：会写 `test-results/data-display-audit/frontend-static-report.json`，适合报告型门禁。
- `.venv/bin/python scripts/deployment_static_preflight.py`：只读检查 Docker/部署配置和生产风险决策文档，不启动 Docker、不连接外部服务；生产上线前使用 `--production` 确认 OpenClaw token auth、compose-only expose 和签收材料仍然有效。

`scripts/dashboard_data_health.py` 不连接外部服务，但会通过 TestClient lifespan 初始化本地数据库、短暂启动/停止调度器和行情服务，并写 `test-results/data-display-audit/api-report.json`。不要把它放入无副作用 hooks；适合人工触发或较高层级门禁。

`scripts/production_env_preflight.py` 只读当前 shell 环境变量且不打印 secret 值，但它要求上线变量存在，不适合默认 hook；适合作为生产前人工门禁或带明确环境的 release review 步骤。

### Level 2：标准交付门禁

适合实现完成后主动运行：

- `.venv/bin/python scripts/release_preflight.py --dry-run`
- `.venv/bin/python scripts/release_preflight.py`
- `.venv/bin/python scripts/release_preflight.py --with-deployment-static`
- `.venv/bin/python scripts/release_preflight.py --with-production-static`
- `.venv/bin/python scripts/release_preflight.py --with-production-env`
- `.venv/bin/python scripts/deployment_static_preflight.py --production`
- `.venv/bin/python scripts/production_env_preflight.py --profile all`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m compileall -q .`
- `.venv/bin/python scripts/frontend_data_render_audit.py`
- `.venv/bin/python scripts/dashboard_data_health.py`
- 针对受影响前端页面的 browser smoke。
- 受影响 E2E：`scripts/e2e-local.sh smoke` 或 `scripts/e2e-local.sh data-health`。

本地 Dashboard/dev server 或 E2E server 启动属于人工触发的标准交付门禁：需要监听 `localhost`/`127.0.0.1` 时默认外部/非沙箱执行启动，但页面验证仍使用 Codex in-app Browser。启动前检查端口/PID，验证后清理临时服务。

`scripts/release_preflight.py` 默认只运行 context pack verifier、全量 pytest、compileall 和 `git diff --check`；不启动 Dashboard、Docker、真实 provider、OpenClaw/LLM、同步数据、交易脚本或生产配置。`--with-audits` 会额外运行 report-writing 的数据展示健康和前端静态扫描，适合手动交付证据，不适合严格无写入 hook。`--with-deployment-static` 会额外运行 Docker/环境文件静态检查，但仍不执行 `docker compose`。`--with-production-static` 使用同一只读静态检查并采用生产失败策略。`--with-production-env` 会额外运行只读环境变量检查，要求当前 shell 已准备生产变量，且输出不回显 secret 值。

### Level 3：高风险门禁

需要用户确认或专门环境：

- `docker compose up -d`
- 真实数据同步。
- OpenClaw/LLM 外部服务联调。
- 实盘/券商 SDK、交易、下单、权限和生产配置验证。

## 改动类型矩阵

| 改动类型 | 最小门禁 | 推荐门禁 | 禁止自动 hook |
|---|---|---|---|
| 文档/context pack | `.venv/bin/python scripts/verify_context_pack.py` | `.venv/bin/python -m pytest tests/test_verify_context_pack.py -q`、路径/引用检查 | 无 |
| Python 逻辑 | 针对性 pytest | compileall、全量 pytest | 外部数据同步；`compileall` 不进严格无写入 hook |
| Dashboard 启动脚本 | `.venv/bin/python -m pytest tests/test_run_dashboard.py -q` | context pack verifier、必要时手动启动 smoke | 自动启动长期服务；真实外部服务 |
| API/router | 针对性 pytest | dashboard data health（人工触发；会写本地报告并触发应用 lifespan） | 真实外部服务写入 |
| 前端 UI/JS/CSS | 前端契约测试，例如 `.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py -q` | frontend render audit、browser smoke、E2E | 自动启动长期服务；报告型扫描不进严格无写入 hook |
| 数据模型/存储 | 针对性 pytest | 全量 pytest | 迁移/清库/真实数据写入 |
| OpenClaw/LLM | 单元测试 | 用户确认后联调 | 凭证、外部调用默认禁用 |
| 模拟盘/实盘 | 单元测试 | 人工确认的 dry-run | 下单、撤单、真实账户 |
| Docker/配置 | `.venv/bin/python scripts/deployment_static_preflight.py` | `.venv/bin/python scripts/production_env_preflight.py --profile docker`，用户确认后 compose | 部署、生产配置变更 |

`release_preflight.py` 适合作为标准交付收口入口；若需要最小门禁或无写入 hook，仍按上表选择更小的针对性命令。

生产上线的人工门禁顺序、证据和回滚要求见 `docs/production-readiness-runbook.md`。该 runbook 是发布执行清单，不会自动批准 Docker、外部服务、数据同步、迁移或交易动作；生产风险 ADR 见 `docs/decisions/0004-production-release-risk-gates.md`，签收模板见 `docs/release-evidence/production-release-decision-template.md`。

## 禁止放入 hooks

- `docker compose up -d`、`docker compose down`。
- 本地 Dashboard/dev server、E2E server 或任何长期监听端口的命令。
- 安装依赖、升级依赖、修改 lock 文件。
- 数据同步、数据库迁移、清库、清缓存。
- OpenClaw/LLM 真实外部调用。
- 实盘、券商、交易、下单、撤单、权限变更。
- 需要凭证、生产配置或真实外部服务的命令。
- `scripts/production_env_preflight.py` 和 `release_preflight.py --with-production-env` 不放入默认 hook；它们需要生产变量存在，适合作为人工上线门禁。

## 失败处理

1. 记录失败命令和关键输出。
2. 判断是否由当前改动引起。
3. 使用 `debug-loop` 定位根因并最小修复。
4. 复测同一门禁。
5. 如果是既有失败或环境缺失，在最终回复说明证据、影响和未验证风险。

## 待确认

- 是否需要在本仓库启用项目级 hooks；2026-06-07 阶段复盘结论是暂不启用，只保留候选集。
- 是否需要把已验证的 Level 1 候选组合成一个项目脚本；当前证据支持文档化路由，暂不新增包装入口。
- 如果连续多次总是运行同一组命令且耗时稳定，再考虑启用 hooks 或包装成统一快速门禁。
