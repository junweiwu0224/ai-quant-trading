# 全量数据展示健康检查实施计划

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行此计划。步骤使用复选框 (`- [ ]`) 追踪。

**目标：** 为 Junwei Quant 建立一套可重复运行的全量数据展示检查，覆盖 API 响应、前端渲染风险、真实浏览器页面和最终诊断报告。

**架构：** 第一层用 FastAPI `TestClient` 扫描只读 API，发现非有限数值、`NaN`、`undefined`、`[object Object]` 和接口错误。第二层静态扫描前端渲染代码，定位容易产生异常显示的格式化写法。第三层用 Playwright 打开真实 Dashboard 页面，记录控制台错误、网络失败、可见异常文本和关键区域占位情况，最后把结果落到 `test-results/data-display-audit/`。

**技术栈：** Python 3.11、FastAPI `TestClient`、pytest、Playwright、Node/npm、PowerShell。

---

## 范围

本计划只做全量检查与证据采集，不直接修复业务数据逻辑。检查过程只访问只读 GET 端点和已有页面，不调用下单、撤单、同步、导入、删除、注册、登录以外的写接口。浏览器侧会创建测试账号或登录测试账号，和现有 E2E 测试保持一致。

第一轮输出是：

- `test-results/data-display-audit/api-report.json`
- `test-results/data-display-audit/frontend-static-report.json`
- `test-results/data-display-audit/browser-report.json`
- `test-results/data-display-audit/summary.md`

如果报告显示大量同类问题，再另起修复计划，按“格式化工具缺失、API schema 不稳定、数据源/缓存陈旧、页面生命周期错乱”等根因分批处理。

## 文件结构

- 新建 `scripts/dashboard_data_health.py`：FastAPI 只读 API 健康扫描 CLI，负责请求端点、递归检查 JSON、输出 API 报告。
- 新建 `scripts/frontend_data_render_audit.py`：静态扫描前端 JS，找出高风险渲染模式，输出静态风险报告。
- 新建 `scripts/run_data_display_audit.ps1`：Windows 一键运行入口，串联 API 扫描、静态扫描、可选浏览器巡检和汇总。
- 新建 `tests/test_dashboard_data_health.py`：单测 API 扫描器的异常识别和路由 manifest。
- 新建 `tests/test_frontend_data_render_audit.py`：单测前端静态扫描器的风险分类。
- 新建 `tests/e2e/data-display-health.spec.cjs`：Playwright 页面巡检，记录可见异常、控制台错误和网络失败。
- 修改 `package.json`：增加 `e2e:data-health` 脚本。

---

### 任务 1: API 数据健康扫描器

**文件：**
- 新建: `scripts/dashboard_data_health.py`
- 新建: `tests/test_dashboard_data_health.py`

- [ ] **步骤 1：编写失败测试**

写入 `tests/test_dashboard_data_health.py`：

