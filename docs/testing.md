# Testing

本文件记录 AI Quant Trading 的测试策略和验证矩阵。命令细节见 `docs/commands.md`。

## 测试入口

本次新增的 Evidence、Signal Ledger、Promotion、Outbox、订单意图和审计纵切，可使用不加载仓库级 FastAPI 夹具的定向测试入口验证。

本次纵切的最小命令：

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --noconftest -q tests/test_alert_outbox_contract.py tests/test_alert_outbox_wiring.py tests/test_audit_router_contract.py tests/test_evidence_store.py tests/test_evidence_collector.py tests/test_signal_ledger_and_promotion.py tests/test_notification_outbox.py tests/test_daily_workflow.py tests/test_signal_service_ledger.py tests/test_order_intent.py tests/test_order_intent_store.py tests/test_audit_read_model.py tests/test_strategy_lab_promotion_policy.py tests/test_agentic_strategy_lab.py

继续实施后的 operation/evidence 纵切可用项目默认 pytest 配置运行：

```bash
.venv/bin/python -m pytest -q tests/test_agentic_operations.py tests/test_signal_service_ledger.py tests/test_evidence_store.py tests/test_news_collector.py
```

不要对需要仓库级 fixtures 的 API 测试使用 `--noconftest`；该选项会人为移除 `client` 等项目 fixture，失败不能作为代码门禁结论。

决策平台纵切的集中验证入口：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest --noconftest -q \
  tests/test_decision_platform_invariants.py \
  tests/test_decision_backup.py \
  tests/test_decision_worker_backup_artifacts.py \
  tests/test_vue_decision_contract.py \
  tests/test_vue_more_contract.py \
  tests/test_decision_runtime_config.py \
  tests/test_decision_report_exports.py \
  tests/test_decision_report_export_contract.py
```

该入口覆盖独立 Worker lease/时区上下文、冻结输入 replay、验证硬门槛、通知资格、市场能力、
隔离恢复、Worker `DECISION_ARTIFACT_DIRS` 读取和附件恢复，以及 Vue 主路由和高级工具迁移矩阵。
它不代表真实 provider、Webhook 或真实交易接口已经联调；Docker 全量栈和桌面/移动浏览器验收需按本文件后面的交付门禁单独执行。

Worker 每日备份的本地证据也可以单独运行：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest --noconftest -q \
  tests/test_decision_worker_backup_artifacts.py
```

该测试只创建 `tmp_path` 下的临时 SQLite、附件和隔离恢复目录。它设置
`DECISION_ARTIFACT_DIRS`，调用 Worker 的 daily backup，读取实际 `manifest.json`，确认 manifest
记录附件文件和 hash，再分别执行 `verify_only=True` 与真实 restore。verify-only 必须保持目标目录不
存在；restore 必须恢复附件内容和 SQLite 文件。测试不启动 Dashboard、Docker、provider、通知、LLM
或交易接口。

- Pytest：`.venv/bin/python -m pytest -q`。
- 针对性 pytest：`.venv/bin/python -m pytest tests/test_<area>.py -q`。
- Context pack 验证：`.venv/bin/python scripts/verify_context_pack.py`。
- Python 语法检查：`.venv/bin/python -m compileall -q .`。
- E2E：启动 Dashboard 后运行 `scripts/e2e-local.sh smoke|data-health|all`，或 `npm run e2e:docker`。
- API 数据健康：`.venv/bin/python scripts/dashboard_data_health.py`。该脚本不连接外部服务，但会通过 FastAPI TestClient lifespan 初始化本地数据库、短暂启动/停止调度器和行情服务，并写入 `test-results/data-display-audit/api-report.json`。
- 前端渲染静态扫描：`.venv/bin/python scripts/frontend_data_render_audit.py`。
- Vue 构建：`npm run build --prefix dashboard/ui`。

## 改动类型矩阵

| 改动类型 | 最小验证 | 推荐补充 |
|---|---|---|
| 文档/context pack | `.venv/bin/python scripts/verify_context_pack.py` | 路径和链接检查、`rg` 搜索引用 |
| Python 语法/导入 | `.venv/bin/python -m compileall -q .` | 相关 pytest |
| 数据/存储/调度 | 相关 `tests/test_data.py`、`tests/test_scheduler.py` 或新增针对性测试 | `.venv/bin/python -m pytest -q` |
| Signal/Qlib/机会池 | `tests/test_signal_engine.py`、`tests/test_signal_api.py`、`tests/test_qlib_*` | 对应前端契约测试 |
| Dashboard API | 对应 router 的 pytest | `.venv/bin/python scripts/dashboard_data_health.py`，执行前确认接受本地 DB 初始化、临时行情订阅和 `test-results/` 报告产物 |
| Vue/TypeScript 前端 | `tests/test_vue_*`、`dashboard/ui/src/**/*.spec.ts` | 浏览器 smoke、`frontend_data_render_audit.py` |
| AI Runtime/LLM | `tests/test_ai_*.py`、`tests/test_ai_runtime.py` | 手动确认 provider 和凭证范围；禁止改变确定性结果 |
| 模拟盘/交易/实盘 | 相关 engine/paper/live 测试 | 禁止未确认的真实下单或外部写操作 |
| Docker/部署 | `docker compose config -q` | 用户要求“部署”时执行全量 `ai` + `trading` profile 命令并做容器/API/浏览器验收 |

