# Commands

本文件记录 AI Quant Trading 的常用命令。命令变化时同步更新 `AGENTS.md`、`docs/testing.md` 和 `docs/quality-gates.md`。

## 环境

```bash
.venv/bin/python -m pip install -r requirements.txt
```

如果 `.venv/` 不存在，先运行 `python3 -m venv .venv`。本机 macOS/Linux 优先使用 `.venv/bin/python`，不要假设存在 `python` 命令。

## 本地开发

```bash
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service
```

默认 Dashboard 地址：

```text
http://127.0.0.1:8001
```

不加 `--no-signal-service` 会尝试启动 AI 信号兼容服务子进程（历史模块路径仍为 `data.qlib.service`），并写 `logs/qlib_service.log`。

## Docker

```bash
docker compose up -d
docker compose down
```

`docker compose up -d` 会启动 OpenClaw 和 Dashboard，并挂载 `data/`、`logs/`、`dashboard/templates/`、`dashboard/static/`。执行前确认本地数据和环境变量影响，并在 `.env` 或外部环境中设置 `OPENCLAW_API_KEY`；OpenClaw gateway 默认只通过 compose 网络暴露给 Dashboard，不发布宿主机 `18789` 端口。

本地交付预检默认不执行 Docker；需要容器或部署验证时，先确认环境和数据影响。

## 测试

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_signal_engine.py -q
.venv/bin/python -m pytest tests/test_dashboard.py -q
```

`pyproject.toml` 设置了 `testpaths = ["tests"]`，并定义 `unit`、`integration` markers。

## 本地交付预检

```bash
.venv/bin/python scripts/release_preflight.py --dry-run
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/release_preflight.py
.venv/bin/python scripts/release_preflight.py --with-audits
.venv/bin/python scripts/release_preflight.py --with-deployment-static
.venv/bin/python scripts/release_preflight.py --with-production-static
.venv/bin/python scripts/release_preflight.py --with-production-env
.venv/bin/python scripts/release_preflight.py --with-production-auth
.venv/bin/python scripts/deployment_static_preflight.py
.venv/bin/python scripts/deployment_static_preflight.py --production
.venv/bin/python scripts/production_env_preflight.py --profile all
.venv/bin/python scripts/production_auth_preflight.py
```

默认预检只编排本地可复现门禁：context pack verifier、release evidence 覆盖检查、全量 pytest、compileall 和 `git diff --check`。它不会启动 Dashboard、Docker、真实 provider、OpenClaw/LLM、同步数据、运行交易脚本或修改生产配置。`--verify-evidence` 可单独检查当前 modified/untracked 文件是否都被交付证据清单覆盖；`--with-audits` 会额外运行数据展示健康和前端静态扫描，并写入 `test-results/data-display-audit/` 报告；`--with-deployment-static` 会额外运行不启动 Docker 的部署静态预检；`--with-production-static` 会使用生产静态门禁，检查 OpenClaw token auth、compose-only expose 和生产风险决策文档；`--with-production-env` 会显式运行生产环境变量预检，要求当前 shell 已提供上线所需变量；`--with-production-auth` 会运行不导入 app 的生产认证静态预检。

`scripts/deployment_static_preflight.py` 只读取 `docker-compose.yml`、`Dockerfile`、`.dockerignore`、`.env.example` 和生产风险决策文档，检查交易 profile、默认 APP_ENV、密钥注入、Docker 忽略项、OpenClaw token/network 边界和上线签收材料是否存在。默认只因 hard finding 失败；`--production` 或 `--fail-on-soft` 会把生产上线前需要确认的 soft finding 也作为失败。

`scripts/production_env_preflight.py` 只读取当前进程环境变量，不读取 `.env` 文件、不启动服务、不连接外部系统、不打印 secret 值。可用 `--profile base|docker|llm|provider|all` 分层检查：`base` 要求 `APP_ENV=production` 和 `QUANT_SYSTEM_API_KEY`，`docker` 额外要求 `OPENCLAW_API_KEY`，`llm` 额外要求 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`，`provider` 额外要求 `IWENCAI_COOKIE`。

