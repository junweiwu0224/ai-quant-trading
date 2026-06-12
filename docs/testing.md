# Testing

本文件记录 AI Quant Trading 的测试策略和验证矩阵。命令细节见 `docs/commands.md`。

## 测试入口

- 本地交付预检：`.venv/bin/python scripts/release_preflight.py`。先用 `--dry-run` 查看命令；默认运行 context pack verifier、release evidence 覆盖检查、全量 pytest、compileall 和 `git diff --check`。
- Pytest：`.venv/bin/python -m pytest -q`。
- 针对性 pytest：`.venv/bin/python -m pytest tests/test_<area>.py -q`。
- Context pack 验证：`.venv/bin/python scripts/verify_context_pack.py`。
- Python 语法检查：`.venv/bin/python -m compileall -q .`。
- E2E：启动 Dashboard 后运行 `scripts/e2e-local.sh smoke|data-health|all`，或 `npm run e2e:docker`。
- API 数据健康：`.venv/bin/python scripts/dashboard_data_health.py`。该脚本不连接外部服务，但会通过 FastAPI TestClient lifespan 初始化本地数据库、短暂启动/停止调度器和行情服务，并写入 `test-results/data-display-audit/api-report.json`。
- 前端渲染静态扫描：`.venv/bin/python scripts/frontend_data_render_audit.py`。
- 部署静态预检：`.venv/bin/python scripts/deployment_static_preflight.py`。该脚本只读 Docker/环境示例文件和生产风险决策文档，不启动 Docker、不连接外部服务；生产上线前使用 `--production` 确认 OpenClaw token auth、compose-only expose 和签收材料仍然有效。
- 生产环境变量预检：`.venv/bin/python scripts/production_env_preflight.py --profile all`。该脚本只读当前 shell 环境变量，不读取 `.env` 文件、不启动服务、不连接外部系统、不打印 secret 值；生产上线前用它确认 `APP_ENV`、Dashboard API key、OpenClaw token、LLM 和 provider 凭证边界。
- 生产认证静态预检：`.venv/bin/python scripts/production_auth_preflight.py`。该脚本只读源码和测试文件，不导入 FastAPI app、不触发 lifespan、不读取 `.env` 或数据库；生产上线前用它确认 session/API-key/CORS/邀请码审计边界仍然有效。
- 生产发布决策记录校验：`.venv/bin/python scripts/production_release_decision_verify.py` 默认验证签收模板；填写记录后用 `--decision <record>` 验证必填字段、门禁结论、风险接受字段和 secret redaction。
- 本地交付证据：`docs/release-evidence/2026-06-12-local-delivery-readiness.md` 记录本轮 release delta、验证结果、报告产物和未覆盖上线门禁。
- 生产上线 runbook：`docs/production-readiness-runbook.md` 记录需要用户确认后才执行的 Docker、真实 provider、OpenClaw/LLM、数据同步和交易门禁。

## 改动类型矩阵

| 改动类型 | 最小验证 | 推荐补充 |
|---|---|---|
| 文档/context pack | `.venv/bin/python scripts/verify_context_pack.py` | 路径和链接检查、`rg` 搜索引用 |
| Python 语法/导入 | `.venv/bin/python -m compileall -q .` | 相关 pytest |
| 数据/存储/调度 | 相关 `tests/test_data.py`、`tests/test_scheduler.py` 或新增针对性测试 | `.venv/bin/python -m pytest -q` |
| Signal/Qlib/机会池 | `tests/test_signal_engine.py`、`tests/test_signal_api.py`、`tests/test_qlib_*` | 对应前端契约测试 |
| Dashboard API | 对应 router 的 pytest | `.venv/bin/python scripts/dashboard_data_health.py`，执行前确认接受本地 DB 初始化、临时行情订阅和 `test-results/` 报告产物 |
| 认证/session/API key | `tests/test_session_gate.py`、`tests/test_openclaw_account.py` | `.venv/bin/python scripts/production_auth_preflight.py` |
| 前端 JS/模板/CSS | 对应 `tests/test_*frontend*.py` 或契约测试 | 浏览器 smoke、`frontend_data_render_audit.py` |
| OpenClaw/LLM | 相关 `tests/test_openclaw_*` | `.venv/bin/python scripts/production_env_preflight.py --profile llm`，再手动确认外部服务和凭证范围 |
| 模拟盘/交易/实盘 | 相关 engine/paper/live 测试 | 禁止未确认的真实下单或外部写操作 |
| Docker/部署 | `.venv/bin/python scripts/deployment_static_preflight.py` | `.venv/bin/python scripts/production_env_preflight.py --profile docker`，用户确认后再 `docker compose up -d` |

