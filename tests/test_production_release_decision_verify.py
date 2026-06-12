from __future__ import annotations

import json

from scripts import production_release_decision_verify as verifier


ROOT = verifier.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / verifier.DEFAULT_TEMPLATE


FILLED_DECISION = """# Production Release Decision

本记录用于生产上线前签收。不得在本记录中填写 secret 原文。

## Release Identity

- 日期：2026-06-13
- Branch：codex/local-delivery-2026-06-12
- Commit SHA：253573a
- Bundle path：releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz
- Bundle checksum file：releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz.sha256
- Release evidence：docs/release-evidence/2026-06-12-local-delivery-readiness.md
- 决策状态：Deferred
- 决策人 / owner：Release Owner

## Local Evidence Gate

- `git status --short`：clean
- `.venv/bin/python scripts/release_preflight.py --verify-evidence`：passed
- `.venv/bin/python scripts/build_release_bundle.py --verify-only`：passed
- `.venv/bin/python scripts/deployment_static_preflight.py`：passed
- `.venv/bin/python scripts/deployment_static_preflight.py --production`：passed

结论：passed

## Production Environment Gate

不得在本记录中填写 secret 原文；只记录命令、状态和 operator 确认。

- `.venv/bin/python scripts/production_env_preflight.py --profile base`：passed
- `.venv/bin/python scripts/production_env_preflight.py --profile docker`：passed
- `.venv/bin/python scripts/production_env_preflight.py --profile llm`：not in scope
- `.venv/bin/python scripts/production_env_preflight.py --profile provider`：not in scope
- `.venv/bin/python scripts/production_env_preflight.py --profile all`：deferred
- `APP_ENV=production` 是否确认：是
- Dashboard API key 是否由受控环境注入且未写入仓库：是，未记录原文
- OpenClaw token 是否由受控环境注入且未写入仓库：是，未记录原文
- LLM/provider 凭证是否仅在批准范围内使用：本次未批准真实调用

结论：deferred until staging shell check

## Production Auth Boundary Gate

- `.venv/bin/python scripts/production_auth_preflight.py`：passed
- 测试环境 API 绕过是否仅限 `APP_ENV=test`：是
- 生产 CORS 是否只允许批准的 HTTPS origin：是
- `quant_session` cookie 在生产是否 `secure` / `httponly` / `samesite=lax`：是
- API key 是否由 `X-API-Key` / `Authorization: Bearer` 支持，且使用 constant-time compare：是
- 生产是否禁止默认创建 `LOCAL1` 邀请码：是
- session token / invite code 是否只按 hash 存储或审计：是
- 注册审计是否未记录明文邀请码：是

结论：passed

## OpenClaw Auth And Network Gate

- 当前配置是否使用 `openclaw gateway run --auth token --token "$${OPENCLAW_API_KEY}"`：是
- 当前配置是否仅 `expose: 18789` 到 compose 网络，且未发布宿主机端口：是
- `OPENCLAW_API_KEY` / `OPENCLAW_GATEWAY_TOKEN` 是否从环境注入且未写入仓库：是，未记录原文
- 若需要原生 Web 面板，`OPENCLAW_WEB_URL` 是否指向受控反向代理入口：not in scope
- 解决方式：保持 compose-only expose
- 若临时接受：
  - Owner：无
  - 到期时间：无
  - 补偿控制：无
  - 修复 issue / 后续 ADR：无
  - 回滚命令：docker compose down

结论：passed

## Docker Compose Gate

- `docker compose config`：passed
- `docker compose up -d --build dashboard openclaw`：not approved
- `docker compose ps`：not run
- Dashboard health smoke：not run
- 日志检查：not run
- 回滚命令：docker compose down

结论：deferred

## Real Provider / iWencai Gate

- 是否使用真实 cookie/token：否
- 查询语句和频率：not approved
- 是否记录或暴露敏感凭证：否
- `provider_status` / `source_status` / `parsed_conditions` / `candidate_provenance`：local fixtures verified
- unsupported field / schema drift / rate limit 降级行为：covered by tests
- 写入池、自选、篮子、回测草案动作是否在降级状态下阻断：covered by tests

结论：deferred

## OpenClaw / LLM Gate

- 外部服务地址和认证范围：not approved
- 模型 / 额度 / 日志边界：not approved
- `/api/openclaw/status`：local contract covered
- 只读 chat smoke：not run
- workspace / audit / history 隔离：local contract covered
- 禁止项是否保持禁止：交易、broker、数据迁移、生产配置写入

结论：deferred

## Data Sync And Migration Gate

- 数据目录：data/
- 备份位置：not approved
- preview / shadow apply 结果：not run
- 是否连接外部数据源：否
- 是否写入 `data/db/`、`data/quant.db`、`data/paper_trading.db` 或状态文件：否
- 回滚方式：restore backup before approved run

结论：deferred

## Paper / Live / Broker Gate

默认结论应为 `Not approved`，除非本次上线范围明确包含交易验证且已经单独批准。

- paper/live 环境隔离：not approved
- broker SDK / 账号 / 权限：not approved
- 最大下单金额 / 风控阈值：not approved
- 审计记录：not approved
- 回滚和熔断：not approved
- 被批准的命令：none

结论：Not approved

## Final Decision

- Approved / Rejected / Deferred：Deferred
- 必须先修复的问题：真实 Docker/provider/OpenClaw/data/trading gates 未执行
- 被临时接受的风险：无
- 风险接受到期时间：无
- 回滚负责人：Release Owner
- 下一次复核日期：2026-06-20
"""