```python
import json

from scripts.dashboard_data_health import (
    HARD_BAD_STRINGS,
    SAFE_GET_PATHS,
    AuditFinding,
    find_json_anomalies,
    normalize_path_for_name,
)


def test_normalize_path_for_name_makes_stable_filename_piece():
    assert normalize_path_for_name("/api/stock/kline/600519?period=daily&count=30") == "api_stock_kline_600519_period_daily_count_30"


def test_find_json_anomalies_flags_hard_bad_strings_and_nonfinite_numbers():
    payload = {
        "quote": {
            "price": float("nan"),
            "change": "undefined",
            "label": "[object Object]",
            "valid_placeholder": "--",
        },
        "items": [{"ratio": float("inf")}],
    }

    findings = find_json_anomalies(payload)
    rendered = {(item.path, item.kind, item.value) for item in findings}

    assert ("$.quote.price", "non_finite_number", "nan") in rendered
    assert ("$.quote.change", "bad_display_string", "undefined") in rendered
    assert ("$.quote.label", "bad_display_string", "[object Object]") in rendered
    assert ("$.items[0].ratio", "non_finite_number", "inf") in rendered
    assert not any(item.path == "$.quote.valid_placeholder" for item in findings)


def test_audit_finding_is_json_serializable():
    finding = AuditFinding(path="$.x", kind="bad_display_string", value="nan", severity="hard")

    assert json.loads(json.dumps(finding.to_dict())) == {
        "path": "$.x",
        "kind": "bad_display_string",
        "value": "nan",
        "severity": "hard",
    }


def test_safe_get_paths_cover_user_selected_data_areas():
    expected = {
        "/api/stock/detail/600519",
        "/api/stock/kline/600519?period=daily&count=30",
        "/api/stock/market/indices",
        "/api/market/radar",
        "/api/portfolio/snapshot",
        "/api/paper/status",
        "/api/backtest/strategies",
        "/api/alpha/model-status",
        "/api/watchlist",
        "/api/datahub/health",
    }

    assert expected.issubset(set(SAFE_GET_PATHS))
    assert all("{" not in path and "}" not in path for path in SAFE_GET_PATHS)
    assert all(not path.startswith("/api/account/") for path in SAFE_GET_PATHS)
```

- [ ] **步骤 2：运行测试确认失败**

运行:

```powershell
python -m pytest tests/test_dashboard_data_health.py -q
```

预期: 失败，并提示 `ModuleNotFoundError: No module named 'scripts.dashboard_data_health'`。

- [ ] **步骤 3：编写 API 扫描器最小实现**

写入 `scripts/dashboard_data_health.py`：

