# AGENTS.md

本文件补充 AI Quant Trading 的项目级规则。默认继承用户全局 Codex 工作原则；如有冲突，以本文件中更具体的项目规则为准。

## 项目快照

- 项目目标：A 股量化交易系统，覆盖数据采集、因子研究、策略回测、模拟交易、AI/Agent 策略研发和 Web Dashboard。
- 主要技术栈：本地验证 `.venv` 使用 Python 3.12，Docker 镜像当前基线为 Python 3.11；FastAPI、Jinja2、Vanilla JS、Chart.js、KlineCharts、SQLite/SQLAlchemy、APScheduler、pytest、Playwright、Docker Compose。
- 主要入口：`dashboard/app.py`、`scripts/run_dashboard.py`、`docker-compose.yml`、`README.md`。
- 架构文档：`docs/ARCHITECTURE.md`。
- Superpowers 计划：`docs/superpowers/plans/`。
- ADR：`docs/decisions/`。

## 设置和常用命令

优先查看 `docs/commands.md`。命令变化时同步更新该文件。

- 安装依赖：`python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`。
- 本地开发：`.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service`。
- Docker 启动：`docker compose up -d`。
- 后端/API/核心测试：`.venv/bin/python -m pytest -q`。
- 语法检查：`.venv/bin/python -m compileall -q .`。
- Context pack 验证：`.venv/bin/python scripts/verify_context_pack.py`。
- 本地交付预检：`.venv/bin/python scripts/release_preflight.py`。
- 生产环境变量只读预检：`.venv/bin/python scripts/production_env_preflight.py --profile all`。
- E2E：先启动 Dashboard，再运行 `scripts/e2e-local.sh all` 或 `npm run e2e:docker`。
- `npm test` 当前是占位脚本，会直接失败；不要把它当作项目验证命令。

## 仓库地图

- `dashboard/`：FastAPI 应用、API routers、Jinja2 模板、前端静态资源。
- `data/`：数据采集、行情服务、存储、调度、Qlib/Signal 兼容层。
- `alpha/`：因子、模型、选股、LLM 策略和 Alpha 研究工具。
- `agentic/`：Agent 驱动的信号、策略实验、回测晋级和模拟盘桥接。
- `engine/`：回测、模拟盘、实盘接口、预警、条件单和报告。
- `risk/`：风控规则、仓位、止损和监控。
- `strategy/`：内置策略、自定义策略管理和版本管理。
- `tests/`：pytest 单元/API/前端契约测试和 Playwright E2E。
- `scripts/`：Dashboard 启动、数据同步、E2E 和数据健康扫描脚本。
- `docs/`：架构、Superpowers plans、ADR 和 Codex context pack。

## 项目级工作规则

- 修改前先阅读相关模块、`docs/ARCHITECTURE.md` 和对应测试，不要只按文件名猜测。
- 前端是 Vanilla JS 多模块结构，修改页面逻辑时同步检查 `dashboard/templates/partials/scripts.html`、`dashboard/static/sw.js` 和相关测试。
- API 改动优先保持旧字段兼容；尤其是 `qlib_*` legacy 字段和新的 Signal Engine 语义并存区域。
- 涉及数据源、行情、交易、模拟盘、权限、OpenClaw、LLM 或实盘接口时，先明确安全边界和验证方式。
- 不要提交或展示 `.env`、API key、券商凭证、真实交易账号、生产数据和本地数据库内容。
- 运行会写数据库、同步外部数据、启动交易/实盘、调用外部 LLM 或下单相关脚本前，先确认影响范围。

## 验证矩阵

优先查看 `docs/testing.md` 和 `docs/quality-gates.md`。

