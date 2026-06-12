# Production Readiness Runbook

本 runbook 用于把 AI Quant Trading 的本地交付包推进到可上线交付。它不是生产发布批准；任何会启动容器、访问外部服务、写数据库、同步数据、调用 LLM/OpenClaw、模拟盘/实盘或修改生产配置的步骤，都必须先确认环境、凭证、数据影响和回滚窗口。

## 当前基线

- 分支：`codex/local-delivery-2026-06-12`
- 本地交付证据：`docs/release-evidence/2026-06-12-local-delivery-readiness.md`
- 本地 bundle：`releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz`
- Bundle 校验：`releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz.sha256`
- 默认本地预检不启动 Dashboard、Docker、真实 provider、OpenClaw/LLM、同步数据、交易脚本或生产配置。

## 0. 只读准备

可直接执行：

```bash
git status --short
.venv/bin/python scripts/release_preflight.py --dry-run
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/build_release_bundle.py --verify-only
.venv/bin/python scripts/deployment_static_preflight.py
.venv/bin/python scripts/release_preflight.py --with-production-static
.venv/bin/python scripts/production_env_preflight.py --profile base
.venv/bin/python scripts/production_auth_preflight.py
.venv/bin/python scripts/production_release_decision_verify.py
```

通过标准：

- Git 工作树没有未提交源码改动。
- Release evidence 和 bundle verify 通过。
- Deployment static preflight 没有 hard findings。
- 生产静态门禁通过；OpenClaw 必须保持 token auth、compose-only network expose，且不能默认发布宿主机 `18789` 端口。生产风险门禁见 `docs/decisions/0004-production-release-risk-gates.md`；签收模板见 `docs/release-evidence/production-release-decision-template.md`。
- 生产环境变量基础门禁通过；脚本只报告变量状态，不打印 secret 值。
- 生产认证静态门禁通过；测试环境绕过、生产 CORS、session cookie、API key、默认邀请码和审计红线没有退化。
- 生产发布决策模板校验通过；填写后的发布记录必须再用 `--decision <record>` 校验。

## 1. 本地标准门禁

可直接执行：

```bash
.venv/bin/python scripts/release_preflight.py --with-deployment-static
```

通过标准：

- Context pack OK。
- Release evidence OK。
- Pytest 全量通过。
- Compileall 通过。
- `git diff --check` 通过。
- Deployment static preflight 没有 hard findings。

如果失败：

- 保留输出。
- 使用 `debug-loop` 定位根因。
- 修复后重跑同一命令。
- 不要跳过失败门禁继续上线。

## 1.5 生产环境变量门禁

该门禁只读取当前 shell 环境变量，不读取 `.env` 文件、不启动服务、不连接外部系统、不打印 secret 值。它用于上线前确认配置是否已经由 operator 注入，而不是证明凭证真的有效。

按上线范围执行：

```bash
.venv/bin/python scripts/production_env_preflight.py --profile base
.venv/bin/python scripts/production_env_preflight.py --profile docker
.venv/bin/python scripts/production_env_preflight.py --profile llm
.venv/bin/python scripts/production_env_preflight.py --profile provider
.venv/bin/python scripts/production_env_preflight.py --profile all
```

通过标准：