## E2E 注意事项

- Dashboard 必须先运行，默认 `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001`。
- `scripts/e2e-local.sh` 依赖本仓库 `.tools/` 下的本地 Node/Playwright 工具链。
- `scripts/e2e.sh` 使用官方 Playwright Docker image。
- OpenClaw E2E mock 要对齐真实 API 响应形状；切到设置页后等待 `/api/openclaw/status` 等异步状态请求完成，再断言 Skill 历史、权限或服务状态。
- E2E 会产生 `test-results/`，该目录已在 `.gitignore` 中忽略。

## 本地 QA / Dev Server

Dashboard/dev server、E2E server 或任何需要监听 `localhost`/`127.0.0.1` 端口的浏览器 QA 命令，默认用外部/非沙箱执行启动；页面验证仍优先使用 Codex in-app Browser，以保留可视化检查、DOM 检查、console 检查和桌面/移动视口验证。

- 启动前检查 `8001` 是否已有监听进程，并确认旧进程是否健康；不要把沙箱内 `curl 127.0.0.1` 失败直接当成服务不可用，必要时用 in-app Browser 做真实访问确认。
- 优先使用项目脚本启动，例如 `.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service`。
- E2E 和 browser smoke 使用本地测试数据，不执行真实交易、真实数据同步、外部 LLM/OpenClaw 写操作或生产配置变更。
- 记录端口、PID 或后台会话；验证完成后停止临时服务，除非用户明确要求保留。
- 普通 pytest、compileall、context pack verifier、静态前端契约测试等不需要监听端口的命令仍按常规执行。
- `scripts/release_preflight.py` 的默认计划也不监听端口；它只是顺序运行本地门禁。`--with-audits` 会写 `test-results/data-display-audit/` 报告，但仍不启动 Dashboard dev server 或 Docker。

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
- `.venv/bin/python scripts/deployment_static_preflight.py` 是只读静态检查，不替代 Docker build/compose smoke；生产上线前跑 `.venv/bin/python scripts/deployment_static_preflight.py --production`。
- `.venv/bin/python scripts/release_preflight.py --with-production-static` 是本地门禁加生产静态门禁的组合；它仍不启动 Docker、不调用 OpenClaw/LLM，只验证静态生产边界。
- `.venv/bin/python scripts/production_env_preflight.py --profile all` 是只读环境门禁，只检查当前 shell 中变量是否存在、是否仍是占位值、secret 是否明显过短，输出不会回显密钥值；它不证明凭证有效，也不替代真实 provider/LLM/OpenClaw smoke。
- `.venv/bin/python scripts/release_preflight.py --with-production-env` 会在标准本地门禁后显式运行生产环境变量预检；不要把它放入默认 hook，因为它要求当前环境具备上线变量。
- `.venv/bin/python scripts/production_auth_preflight.py` 是只读源码/测试门禁，不导入 `dashboard.app`，用于确认生产认证边界没有被后续改动弱化；它不替代真实 HTTPS、反向代理、浏览器登录和 API key smoke。
- `.venv/bin/python scripts/release_preflight.py --with-production-auth` 会在标准本地门禁后显式运行生产认证静态预检。
- `.venv/bin/python scripts/production_release_decision_verify.py` 是只读 Markdown 签收记录门禁；默认只验证模板，`--decision <record>` 验证填写后的发布记录是否选择最终决策、填写每个门禁结论、记录临时风险 owner/到期时间/补偿控制/回滚，并拒绝疑似 secret 原文。
- `.venv/bin/python scripts/release_preflight.py --with-release-decision` 会在标准本地门禁后显式运行生产发布决策模板校验。
- `.venv/bin/python scripts/release_preflight.py` 不等于生产发布批准；Docker、部署、真实 provider、外部 LLM/OpenClaw、数据同步、交易和生产配置验证仍需用户确认。
- 全量 pytest 可能受可选依赖、外部数据源、机器环境和当前大量未提交改动影响。
- 真实数据同步、OpenClaw、LLM、Docker、实盘/券商相关验证不要放入默认自动门禁。

## 待确认

- 当前主线是否有稳定的“提交前最小测试集”。
- 是否需要新增 `make test` 或脚本统一常用验证。