- 文档/context pack 改动：`.venv/bin/python scripts/verify_context_pack.py`，必要时补充 Markdown 路径和引用检查。
- Python 语法或跨模块导入：`.venv/bin/python -m compileall -q .`。
- 单元/API/领域逻辑：`.venv/bin/python -m pytest <相关 tests/test_*.py> -q`，必要时再跑 `.venv/bin/python -m pytest -q`。
- Dashboard API：优先使用对应 pytest；数据展示风险可跑 `.venv/bin/python scripts/dashboard_data_health.py`。
- 前端渲染/契约：运行对应 `tests/test_*frontend*.py` 或 `.venv/bin/python scripts/frontend_data_render_audit.py`。
- 真实浏览器流程：先启动 Dashboard，再跑 `scripts/e2e-local.sh smoke`、`scripts/e2e-local.sh data-health` 或 `scripts/e2e-local.sh all`。
- 本地 Dashboard/dev server、E2E server 或任何需要监听 `localhost`/`127.0.0.1` 端口的 QA 命令，默认使用外部/非沙箱执行启动；页面验证仍优先使用 Codex in-app Browser。启动前检查 `8001` 端口和旧进程健康状态，验证后停止临时服务，除非用户明确要求保留。
- Docker/部署：`docker compose up -d` 会启动服务并写本地数据目录，执行前确认。
- 生产上线前环境变量检查：`.venv/bin/python scripts/production_env_preflight.py --profile all` 只读当前 shell 环境，不读取 `.env`，不打印 secret 值；它需要真实上线变量，默认不放进普通本地门禁或 hook。

## Hooks 和质量门禁

- 项目门禁文档：`docs/quality-gates.md`。
- 当前不默认启用阻断型 hooks；先按文档手动选择验证。
- 标准交付收口可用 `.venv/bin/python scripts/release_preflight.py`；先用 `--dry-run` 检查命令。默认不会启动 Dashboard、Docker、真实 provider、外部 LLM/OpenClaw、同步数据、交易脚本或生产配置。
- 生产前可显式加 `.venv/bin/python scripts/release_preflight.py --with-production-env` 或单跑 `scripts/production_env_preflight.py`；不得把 secret 写入仓库或文档来通过门禁。
- 适合前移的快速门禁：`.venv/bin/python scripts/verify_context_pack.py`、`.venv/bin/python -m compileall -q .`、针对性 pytest、前端静态渲染扫描。
- 不适合自动 hook：`docker compose up`、真实数据同步、E2E、外部 LLM/OpenClaw 调用、交易/实盘脚本、数据库迁移或清理。

## Subagents

- 项目 subagents 指南：`docs/subagents.md`。
- 适合并行：独立测试失败调查、后端 API 与前端契约分离调查、不同页面/不同数据域的只读影响分析。
- 禁止并行：同一 JS/CSS bundle、同一数据库迁移、同一 API contract 或同一业务语义迁移的竞争性修改。
- subagent 返回后主 agent 必须回读关键改动并运行集成验证。

## Codex 使用效果

- 效果评估文档：`docs/codex-usage.md`。
- 本仓库第一轮目标：用 3-5 个 M/L/XL 任务验证 context pack 是否减少上下文定位、验证选择和用户纠偏成本。
- 当前最容易过度流程化的场景：小型文档修正、单文件测试修复、只读问题回答。

## 安全和数据

敏感区域：

- `.env`、`.env.local`、`data/broker_config.json`、`data/db/`、`logs/`、`models/`、`data/openclaw/`。
- `docker-compose.yml` 中的 LLM/OpenClaw/API key 环境变量。
- `engine/live_engine.py`、`engine/broker.py`、`scripts/run_live.py` 和实盘/券商相关配置。
- 自定义策略执行、OpenClaw 工具桥接、LLM 调用和 WebSocket/API key 认证。

## 文档和知识沉淀

- 架构事实更新到 `docs/ARCHITECTURE.md`。
- 命令更新到 `docs/commands.md`。
- 测试和验证策略更新到 `docs/testing.md` 或 `docs/quality-gates.md`。
- subagents 并行边界更新到 `docs/subagents.md`。
- Codex 使用效果和复盘信号更新到 `docs/codex-usage.md`。
- 长期技术取舍写入 `docs/decisions/`。
- XL/正式规格任务写入 `docs/specs/`。
- 仓库特有工作经验写入 `docs/codex-playbook.md`。