- `base`：`APP_ENV=production`，`QUANT_SYSTEM_API_KEY` 已设置且不是占位值。
- `docker`：除 base 外，`OPENCLAW_API_KEY` 已设置，用于 OpenClaw token auth。
- `llm`：除 base 外，`OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 已设置；后续仍需只读 LLM smoke。
- `provider`：除 base 外，`IWENCAI_COOKIE` 已设置；后续仍需真实 provider rate-limit 和不泄密验证。

如果失败：

- 不要把真实 secret 写入文档、日志或最终回复。
- 由 operator 在受控环境中注入变量后重跑同一命令。
- 不要为了让门禁通过而把 secret 写入仓库或 `.env.example`。

## 1.6 生产认证静态门禁

该门禁只读源码和测试文件，不导入 FastAPI app、不触发应用 lifespan、不读取 `.env` 或数据库。它用于上线前确认认证边界没有在后续改动中被静态弱化。

执行：

```bash
.venv/bin/python scripts/production_auth_preflight.py
```

通过标准：

- `SessionGateMiddleware` 的测试绕过只限 `APP_ENV=test`。
- 配置 API key 后，HTTP API 支持 `X-API-Key` 或 `Authorization: Bearer`，且比较使用 constant-time compare。
- 生产 CORS 只允许批准的 HTTPS origin，不包含 `localhost` 或 `127.0.0.1`。
- `quant_session` cookie 在 `APP_ENV=production` 下启用 `secure`，并保留 `httponly`、`samesite=lax`、`path=/`。
- 生产环境未设置有效 `QUANT_DEFAULT_INVITE_CODE` 时不会自动创建 `LOCAL1` 默认邀请码。
- session token 和 invite code 只按 hash 存储/查询，注册审计记录不写明文邀请码。

如果失败：

- 先确认是脚本误报还是认证边界真的退化。
- 真退化时修复源码并补测试，再重跑同一门禁。
- 不要通过放宽门禁来推进上线。

## 1.7 生产发布决策记录门禁

该门禁只读 `docs/release-evidence/production-release-decision-template.md` 或填写后的 Markdown 发布记录，不读取环境变量、不启动服务、不连接外部系统、不打印疑似 secret 值。默认命令验证模板结构；上线前必须复制模板填写实际证据后再验证填写记录。

执行：

```bash
.venv/bin/python scripts/production_release_decision_verify.py
.venv/bin/python scripts/production_release_decision_verify.py --decision <filled-record>
```

通过标准：

- 模板包含 Release Identity、本地证据、生产环境、认证边界、OpenClaw 网络、Docker、真实 provider、OpenClaw/LLM、数据同步、交易和 Final Decision 等章节。
- 填写后的记录必须有 branch、commit、bundle、checksum、release evidence、决策状态和 owner。
- 每个生产门禁必须有明确结论。
- Final Decision 必须在 `Approved`、`Rejected`、`Deferred` 中选择一个。
- 如临时接受 OpenClaw 网络、真实 provider 或交易边界风险，必须记录 owner、到期时间、补偿控制、回滚命令和后续修复项。
- 记录中不得出现 API key、token、cookie、password、Bearer token 或类似 secret 原文。

如果失败：

- 补齐发布证据或风险 owner 后重跑同一命令。
- 若失败原因是记录了 secret 原文，删除该值、轮换受影响凭证，并只保留 present/missing/operator-confirmed 等状态。
- 不要把模板校验通过当作生产发布批准；批准必须来自填写后的记录和本 runbook 的实际门禁证据。

## 2. Docker Compose 验证

需要先确认：

- 允许 Docker 写入/挂载本地 `data/`、`logs/`、`dashboard/templates/`、`dashboard/static/`。
- 已决定是否设置 `QUANT_SYSTEM_API_KEY`、`APP_ENV`、`OPENAI_*`、`OPENCLAW_*`、`IWENCAI_COOKIE`。
- 已设置 `OPENCLAW_API_KEY`，并确认 OpenClaw gateway 仅通过 compose 网络 `expose: 18789` 供 Dashboard 容器访问；若需要原生 Web 面板，必须显式设置受控的 `OPENCLAW_WEB_URL`。
- 已通过 `.venv/bin/python scripts/production_env_preflight.py --profile docker`。
- 已通过 `.venv/bin/python scripts/production_auth_preflight.py`。
- 已准备发布决策记录草案，并将在 Docker/provider/LLM/data/trading 门禁完成后运行 `.venv/bin/python scripts/production_release_decision_verify.py --decision <record>`。

确认后执行：

```bash
docker compose config
docker compose up -d --build dashboard openclaw
docker compose ps
```

建议 smoke：

```bash
curl -fsS http://127.0.0.1:8001/api/health
curl -fsS http://127.0.0.1:8001/
```

通过标准：

- `docker compose config` 成功。
- Dashboard 和 OpenClaw 容器处于 running/healthy 或等价可用状态。
- Dashboard 首页/API health 可访问。
- 日志无启动循环、密钥缺失硬错误或数据库初始化硬错误。

回滚：

```bash
docker compose down
```

未确认前不要执行：

- `docker compose up -d`。
- 修改生产 `.env`。
- 清理或迁移真实数据目录。

## 3. 浏览器和 E2E 验证

需要 Dashboard 已启动。默认使用本地测试数据，不提交真实 provider 查询。

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh smoke
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh data-health
```