```python
"""Dashboard read-only API data display health audit."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("APP_ENV", "test")

HARD_BAD_STRINGS = frozenset({"nan", "undefined", "inf", "infinity", "-inf", "-infinity", "[object object]"})
SOFT_PLACEHOLDER_STRINGS = frozenset({"--", "-", ""})

SAFE_GET_PATHS = [
    "/api/system/status",
    "/api/system/strategies",
    "/api/system/risk/rules",
    "/api/backtest/strategies",
    "/api/backtest/stocks",
    "/api/portfolio/snapshot",
    "/api/portfolio/trades",
    "/api/portfolio/risk",
    "/api/paper/status",
    "/api/paper/orders",
    "/api/paper/positions",
    "/api/paper/performance",
    "/api/stock/search?q=600519&limit=5",
    "/api/stock/detail/600519",
    "/api/stock/kline/600519?period=daily&count=30",
    "/api/stock/market/indices",
    "/api/stock/market/stats",
    "/api/market/radar",
    "/api/market/sectors",
    "/api/market/heatmap",
    "/api/market/northbound",
    "/api/valuation/health",
    "/api/datahub/health",
    "/api/datahub/decision-matrix?scope=codes&codes=600519&limit=3&fast=true",
    "/api/alerts/rules",
    "/api/conditional-orders/rules",
    "/api/alpha/model-status",
    "/api/alpha/formula/catalog",
    "/api/watchlist",
    "/api/qlib/health",
]


@dataclass(frozen=True)
class AuditFinding:
    path: str
    kind: str
    value: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "kind": self.kind,
            "value": self.value,
            "severity": self.severity,
        }


def normalize_path_for_name(path: str) -> str:
    cleaned = path.strip().strip("/")
    cleaned = cleaned.replace("?", "_").replace("&", "_").replace("=", "_")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned)
    return cleaned.strip("_") or "root"


def _string_finding(value: str, path: str) -> AuditFinding | None:
    normalized = value.strip().lower()
    if normalized in HARD_BAD_STRINGS:
        return AuditFinding(path=path, kind="bad_display_string", value=value, severity="hard")
    if "nan%" in normalized or "undefined%" in normalized or "infinity%" in normalized:
        return AuditFinding(path=path, kind="bad_display_string", value=value, severity="hard")
    if normalized in SOFT_PLACEHOLDER_STRINGS:
        return None
    return None


def find_json_anomalies(value: Any, path: str = "$") -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    if isinstance(value, float):
        if not math.isfinite(value):
            findings.append(AuditFinding(path=path, kind="non_finite_number", value=str(value), severity="hard"))
        return findings
    if isinstance(value, str):
        finding = _string_finding(value, path)
        return [finding] if finding else []
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = str(key).replace('"', '\\"')
            next_path = f'{path}.{child_key}' if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", child_key) else f'{path}["{child_key}"]'
            findings.extend(find_json_anomalies(child, next_path))
        return findings
    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_json_anomalies(child, f"{path}[{index}]"))
        return findings
    return findings


def _install_test_account_override(app) -> None:
    try:
        from dashboard.session import current_account
    except Exception:
        return

    app.dependency_overrides[current_account] = lambda: {
        "id": "audit-user",
        "username": "audit-user",
        "workspace": {"id": "audit-workspace", "name": "Audit Workspace"},
    }


def run_api_audit(paths: list[str] | None = None) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from dashboard.app import app

    _install_test_account_override(app)
    client = TestClient(app)
    selected_paths = paths or SAFE_GET_PATHS
    endpoints: list[dict[str, Any]] = []

    for path in selected_paths:
        record: dict[str, Any] = {
            "path": path,
            "name": normalize_path_for_name(path),
            "status_code": None,
            "ok": False,
            "json": False,
            "findings": [],
            "error": "",
        }
        try:
            response = client.get(path)
            record["status_code"] = response.status_code
            record["ok"] = 200 <= response.status_code < 300
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                payload = response.json()
                record["json"] = True
                record["findings"] = [item.to_dict() for item in find_json_anomalies(payload)]
            else:
                record["error"] = f"non-json response: {content_type}"
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        endpoints.append(record)

    hard_findings = sum(
        1
        for endpoint in endpoints
        for finding in endpoint["findings"]
        if finding.get("severity") == "hard"
    )
    failed_endpoints = [endpoint for endpoint in endpoints if not endpoint["ok"] or endpoint["error"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "api",
        "total_endpoints": len(endpoints),
        "failed_endpoint_count": len(failed_endpoints),
        "hard_finding_count": hard_findings,
        "endpoints": endpoints,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit read-only dashboard API data display health.")
    parser.add_argument("--output", default="test-results/data-display-audit/api-report.json")
    parser.add_argument("--path", action="append", dest="paths", help="Limit scan to one path; repeatable.")
    parser.add_argument("--fail-on-hard", action="store_true", help="Exit 1 when hard findings or endpoint failures exist.")
    args = parser.parse_args(argv)

    report = run_api_audit(args.paths)
    write_report(report, Path(args.output))
    print(f"Wrote API data health report: {args.output}")
    print(f"Endpoints: {report['total_endpoints']}, failed: {report['failed_endpoint_count']}, hard findings: {report['hard_finding_count']}")
    if args.fail_on_hard and (report["failed_endpoint_count"] or report["hard_finding_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **步骤 4：运行测试确认通过**

运行:

```powershell
python -m pytest tests/test_dashboard_data_health.py -q
```

预期: 4 个测试通过。

- [ ] **步骤 5：运行一次 API 审计基线**

运行:

```powershell
python scripts/dashboard_data_health.py --output test-results/data-display-audit/api-report.json
```

预期: 命令退出码为 0，并输出类似:

```text
Wrote API data health report: test-results/data-display-audit/api-report.json
Endpoints: 30, failed: N, hard findings: M
```

- [ ] **步骤 6：提交**

```powershell
git add scripts/dashboard_data_health.py tests/test_dashboard_data_health.py
git commit -m "test: add dashboard API data health audit"
```

---

### 任务 2: 前端渲染静态风险扫描器

**文件：**
- 新建: `scripts/frontend_data_render_audit.py`
- 新建: `tests/test_frontend_data_render_audit.py`

- [ ] **步骤 1：编写失败测试**

写入 `tests/test_frontend_data_render_audit.py`：

```python
from pathlib import Path

