# Commands

本文件记录 AI Quant Trading 的常用命令。命令变化时同步更新 `AGENTS.md`、`docs/testing.md` 和 `docs/quality-gates.md`。

## 环境

```bash
.venv/bin/python -m pip install -r requirements.txt
```

如果 `.venv/` 不存在，先运行 `python3 -m venv .venv`。本机 macOS/Linux 优先使用 `.venv/bin/python`，不要假设存在 `python` 命令。

## 本地开发

```bash
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-qlib
```

默认 Dashboard 地址：

```text
http://127.0.0.1:8001
```

不加 `--no-qlib` 会尝试启动 `data.qlib.service` 子进程并写 `logs/qlib_service.log`。

## Docker

```bash
docker compose up -d
docker compose down
```

`docker compose up -d` 会启动 OpenClaw 和 Dashboard，并挂载 `data/`、`logs/`、`dashboard/templates/`、`dashboard/static/`。执行前确认本地数据和环境变量影响。

## 测试

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_signal_engine.py -q
.venv/bin/python -m pytest tests/test_dashboard.py -q
```

`pyproject.toml` 设置了 `testpaths = ["tests"]`，并定义 `unit`、`integration` markers。

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
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-qlib
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
.venv/bin/python scripts/sync_qlib_daily.py
.venv/bin/python scripts/sync_full_stock_daily.py
.venv/bin/python scripts/verify_datasource.py
.venv/bin/python scripts/run_backtest.py
.venv/bin/python scripts/run_paper.py
.venv/bin/python scripts/run_live.py
```

这些命令可能写入本地数据库、同步外部数据、启动交易相关流程或依赖外部服务。除非任务明确需要，优先只读检查；运行前确认影响范围。

## 待确认

- 是否有项目标准 lint/format 命令。
- 是否需要把常用 pytest 子集沉淀为脚本或 Makefile target。
