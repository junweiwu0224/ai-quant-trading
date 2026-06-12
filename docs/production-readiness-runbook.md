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
```

通过标准：

- Git 工作树没有未提交源码改动。
- Release evidence 和 bundle verify 通过。
- Deployment static preflight 没有 hard findings。
- 生产静态门禁通过；OpenClaw 必须保持 token auth、compose-only network expose，且不能默认发布宿主机 `18789` 端口。生产风险门禁见 `docs/decisions/0004-production-release-risk-gates.md`；签收模板见 `docs/release-evidence/production-release-decision-template.md`。

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

## 2. Docker Compose 验证

需要先确认：

- 允许 Docker 写入/挂载本地 `data/`、`logs/`、`dashboard/templates/`、`dashboard/static/`。
- 已决定是否设置 `QUANT_SYSTEM_API_KEY`、`APP_ENV`、`OPENAI_*`、`OPENCLAW_*`、`IWENCAI_COOKIE`。
- 已设置 `OPENCLAW_API_KEY`，并确认 OpenClaw gateway 仅通过 compose 网络 `expose: 18789` 供 Dashboard 容器访问；若需要原生 Web 面板，必须显式设置受控的 `OPENCLAW_WEB_URL`。

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
- Docker compose config / ps / smoke 结果。
- Provider / OpenClaw / LLM 验证范围。
- 未解决风险、接受人和到期时间。
- 回滚命令和数据备份位置。

如果接受公开 OpenClaw 原生面板、真实 provider 限制或交易边界等生产风险，必须在发布批准记录中写明 owner、到期时间、补偿控制、回滚路径和后续修复项；不得把本地 release preflight 当作生产发布批准。长期门禁决策见 `docs/decisions/0004-production-release-risk-gates.md`。