from scripts.frontend_data_render_audit import RenderRisk, scan_js_text, scan_static_tree


def test_scan_js_text_flags_raw_tofixed_and_innerhtml():
    text = """
    priceCell.textContent = '¥' + q.price.toFixed(2);
    panel.innerHTML = `<td>${payload.value}</td>`;
    safe.textContent = DisplayFormat.money(payload.value);
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))
    keys = {(risk.kind, risk.severity) for risk in risks}

    assert ("raw_to_fixed", "high") in keys
    assert ("dynamic_inner_html", "medium") in keys
    assert all(isinstance(risk, RenderRisk) for risk in risks)


def test_scan_js_text_ignores_comments_and_empty_lines():
    text = """
    // value.toFixed(2)

    const value = DisplayFormat.percent(row.ratio);
    """

    assert scan_js_text(text, Path("dashboard/static/sample.js")) == []


def test_scan_static_tree_returns_sorted_risks(tmp_path):
    first = tmp_path / "b.js"
    second = tmp_path / "a.js"
    first.write_text("x.innerHTML = `<span>${value}</span>`;", encoding="utf-8")
    second.write_text("y.textContent = z.toFixed(2);", encoding="utf-8")

    risks = scan_static_tree(tmp_path)

    assert [risk.file for risk in risks] == ["a.js", "b.js"]
```

- [ ] **步骤 2：运行测试确认失败**

运行:

```powershell
python -m pytest tests/test_frontend_data_render_audit.py -q
```

预期: 失败，并提示 `ModuleNotFoundError: No module named 'scripts.frontend_data_render_audit'`。

- [ ] **步骤 3：编写静态扫描器最小实现**

写入 `scripts/frontend_data_render_audit.py`：

```python
"""Static risk scan for dashboard frontend data rendering."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RenderRisk:
    file: str
    line: int
    kind: str
    severity: str
    snippet: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "file": self.file,
            "line": self.line,
            "kind": self.kind,
            "severity": self.severity,
            "snippet": self.snippet,
        }


RISK_PATTERNS = [
    ("raw_to_fixed", "high", re.compile(r"\.toFixed\s*\(")),
    ("raw_number_constructor", "medium", re.compile(r"\bNumber\s*\(")),
    ("fallback_or_placeholder", "medium", re.compile(r"\|\|\s*['\"]--['\"]")),
    ("dynamic_inner_html", "medium", re.compile(r"\.innerHTML\s*=\s*`.*\$\{")),
    ("direct_nan_check", "low", re.compile(r"\bisNaN\s*\(")),
]


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("//") or stripped.startswith("*")


def scan_js_text(text: str, file_path: Path) -> list[RenderRisk]:
    risks: list[RenderRisk] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if _is_comment_or_blank(line):
            continue
        for kind, severity, pattern in RISK_PATTERNS:
            if pattern.search(line):
                risks.append(RenderRisk(
                    file=file_path.as_posix(),
                    line=index,
                    kind=kind,
                    severity=severity,
                    snippet=line.strip()[:240],
                ))
    return risks


def scan_static_tree(root: Path) -> list[RenderRisk]:
    risks: list[RenderRisk] = []
    for path in sorted(root.rglob("*.js")):
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        risks.extend(scan_js_text(text, path.relative_to(root)))
    return sorted(risks, key=lambda risk: (risk.file, risk.line, risk.kind))