`scripts/production_auth_preflight.py` 只读源码和测试文件，不导入 FastAPI app、不触发生命周期、不读取 `.env` 或数据库。它检查生产认证边界：测试环境绕过仅限 `APP_ENV=test`、生产 CORS 不包含 localhost、session cookie 在生产启用 `secure`、API key 用 constant-time compare、生产不自动创建 `LOCAL1` 邀请码、邀请码和 session token 不以明文审计/存储。

本地交付证据清单写在 `docs/release-evidence/`。当前同花顺式平台升级收口证据见 `docs/release-evidence/2026-06-12-local-delivery-readiness.md`。

生产上线执行顺序和确认边界见 `docs/production-readiness-runbook.md`。该 runbook 包含 Docker compose、真实 provider、OpenClaw/LLM、数据同步和交易相关门禁；这些步骤默认不由本地预检执行。长期生产风险门禁见 `docs/decisions/0004-production-release-risk-gates.md`，发布签收模板见 `docs/release-evidence/production-release-decision-template.md`。

## Context pack 验证

```bash
.venv/bin/python scripts/verify_context_pack.py
.venv/bin/python -m pytest tests/test_verify_context_pack.py -q
```

该命令只检查 Codex context pack 文件、命令写法、架构文档引用和敏感模式，不启动 Dashboard、不连接外部服务、不写业务数据库。

## 语法检查

```bash
.venv/bin/python -m compileall -q .
```

适合快速发现 Python 语法错误。注意：该命令会更新 `__pycache__/`，但这些文件应保持忽略状态。

## 数据展示健康检查

```bash
.venv/bin/python scripts/dashboard_data_health.py
.venv/bin/python scripts/frontend_data_render_audit.py
```

`dashboard_data_health.py` 使用 FastAPI TestClient 扫描 API 返回值，不连接外部服务，但会触发应用 lifespan：初始化本地数据库、短暂启动/停止调度器和行情服务，并写入 `test-results/data-display-audit/api-report.json`。`frontend_data_render_audit.py` 静态扫描前端渲染风险，并写入 `test-results/data-display-audit/frontend-static-report.json`。

## E2E

先启动 Dashboard：

```bash
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service
```

再运行：

```bash
scripts/e2e-local.sh smoke
scripts/e2e-local.sh data-health
scripts/e2e-local.sh all
```

或者使用 Docker runner：

```bash
npm run e2e:docker
```

`package.json` 中 `npm run e2e` 和 `npm run e2e:data-health` 依赖 Playwright 配置；`npm test` 当前是占位脚本，会直接失败。

## 数据和运维脚本

```bash
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/sync_data.py
.venv/bin/python scripts/audit_stock_info.py
.venv/bin/python scripts/audit_stock_info.py --cleanup-preview
.venv/bin/python scripts/audit_stock_info.py --shadow-apply --confirm MERGE_AND_DELETE_STOCK_INFO_DUPLICATES
.venv/bin/python scripts/audit_stock_info.py --cleanup-apply --confirm MERGE_AND_DELETE_STOCK_INFO_DUPLICATES
.venv/bin/python scripts/sync_stock_industry.py --dry-run
.venv/bin/python scripts/sync_stock_industry.py
.venv/bin/python scripts/sync_signal_daily.py
.venv/bin/python scripts/sync_full_stock_daily.py
.venv/bin/python scripts/verify_datasource.py
.venv/bin/python scripts/run_backtest.py
.venv/bin/python scripts/run_paper.py
.venv/bin/python scripts/run_live.py
```

这些命令可能写入本地数据库、同步外部数据、启动交易相关流程或依赖外部服务。`scripts/audit_stock_info.py --shadow-apply` 只写 `test-results` 里的数据库副本，用于验证清理效果；`scripts/audit_stock_info.py --cleanup-apply` 会合并并删除真实库历史错前缀重复行，必须先跑 `--cleanup-preview` 和 `--shadow-apply` 并确认影响范围。`scripts/sync_signal_daily.py` 是 AI 信号覆盖池主入口，旧 `scripts/sync_qlib_daily.py` 仅保留兼容。除非任务明确需要，优先只读检查；运行前确认影响范围。

## 待确认

- 是否有项目标准 lint/format 命令。
- 是否需要把常用 pytest 子集沉淀为脚本或 Makefile target。
