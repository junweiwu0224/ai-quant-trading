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

### 全量本地部署（默认）

本项目中“部署”默认指全量本地 Docker 栈，不是只启动 Dashboard。该命令会构建并启动 Dashboard、独立决策 Worker、Pi Agent Worker、paper 模拟盘和 backtest 任务；V2 Live 当前禁用。`scripts/run_live.py` 仅用于拒绝 Live 请求，不作为 Compose 服务启动：

```bash
DECISION_WORKER_ENABLED=true \
DECISION_EXTERNAL_DELIVERY_ENABLED=false \
PI_AGENT_WORKER_ENABLED=true \
docker compose --profile ai --profile trading up -d --build
```

`paper` 使用现有 legacy `scripts/run_paper.py` 命令；`backtest` 是一次性任务，完成后以 `0` 退出属于正常状态。`DECISION_EXTERNAL_DELIVERY_ENABLED=false` 和 Docker 栈的 `AI_INLINE_EXECUTION=false` 必须保持关闭，确保本地部署不会自动向外部渠道投递，也不会绕过独立 Pi Agent Worker。以后凡是任务要求“部署”，默认执行上述全量命令，不得退回只启动默认服务的快捷命令。

`cloudflared` 不属于默认本地全量栈，因为它会改变网络暴露边界。只有在 `.env` 配置 `CLOUDFLARED_TUNNEL_TOKEN` 并明确确认外部暴露范围后，才单独执行：

```bash
docker compose --profile tunnel up -d cloudflared
```

停止本地全量栈：

```bash
docker compose --profile ai --profile trading down
```

部署会挂载 `data/` 和 `logs/` 并写入本地运行数据；执行前确认影响范围。若只需要 Dashboard 控制面做静态开发，才使用不带 profile 的 `docker compose up -d dashboard`，这不称为完整部署。

默认 Dashboard/Worker 镜像使用当前 Docker 平台，并排除测试依赖、`pyqlib` 和按需的 LiteLLM；BuildKit 会缓存 npm/pip 包。Pi Agent 使用独立的 `pi-agent` target，内置 Pi CLI：

```bash
docker compose build dashboard
docker compose --profile ai build pi-agent
```

跨平台构建时显式设置 Docker 平台，例如 `DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build dashboard`；不要把 amd64 模拟运行作为 Apple Silicon 的默认部署平台。

Pi Agent Worker 是 AI 任务队列的唯一生产消费者。它通过 `data/db/ai_runtime.db` 复用冻结上下文、任务、报告、脱敏 provider readiness 和有限尝试记录，但 Pi 子进程在空目录、无工具、无 session、无项目扩展的模式下运行。Pi 的模型凭据仍来自它支持的环境变量或运行时配置，不写入项目数据库；AI 输出不会写入确定性动作或自动推送资格。`paper`、`backtest` 需要显式启用 `trading` profile；V2 Live 当前禁用，`scripts/run_live.py` 是 rejection-only 入口，不是部署服务。