def build_report(root: Path) -> dict:
    risks = scan_static_tree(root)
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for risk in risks:
        by_kind[risk.kind] = by_kind.get(risk.kind, 0) + 1
        by_severity[risk.severity] = by_severity.get(risk.severity, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "frontend_static",
        "root": root.as_posix(),
        "risk_count": len(risks),
        "by_kind": by_kind,
        "by_severity": by_severity,
        "risks": [risk.to_dict() for risk in risks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit frontend rendering risk patterns.")
    parser.add_argument("--root", default="dashboard/static")
    parser.add_argument("--output", default="test-results/data-display-audit/frontend-static-report.json")
    args = parser.parse_args(argv)

    report = build_report(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote frontend static data render report: {args.output}")
    print(f"Risks: {report['risk_count']}, by severity: {report['by_severity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **步骤 4：运行测试确认通过**

运行:

```powershell
python -m pytest tests/test_frontend_data_render_audit.py -q
```

预期: 3 个测试通过。

- [ ] **步骤 5：运行一次静态扫描基线**

运行:

```powershell
python scripts/frontend_data_render_audit.py --output test-results/data-display-audit/frontend-static-report.json
```

预期: 命令退出码为 0，并输出风险总数和 severity 汇总。

- [ ] **步骤 6：提交**

```powershell
git add scripts/frontend_data_render_audit.py tests/test_frontend_data_render_audit.py
git commit -m "test: add frontend data rendering risk audit"
```

---

### 任务 3: 真实浏览器数据展示巡检

**文件：**
- 新建: `tests/e2e/data-display-health.spec.cjs`
- 修改: `package.json`

- [ ] **步骤 1：编写 Playwright 巡检 spec**

写入 `tests/e2e/data-display-health.spec.cjs`：

```javascript
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const TEST_PASSWORD = 'Playwright123!';
const TEST_INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const REPORT_DIR = path.join(process.cwd(), 'test-results', 'data-display-audit');
const REPORT_PATH = path.join(REPORT_DIR, 'browser-report.json');
const HARD_BAD_TEXT = /\b(?:NaN|undefined|Infinity|\[object Object\]|Invalid Date)\b/i;

function getCookieDomain() {
    try {
        const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001';
        return new URL(baseUrl).hostname || '127.0.0.1';
    } catch {
        return '127.0.0.1';
    }
}

async function ensureAuthenticated(page, usernameSuffix = Date.now()) {
    const username = `audit_${usernameSuffix}`.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 32);
    const cookieDomain = getCookieDomain();
    const payload = {
        username,
        password: TEST_PASSWORD,
        invite_code: TEST_INVITE_CODE,
        display_name: username,
        email: null,
    };
    const auth = await page.request.post('/api/account/register', { data: payload });
    if (!auth.ok()) {
        const login = await page.request.post('/api/account/login', {
            data: { username: 'pw_shell', password: TEST_PASSWORD },
        });
        expect(login.ok()).toBeTruthy();
        const sessionCookie = login.headers()['set-cookie'] || '';
        await page.context().addCookies([{
            name: 'quant_session',
            value: sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '',
            domain: cookieDomain,
            path: '/',
            httpOnly: true,
            sameSite: 'Lax',
        }]);
        return username;
    }
    const sessionCookie = auth.headers()['set-cookie'] || '';
    await page.context().addCookies([{
        name: 'quant_session',
        value: sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '',
        domain: cookieDomain,
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
    return username;
}

async function waitForAppReady(page) {
    await expect(page.locator('body')).toBeVisible();
    await page.waitForFunction(() => Boolean(window.App && window.APIClient && window.BusinessAdapter), null, {
        timeout: 20_000,
    });
}

async function collectPanelSnapshot(page, tabName) {
    await page.evaluate(async (name) => {
        if (window.App && typeof window.App.switchTab === 'function') {
            await window.App.switchTab(name);
        }
    }, tabName);
    await page.waitForTimeout(1000);
    const result = await page.evaluate((name) => {
        const panel = document.getElementById(`tab-${name}`);
        const text = panel ? panel.innerText : '';
        const hardMatches = text.match(/\b(?:NaN|undefined|Infinity|\[object Object\]|Invalid Date)\b/gi) || [];
        const placeholderMatches = text.match(/--/g) || [];
        return {
            tab: name,
            visible: Boolean(panel && !panel.hidden && getComputedStyle(panel).display !== 'none'),
            textLength: text.length,
            hardMatches: [...new Set(hardMatches)].slice(0, 20),
            placeholderCount: placeholderMatches.length,
        };
    }, tabName);
    return result;
}

test('dashboard data display health audit', async ({ page }) => {
    const consoleErrors = [];
    const failedRequests = [];
    page.on('console', (message) => {
        if (['error', 'warning'].includes(message.type())) {
            consoleErrors.push({ type: message.type(), text: message.text() });
        }
    });
    page.on('requestfailed', (request) => {
        failedRequests.push({
            url: request.url(),
            method: request.method(),
            failure: request.failure() ? request.failure().errorText : '',
        });
    });

    await ensureAuthenticated(page, 'data_display');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    const tabs = ['overview', 'intelligence', 'research', 'trade', 'paper', 'strategy-admin'];
    const panels = [];
    for (const tabName of tabs) {
        panels.push(await collectPanelSnapshot(page, tabName));
    }

    await page.evaluate(async () => {
        if (window.App && typeof window.App.openStockDetail === 'function') {
            await window.App.openStockDetail('600519', { source: 'playwright:data-display-health', preferDirectOpen: true });
        }
    });
    await page.waitForTimeout(1500);
    const stockText = await page.locator('#tab-stock').innerText({ timeout: 10_000 }).catch(() => '');
    const stockHardMatches = stockText.match(HARD_BAD_TEXT) || [];

    const report = {
        generatedAt: new Date().toISOString(),
        url: page.url(),
        consoleErrors,
        failedRequests,
        panels,
        stockDetail: {
            textLength: stockText.length,
            hardMatches: [...new Set(stockHardMatches)].slice(0, 20),
            placeholderCount: (stockText.match(/--/g) || []).length,
        },
    };

    fs.mkdirSync(REPORT_DIR, { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), 'utf8');

    const hardPanelMatches = panels.flatMap((panel) => panel.hardMatches.map((match) => `${panel.tab}:${match}`));
    expect(hardPanelMatches, JSON.stringify(report, null, 2)).toEqual([]);
    expect(report.stockDetail.hardMatches, JSON.stringify(report, null, 2)).toEqual([]);
});
```

- [ ] **步骤 2：修改 `package.json` 脚本**

把 `scripts` 改成：

```json
{
  "test": "echo \"Error: no test specified\" && exit 1",
  "e2e": "playwright test --config=playwright.config.cjs tests/e2e/v2-smoke.spec.cjs tests/e2e/openclaw.spec.cjs",
  "e2e:data-health": "playwright test --config=playwright.config.cjs tests/e2e/data-display-health.spec.cjs",
  "e2e:docker": "bash scripts/e2e.sh"
}
```

- [ ] **步骤 3：运行 Playwright 巡检确认能生成报告**

先启动 Dashboard:

```powershell
python scripts/run_dashboard.py --host 127.0.0.1 --port 8001 --no-qlib
```

在另一个终端运行:

```powershell
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:8001'
npm run e2e:data-health
```

预期: 若页面存在硬异常文本，测试失败但仍生成 `test-results/data-display-audit/browser-report.json`；若没有硬异常文本，测试通过并生成报告。

- [ ] **步骤 4：提交**

```powershell
git add package.json tests/e2e/data-display-health.spec.cjs
git commit -m "test: add browser data display audit"
```

---

### 任务 4: 一键全量检查入口与汇总报告

**文件：**
- 新建: `scripts/run_data_display_audit.ps1`

- [ ] **步骤 1：编写一键运行脚本**

写入 `scripts/run_data_display_audit.ps1`：

```powershell
param(
  [int]$Port = 8001,
  [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ReportDir = Join-Path $Root "test-results\data-display-audit"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

Push-Location $Root
try {
  python scripts/dashboard_data_health.py --output (Join-Path $ReportDir "api-report.json")
  python scripts/frontend_data_render_audit.py --output (Join-Path $ReportDir "frontend-static-report.json")

  $server = $null
  if (-not $SkipBrowser) {
    $serverLog = Join-Path $ReportDir "dashboard-server.log"
    $serverErr = Join-Path $ReportDir "dashboard-server.err.log"
    $server = Start-Process -FilePath "python" `
      -ArgumentList @("scripts/run_dashboard.py", "--host", "127.0.0.1", "--port", "$Port", "--no-qlib") `
      -WorkingDirectory $Root `
      -RedirectStandardOutput $serverLog `
      -RedirectStandardError $serverErr `
      -WindowStyle Hidden `
      -PassThru

    $ready = $false
    for ($i = 0; $i -lt 80; $i++) {
      try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
          $ready = $true
          break
        }
      } catch {
        Start-Sleep -Milliseconds 500
      }
    }
    if (-not $ready) {
      throw "Dashboard did not become ready on http://127.0.0.1:$Port/"
    }

    $env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:$Port"
    npm run e2e:data-health
  }

  $api = Get-Content -LiteralPath (Join-Path $ReportDir "api-report.json") -Raw | ConvertFrom-Json
  $static = Get-Content -LiteralPath (Join-Path $ReportDir "frontend-static-report.json") -Raw | ConvertFrom-Json
  $browserPath = Join-Path $ReportDir "browser-report.json"
  $browser = if (Test-Path -LiteralPath $browserPath) { Get-Content -LiteralPath $browserPath -Raw | ConvertFrom-Json } else { $null }

  $lines = @()
  $lines += "# 数据展示全量检查摘要"
  $lines += ""
  $lines += "- 生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  $lines += "- API 扫描端点：$($api.total_endpoints)"
  $lines += "- API 失败端点：$($api.failed_endpoint_count)"
  $lines += "- API 硬异常：$($api.hard_finding_count)"
  $lines += "- 前端静态风险：$($static.risk_count)"
  if ($browser) {
    $consoleCount = @($browser.consoleErrors).Count
    $requestCount = @($browser.failedRequests).Count
    $panelHardCount = @($browser.panels | ForEach-Object { $_.hardMatches } | Where-Object { $_ }).Count
    $stockHardCount = @($browser.stockDetail.hardMatches).Count
    $lines += "- 浏览器 console 错误/警告：$consoleCount"
    $lines += "- 浏览器网络失败：$requestCount"
    $lines += "- 页面硬异常文本：$($panelHardCount + $stockHardCount)"
  } else {
    $lines += "- 浏览器巡检：已跳过"
  }
  $lines += ""
  $lines += "## 报告文件"
  $lines += "- api-report.json"
  $lines += "- frontend-static-report.json"
  if ($browser) { $lines += "- browser-report.json" }

  $summaryPath = Join-Path $ReportDir "summary.md"
  $lines | Set-Content -LiteralPath $summaryPath -Encoding UTF8
  Write-Host "Data display audit summary written to $summaryPath"
} finally {
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force
  }
  Pop-Location
}
```

- [ ] **步骤 2：运行非浏览器检查确认脚本可用**

运行:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_data_display_audit.ps1 -SkipBrowser
```

预期: 生成 `api-report.json`、`frontend-static-report.json` 和 `summary.md`。

- [ ] **步骤 3：运行全量检查**

运行:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_data_display_audit.ps1 -Port 8001
```

预期: Dashboard 被自动启动，Playwright 巡检运行，结束后生成四个报告文件。若浏览器测试失败，读取 `browser-report.json` 和 Playwright trace，而不是直接修代码。

- [ ] **步骤 4：提交**

```powershell
git add scripts/run_data_display_audit.ps1
git commit -m "chore: add full data display audit runner"
```

---

### 任务 5: 执行基线检查并归类根因

**文件：**
- 生成: `test-results/data-display-audit/api-report.json`
- 生成: `test-results/data-display-audit/frontend-static-report.json`
- 生成: `test-results/data-display-audit/browser-report.json`
- 生成: `test-results/data-display-audit/summary.md`

- [ ] **步骤 1：运行全量检查**

运行:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_data_display_audit.ps1 -Port 8001
```

预期: 生成 `test-results/data-display-audit/summary.md`。如果命令失败，仍检查已生成的 JSON 报告和 `dashboard-server.err.log`。

- [ ] **步骤 2：读取 API 报告并列出失败端点**

运行:

```powershell
$report = Get-Content test-results/data-display-audit/api-report.json -Raw | ConvertFrom-Json
$report.endpoints | Where-Object { -not $_.ok -or $_.error -or @($_.findings).Count -gt 0 } | Select-Object path,status_code,error,findings | Format-List
```

预期: 看到所有 API 层异常端点、状态码、错误信息和 hard finding。

- [ ] **步骤 3：读取前端静态风险 Top 30**

运行:

```powershell
$static = Get-Content test-results/data-display-audit/frontend-static-report.json -Raw | ConvertFrom-Json
$static.risks | Sort-Object severity,file,line | Select-Object -First 30 file,line,kind,severity,snippet | Format-Table -AutoSize
```

预期: 看到最集中的 `raw_to_fixed`、`dynamic_inner_html` 和 `fallback_or_placeholder` 文件。

- [ ] **步骤 4：读取浏览器异常**

运行:

```powershell
$browser = Get-Content test-results/data-display-audit/browser-report.json -Raw | ConvertFrom-Json
$browser.consoleErrors | Select-Object -First 30 | Format-List
$browser.failedRequests | Select-Object -First 30 | Format-List
$browser.panels | Select-Object tab,visible,textLength,placeholderCount,hardMatches | Format-Table -AutoSize
$browser.stockDetail | Format-List
```

预期: 得到真实页面层面的异常文本、控制台错误、网络失败和各 tab 占位数量。

- [ ] **步骤 5：写根因分类备注**

在终端整理为四类，不写入业务代码：

```text
API 合同问题:
- <端点>: <异常值或错误>

前端格式化问题:
- <文件:行>: <风险模式>

浏览器生命周期/加载问题:
- <tab>: <console 或 network 证据>

外部数据源/缓存问题:
- <端点或模块>: <失败信息>
```

预期: 下一份修复计划能从证据最多的一类开始，而不是同时修改所有页面。

---

### 任务 6: 最终验证命令

**文件：**
- 不新增代码文件。

- [ ] **步骤 1：运行新增 Python 单测**

运行:

```powershell
python -m pytest tests/test_dashboard_data_health.py tests/test_frontend_data_render_audit.py -q
```

预期: 全部通过。

- [ ] **步骤 2：运行现有 Dashboard 后端测试**

运行:

```powershell
python -m pytest tests/test_dashboard.py tests/test_data.py -q
```

预期: 全部通过；若现有测试失败，记录失败用例和堆栈，不把失败掩盖进审计工具。

- [ ] **步骤 3：运行全量审计**

运行:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_data_display_audit.ps1 -Port 8001
```

预期: 生成完整审计报告。Playwright 可因真实页面硬异常而失败，但必须留下 `browser-report.json` 和 Playwright trace。

- [ ] **步骤 4：提交最终计划内变更**

如果前面按任务逐步提交，本步骤只检查状态：

```powershell
git status --short
```

预期: 只剩 `test-results/` 下生成物和用户原本未跟踪/未提交文件；不要提交 `test-results/`。

---

## 自我审查

- 规范覆盖：用户全选的 A-F 范围被拆成 API 层、前端静态层、浏览器真实页面层和汇总报告层，覆盖实时行情、首页概览、持仓模拟盘、研发回测、个股详情和全局格式问题。
- 占位符扫描：计划没有使用 `TBD`、`TODO`、`implement later` 或空泛的“添加适当处理”。
- 类型一致性：`AuditFinding`、`RenderRisk`、`SAFE_GET_PATHS`、`find_json_anomalies`、`scan_js_text`、`scan_static_tree` 在测试和实现中命名一致。
- 安全边界：检查只访问只读端点，写操作限制在测试账号创建和本地报告文件生成。
