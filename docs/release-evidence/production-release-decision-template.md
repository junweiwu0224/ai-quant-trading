# Production Release Decision Template

本模板用于把本地交付包推进到生产上线前的签收记录。它不是默认批准；只有在每个门禁都有证据、owner 和结论后，才可以作为发布批准附件。

## Release Identity

- 日期：
- Branch：
- Commit SHA：
- Bundle path：
- Bundle checksum file：
- Release evidence：
- 决策状态：Draft / Approved / Rejected / Deferred
- 决策人 / owner：

## Local Evidence Gate

- `git status --short`：
- `.venv/bin/python scripts/release_preflight.py --verify-evidence`：
- `.venv/bin/python scripts/build_release_bundle.py --verify-only`：
- `.venv/bin/python scripts/deployment_static_preflight.py`：
- `.venv/bin/python scripts/deployment_static_preflight.py --production`：

结论：

## Production Environment Gate

不得在本记录中填写 secret 原文；只记录命令、状态和 operator 确认。

- `.venv/bin/python scripts/production_env_preflight.py --profile base`：
- `.venv/bin/python scripts/production_env_preflight.py --profile docker`：
- `.venv/bin/python scripts/production_env_preflight.py --profile llm`：
- `.venv/bin/python scripts/production_env_preflight.py --profile provider`：
- `.venv/bin/python scripts/production_env_preflight.py --profile all`：
- `APP_ENV=production` 是否确认：
- Dashboard API key 是否由受控环境注入且未写入仓库：
- OpenClaw token 是否由受控环境注入且未写入仓库：
- LLM/provider 凭证是否仅在批准范围内使用：

结论：

## Production Auth Boundary Gate

- `.venv/bin/python scripts/production_auth_preflight.py`：
- 测试环境 API 绕过是否仅限 `APP_ENV=test`：
- 生产 CORS 是否只允许批准的 HTTPS origin：
- `quant_session` cookie 在生产是否 `secure` / `httponly` / `samesite=lax`：
- API key 是否由 `X-API-Key` / `Authorization: Bearer` 支持，且使用 constant-time compare：
- 生产是否禁止默认创建 `LOCAL1` 邀请码：
- session token / invite code 是否只按 hash 存储或审计：
- 注册审计是否未记录明文邀请码：

结论：

## OpenClaw Auth And Network Gate

- 当前配置是否使用 `openclaw gateway run --auth token --token "$${OPENCLAW_API_KEY}"`：
- 当前配置是否仅 `expose: 18789` 到 compose 网络，且未发布宿主机端口：
- `OPENCLAW_API_KEY` / `OPENCLAW_GATEWAY_TOKEN` 是否从环境注入且未写入仓库：
- 若需要原生 Web 面板，`OPENCLAW_WEB_URL` 是否指向受控反向代理入口：
- 解决方式：保持 compose-only expose / 反向代理认证 / 防火墙 / 内网限定 / 临时接受
- 若临时接受：
  - Owner：
  - 到期时间：
  - 补偿控制：
  - 修复 issue / 后续 ADR：
  - 回滚命令：

结论：

## Docker Compose Gate

- `docker compose config`：
- `docker compose up -d --build dashboard openclaw`：
- `docker compose ps`：
- Dashboard health smoke：
- 日志检查：
- 回滚命令：

结论：

## Real Provider / iWencai Gate

- 是否使用真实 cookie/token：
- 查询语句和频率：
- 是否记录或暴露敏感凭证：
- `provider_status` / `source_status` / `parsed_conditions` / `candidate_provenance`：
- unsupported field / schema drift / rate limit 降级行为：
- 写入池、自选、篮子、回测草案动作是否在降级状态下阻断：

结论：

## OpenClaw / LLM Gate

- 外部服务地址和认证范围：
- 模型 / 额度 / 日志边界：
- `/api/openclaw/status`：
- 只读 chat smoke：
- workspace / audit / history 隔离：
- 禁止项是否保持禁止：交易、broker、数据迁移、生产配置写入

结论：

## Data Sync And Migration Gate

- 数据目录：
- 备份位置：
- preview / shadow apply 结果：
- 是否连接外部数据源：
- 是否写入 `data/db/`、`data/quant.db`、`data/paper_trading.db` 或状态文件：
- 回滚方式：

结论：

## Paper / Live / Broker Gate

默认结论应为 `Not approved`，除非本次上线范围明确包含交易验证且已经单独批准。

- paper/live 环境隔离：
- broker SDK / 账号 / 权限：
- 最大下单金额 / 风控阈值：
- 审计记录：
- 回滚和熔断：
- 被批准的命令：

结论：

## Final Decision

- Approved / Rejected / Deferred：
- 必须先修复的问题：
- 被临时接受的风险：
- 风险接受到期时间：
- 回滚负责人：
- 下一次复核日期：