## 测试

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_signal_engine.py -q
.venv/bin/python -m pytest tests/test_dashboard.py -q
```

`pyproject.toml` 设置了 `testpaths = ["tests"]`，并定义 `unit`、`integration` markers。

Vue 独立工程使用自己的 lockfile；根目录命令只做转发：

```bash
npm run ui:build
npm run ui:test
```

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

`dashboard_data_health.py` 使用 FastAPI TestClient 扫描 API 返回值，不连接外部服务，但会触发应用 lifespan：初始化本地数据库、短暂启动/停止调度器和行情服务，并写入 `test-results/data-display-audit/api-report.json`。`frontend_data_render_audit.py` 默认扫描 `dashboard/ui/src` 下的 Vue/TypeScript/JavaScript 渲染风险，并写入 `test-results/data-display-audit/frontend-static-report.json`。

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

`package.json` 中 `npm run e2e` 和 `npm run e2e:data-health` 依赖 Playwright 配置；根目录不提供 `npm test`，前端测试使用 `npm run ui:test`。

## Pi Agent Worker

```bash
PI_AGENT_WORKER_ENABLED=true .venv/bin/python scripts/run_pi_agent_worker.py --once
PI_AGENT_WORKER_ENABLED=true .venv/bin/python scripts/run_pi_agent_worker.py
```

`PiAgentWorker` 是 AI task queue 的唯一生产消费者，复用 SQLite lease/fence、workspace 隔离、任务取消和审计。每个 Pi 调用都禁用 tools、session、extensions、skills、prompt templates 和项目 context，并在空临时目录运行。新部署使用 `scripts/run_pi_agent_worker.py` 和 Compose `pi-agent` 服务。

## 决策 Worker 与备份

```bash
export DECISION_WORKER_ENABLED=true
export DECISION_BACKUP_DIR=/path/to/daily-backups
export DECISION_ARTIFACT_DIRS=/path/to/decision-artifacts:/path/to/another-artifacts
.venv/bin/python scripts/run_worker.py --once
.venv/bin/python scripts/run_worker.py
.venv/bin/python scripts/backup_decisions.py --output-dir /path/to/backup --database /path/to/decisions.db
.venv/bin/python scripts/backup_decisions.py --output-dir /path/to/backup --database /path/to/decisions.db --artifact-dir /path/to/decision-artifacts
.venv/bin/python scripts/restore_decisions.py --backup-dir /path/to/backup --target-dir /path/to/restore --verify-only
.venv/bin/python scripts/restore_decisions.py --backup-dir /path/to/backup --target-dir /path/to/restore
.venv/bin/python scripts/restore_decisions.py --backup-dir /path/to/backup --target-dir /path/to/restore --replay-decision-id <decision-id>
```

`run_worker.py` 默认只读退出；必须显式设置 `DECISION_WORKER_ENABLED=true` 才会运行。Worker
从进程环境读取 `DECISION_BACKUP_DIR`（默认 `data/backups/daily`）和
`DECISION_ARTIFACT_DIRS`。后者是使用当前系统路径分隔符（macOS/Linux 为 `:`）分隔的附件目录列表；
每个目录必须已经存在，备份输出目录不能位于附件目录中。独立 Worker 在每天上海时间 02:00 的安全点
备份本地决策、事件、lease 和行情数据库以及这些附件目录；同一天已有 manifest 时复用已有备份。
manifest 的 `metadata.artifact_dirs_configured` 记录实际读取的配置，`artifacts` 记录每个附件目录的文件、
大小和 SHA-256。Dashboard 控制面不拥有决策调度或报告投递。

显式备份脚本可重复指定 `--artifact-dir`。恢复命令先用 `--verify-only` 校验 manifest、SQLite 和附件
hash，此模式不会创建目标目录；去掉该参数才会将 SQLite 和附件恢复到不存在或为空的隔离目录。备份和
恢复均使用本地显式路径，不连接 provider、通知、LLM 或交易接口。

Dashboard 兼容模式不会隐式接管后台任务。只有同时设置
`DASHBOARD_BACKGROUND_WORKER=true` 与 `WORKER_OWNERSHIP=dashboard-legacy` 才会启动旧调度器和
legacy 通知 consumer；默认配置由独立 Worker 负责决策、报告和相关 outbox。

独立 Worker 和 AI Worker 的入口会处理 Docker `SIGTERM`/`SIGINT`，先进入 draining，再由
`close()` 释放自身 lease；正常重建不需要等待旧 lease 的 TTL 回收。若进程被强制 kill 或机器
断电，仍需等待 TTL 或使用隔离恢复流程，不能把此机制当作断电保护。

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

- 是否有项目标准 lint/format 命令；当前没有额外 lint/format 门禁。
- 真实 provider、真实渠道、cloudflared 和 Docker 部署仍需单独确认外部影响范围。