## 决策平台验收证据

| 领域 | 当前本地证据 | 尚未证明 |
| --- | --- | --- |
| Worker 所有权 | `tests/test_decision_platform_invariants.py`、`engine/decision_worker.py`、`scripts/run_worker.py` | 长期进程、断电后真实追赶 |
| 可复现决策 | 冻结 snapshot、report fingerprint、restore replay 测试 | 真实市场数据覆盖 |
| 自动推送资格 | 数据质量、验证、目标测试和 provider capability 单测 | 真实渠道最终接收 |
| 多市场 | 市场 adapter capability 和独立时区测试 | 港美/日韩台 provider 接入 |
| Vue 迁移 | Vue build、路由/静态迁移契约、桌面 `1440x900` 与移动 `390x844` 浏览器验收 | 真实用户长期使用和外部 provider 数据覆盖 |
| 备份恢复 | SQLite online backup、manifest/hash、Worker artifact 配置读取、隔离 verify-only/restore 和 replay 测试 | 月度自动恢复演练 |
| Docker 全量部署 | 按 `docs/commands.md` 的 `ai` + `trading` profile 启动并检查容器状态、Dashboard、Worker、AI Worker、paper、live、backtest | tunnel、真实 provider、真实渠道和实盘接口 |

Dashboard 兼容调度的 ownership 条件由 `tests/test_session_gate.py`、`tests/test_scheduler.py` 和
`dashboard/app.py` 共同约束：默认控制面不启动后台调度；只有显式
`DASHBOARD_BACKGROUND_WORKER=true` 与 `WORKER_OWNERSHIP=dashboard-legacy` 才进入 legacy 模式。

## E2E 注意事项

- Dashboard 必须先运行，默认 `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001`。
- `scripts/e2e-local.sh` 依赖本仓库 `.tools/` 下的本地 Node/Playwright 工具链。
- `scripts/e2e.sh` 使用官方 Playwright Docker image。
- Docker 部署默认是全量本地栈：`DECISION_WORKER_ENABLED=true DECISION_EXTERNAL_DELIVERY_ENABLED=false AI_WORKER_ENABLED=true docker compose --profile ai --profile trading up -d --build`。`backtest` 退出码 0 是正常的一次性任务；`cloudflared` 不属于默认部署。
- AI Runtime E2E mock 要对齐真实 API 响应形状；切到 Agent/设置页后等待 `/api/ai/status`、任务和报告请求完成，再断言结构化状态、来源和权限。
- E2E 会产生 `test-results/`，该目录已在 `.gitignore` 中忽略。

## 本地 QA / Dev Server

Dashboard/dev server、E2E server 或任何需要监听 `localhost`/`127.0.0.1` 端口的浏览器 QA 命令，默认用外部/非沙箱执行启动；页面验证仍优先使用 Codex in-app Browser，以保留可视化检查、DOM 检查、console 检查和桌面/移动视口验证。

- 启动前检查 `8001` 是否已有监听进程，并确认旧进程是否健康；不要把沙箱内 `curl 127.0.0.1` 失败直接当成服务不可用，必要时用 in-app Browser 做真实访问确认。
- 优先使用项目脚本启动，例如 `.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service`。
- E2E 和 browser smoke 使用本地测试数据，不执行真实交易、真实数据同步、外部 LLM 写操作或生产配置变更。
- 记录端口、PID 或后台会话；验证完成后停止临时服务，除非用户明确要求保留。
- 普通 pytest、compileall、context pack verifier、静态前端契约测试等不需要监听端口的命令仍按常规执行。

## 测试环境

`tests/conftest.py` 会设置：

```python
os.environ["APP_ENV"] = "test"
```

`dashboard.app` 在 `APP_ENV=test` 下会绕过登录 session gate，便于 TestClient 覆盖 API。

## 风险和限制

- `.venv/bin/python -m compileall -q .` 会遍历整个仓库，可能触发本地 `__pycache__/` 更新。
- `.venv/bin/python scripts/dashboard_data_health.py` 会经 TestClient lifespan 启动应用生命周期；它应避免外部服务写入，但会触发本地数据库初始化、调度器/行情服务启动停止和报告写入。
- `.venv/bin/python scripts/frontend_data_render_audit.py` 会写 `test-results/data-display-audit/frontend-static-report.json`，适合报告型门禁，不适合严格无写入 hook。
- 全量 pytest 可能受可选依赖、外部数据源、机器环境和当前大量未提交改动影响。
- 真实数据同步、外部 LLM、Docker、实盘/券商相关验证不要放入默认自动门禁。

## 待确认

- 当前主线是否有稳定的“提交前最小测试集”。
- 是否需要新增 `make test` 或脚本统一常用验证。
