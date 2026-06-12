# 0004 Production release requires explicit risk gates

- 状态：Accepted
- 日期：2026-06-13
- 相关链接：
  - `docs/production-readiness-runbook.md`
  - `docs/release-evidence/2026-06-12-local-delivery-readiness.md`
  - `docs/release-evidence/production-release-decision-template.md`

## 背景

同花顺式平台升级已经形成本地交付包、预检脚本和本地 E2E 证据，但这不等同于生产上线批准。当前剩余风险跨越多个信任边界：

- OpenClaw gateway 必须在 Docker Compose 中使用 token auth，并且默认只暴露给 compose 内部网络，不能发布宿主机端口 `18789`。
- 真实 iWencai/provider、外部 LLM/OpenClaw、数据同步、数据库迁移、paper/live/broker/trading 都需要凭证、额度、数据写入或交易边界确认。
- 本地 release preflight 的目标是可复现交付证据，不会启动 Docker、访问真实 provider、调用外部 LLM/OpenClaw、写生产数据或执行交易。

如果没有明确的上线风险门禁，团队容易把“本地可交付”误判成“可以生产暴露”。

## 决策

我们决定：

1. 生产上线前必须先完成 `docs/production-readiness-runbook.md` 中的确认型门禁，并把结果记录到 `docs/release-evidence/production-release-decision-template.md` 的副本或等价发布批准记录中。
2. `scripts/deployment_static_preflight.py` 必须把缺失的生产风险决策文档、OpenClaw `--auth none`、未使用 token auth、缺少 `OPENCLAW_API_KEY` 注入、宿主机端口 `18789` 发布等视为 hard finding。
3. OpenClaw auth/network、真实 provider、外部 LLM/OpenClaw、数据同步/迁移、paper/live/broker/trading 不允许通过本地预检自动放行。
4. 若上线时选择临时接受外部 OpenClaw 面板公开入口、真实 provider 限制或交易边界风险，必须记录 owner、到期时间、补偿控制、回滚方式和后续修复项；不得无限期默认接受。

## 主要取舍

- 选择这个方案的原因：把“能打包交付”和“能生产暴露”分开，避免本地测试通过后误触发外部服务、数据写入或交易路径。
- 放弃的替代方案：不把 Docker compose、真实 provider、LLM/OpenClaw、数据同步和交易 smoke 纳入默认 release preflight，因为这些命令有外部副作用或需要凭证/数据/网络批准。
- 接受的代价：上线前多一道人工签收和证据记录；如果 token、网络隔离或发布决策文档退化，生产推进会被静态门禁或人工发布审查拦住。

## 影响

- 正面影响：
  - 本地交付包可以继续快速验证和交接。
  - 生产暴露风险有明确 owner、到期时间、补偿控制和回滚路径。
  - 后续 Codex 或人工 release review 可以直接检查 ADR、runbook、decision record 和静态预检输出。
- 负面影响 / 风险：
  - 仅有 ADR 和模板不能证明生产环境已安全；真实上线仍需要执行 runbook 并保留环境证据。
  - 如果团队选择公开 OpenClaw 原生面板，仍必须用反向代理认证、防火墙、短期风险接受和回滚计划降低风险。
- 需要同步修改的地方：
  - `docs/production-readiness-runbook.md`
  - `docs/release-evidence/2026-06-12-local-delivery-readiness.md`
  - `scripts/deployment_static_preflight.py`
  - `tests/test_deployment_static_preflight.py`

## 后续

- 生产前复制 `docs/release-evidence/production-release-decision-template.md`，填入实际 commit、bundle、checksum、Docker/provider/LLM/data/trading 证据和签收结论。
- 若 OpenClaw auth/network 策略未来变化，更新本 ADR 或新增 superseding ADR，并同步静态预检。
- 若上线范围包含真实交易或 broker，必须另行定义交易批准标准，不能复用本地 release preflight 作为交易批准。