def _decision_file(tmp_path, text: str = FILLED_DECISION):
    path = tmp_path / "decision.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_current_template_verifies_ok():
    assert verifier.verify_template(TEMPLATE) == []


def test_template_reports_missing_required_section(tmp_path):
    path = tmp_path / "template.md"
    text = TEMPLATE.read_text(encoding="utf-8").replace("## Docker Compose Gate", "## Docker Gate")
    path.write_text(text, encoding="utf-8")

    findings = verifier.verify_template(path)

    assert any(item.check == "required-section" and "Docker Compose Gate" in item.message for item in findings)


def test_filled_decision_record_verifies_ok(tmp_path):
    assert verifier.verify_decision(_decision_file(tmp_path)) == []


def test_unfilled_identity_and_gate_conclusion_fail(tmp_path):
    path = _decision_file(
        tmp_path,
        FILLED_DECISION.replace("- Commit SHA：253573a", "- Commit SHA：待填").replace("结论：passed", "结论：", 1),
    )

    findings = verifier.verify_decision(path)

    assert any(item.check == "required-value" and "Commit SHA" in item.message for item in findings)
    assert any(item.check == "gate-conclusion" and "Local Evidence Gate" in item.message for item in findings)


def test_final_decision_must_choose_exact_status(tmp_path):
    path = _decision_file(tmp_path, FILLED_DECISION.replace("- Approved / Rejected / Deferred：Deferred", "- Approved / Rejected / Deferred：Approved / Rejected / Deferred"))

    findings = verifier.verify_decision(path)

    assert any(item.check == "final-decision" for item in findings)


def test_temporary_openclaw_risk_acceptance_requires_owner_expiry_controls_and_rollback(tmp_path):
    path = _decision_file(
        tmp_path,
        FILLED_DECISION.replace("- 解决方式：保持 compose-only expose", "- 解决方式：临时接受").replace("  - Owner：无", "  - Owner："),
    )

    findings = verifier.verify_decision(path)

    assert any(item.check == "risk-acceptance" and "Owner" in item.message for item in findings)


def test_temporary_openclaw_risk_acceptance_accepts_filled_nested_fields(tmp_path):
    path = _decision_file(
        tmp_path,
        FILLED_DECISION.replace("- 解决方式：保持 compose-only expose", "- 解决方式：临时接受")
        .replace("  - Owner：无", "  - Owner：Release Owner")
        .replace("  - 到期时间：无", "  - 到期时间：2026-06-20")
        .replace("  - 补偿控制：无", "  - 补偿控制：防火墙和反向代理认证"),
    )

    findings = verifier.verify_decision(path)

    assert not any(item.check == "risk-acceptance" for item in findings)


def test_final_accepted_risk_requires_expiry_and_recheck(tmp_path):
    path = _decision_file(
        tmp_path,
        FILLED_DECISION.replace("- 被临时接受的风险：无", "- 被临时接受的风险：公开 OpenClaw 面板").replace("- 风险接受到期时间：无", "- 风险接受到期时间："),
    )

    findings = verifier.verify_decision(path)

    assert any(item.check == "risk-acceptance" and "风险接受到期时间" in item.message for item in findings)


def test_secret_like_values_fail_without_printing_value(tmp_path, capsys):
    secret_value = "opaque-cookie-secret-value-123456"
    path = _decision_file(tmp_path, FILLED_DECISION.replace("- 是否使用真实 cookie/token：否", f"- 是否使用真实 cookie/token：cookie：{secret_value}"))

    exit_code = verifier.main(["--decision", str(path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "secret-like value" in output
    assert secret_value not in output


def test_json_output_is_sanitized(tmp_path, capsys):
    secret_value = "Bearer opaque-token-value-123456"
    path = _decision_file(tmp_path, FILLED_DECISION.replace("not approved", secret_value, 1))

    exit_code = verifier.main(["--decision", str(path), "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 1
    assert payload["findings"][0]["check"] == "secret-redaction"
    assert secret_value not in output