需要更完整证据时：

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh all
```

通过标准：

- Smoke 和 data-health 均通过。
- 页面没有空白、主要资源加载失败、明显文字重叠或横向溢出。
- OpenClaw E2E 使用 mock 或受控服务，不触发外部写操作。

## 4. 真实 Provider / iWencai 验证

需要先确认：

- 允许使用真实 provider 凭证/cookie。
- 明确查询频率、rate-limit 边界和可记录的诊断信息。
- 明确不保存、展示或提交 cookie、token、真实账号信息。
- 已通过 `.venv/bin/python scripts/production_env_preflight.py --profile provider`。

建议最小 smoke：

- 使用一条低频、只读查询。
- 验证 `/api/llm/iwencai` 返回 `provider_status`、`source_status`、`parsed_conditions`、`candidate_provenance`。
- 若 provider 返回 unsupported field、schema drift 或 rate limited，UI 必须阻断写入池、自选、篮子和回测草案动作。

通过标准：

- 不泄露 cookie/token。
- provider 状态和降级原因可见。
- schema drift 或 rate limit 不会被前端伪装成 verified 结果。

## 5. OpenClaw / LLM 联调

需要先确认：

- 外部服务地址、认证、模型、额度和日志边界。
- 是否允许 OpenClaw gateway 暴露到容器网络；默认不发布宿主机端口。
- 是否启用 `OPENCLAW_MANAGED`、`OPENCLAW_AUTO_START`。
- 已通过 `.venv/bin/python scripts/production_env_preflight.py --profile llm`，如本次包含 Docker/OpenClaw gateway 也先通过 `--profile docker`。

建议顺序：

1. 先跑 `scripts/deployment_static_preflight.py --production`，确认 token auth、compose-only expose 和生产风险决策文档仍然有效。
2. 只读检查 `/api/openclaw/status`。
3. 使用受控 prompt 做一次非交易、非写入的 chat smoke。
4. 验证 audit/history 是否按用户 workspace 隔离。

禁止：

- 未确认就调用外部 LLM。
- 未确认就写 OpenClaw workspace、技能、记忆或报告。
- 让 OpenClaw 执行交易、broker、数据迁移或生产配置动作。

## 6. 数据同步和迁移

需要先确认：

- 数据目录、备份、可回滚点。
- 是否连接外部数据源。
- 是否允许写 `data/db/`、`data/quant.db`、`data/paper_trading.db` 或状态文件。

建议顺序：

```bash
.venv/bin/python scripts/audit_stock_info.py --cleanup-preview
.venv/bin/python scripts/audit_stock_info.py --shadow-apply --confirm MERGE_AND_DELETE_STOCK_INFO_DUPLICATES
```

只有在 preview 和 shadow apply 结果被确认后，才考虑真实 cleanup 或同步命令。

## 7. 模拟盘 / 实盘 / Broker

当前交付默认不批准任何交易动作。

需要先确认：

- 账户、券商 SDK、权限、风控阈值、最大下单金额、撤单策略。
- paper/live 环境隔离。
- 失败回滚和审计记录。

禁止默认执行：

```bash
.venv/bin/python scripts/run_paper.py
.venv/bin/python scripts/run_live.py
docker compose --profile trading up
```

通过标准必须单独定义，不能复用本地 release preflight 作为交易批准。

## 8. 发布决策记录

上线前复制并填写 `docs/release-evidence/production-release-decision-template.md`，记录：

- Commit SHA / branch。
- Bundle path 和 checksum。
- 本地 preflight 输出。
- Production env preflight 输出状态；不得记录 secret 值。
- Production auth preflight 输出。
- Docker compose config / ps / smoke 结果。
- Provider / OpenClaw / LLM 验证范围。
- 未解决风险、接受人和到期时间。
- 回滚命令和数据备份位置。

填写后执行：

```bash
.venv/bin/python scripts/production_release_decision_verify.py --decision <filled-record>
```

如果接受公开 OpenClaw 原生面板、真实 provider 限制或交易边界等生产风险，必须在发布批准记录中写明 owner、到期时间、补偿控制、回滚路径和后续修复项；不得把本地 release preflight 或模板校验通过当作生产发布批准。长期门禁决策见 `docs/decisions/0004-production-release-risk-gates.md`。
