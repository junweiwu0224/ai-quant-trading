# OpenClaw Integration Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the OpenClaw integration so invite-based auth, per-user workspaces, service startup, tool bridging, memory/report/skill storage, and the OpenClaw UI all work end-to-end.

**Architecture:** Keep the quant platform as the source of truth for users, permissions, audit logs, watchlists, paper trading, reports, and memories. Treat OpenClaw as a native external service with a managed local wrapper: the dashboard maps each user to one OpenClaw workspace, exposes only approved system tools, and records every important action. The UI stays split into focused shell/workbench modules so the OpenClaw surface can evolve without re-tangling the main dashboard.

**Tech Stack:** FastAPI, SQLite, Jinja2, Vanilla JS, Playwright, pytest, Node/npm, the bundled `openclaw-2026.5.20.tgz` package, and the existing dashboard/static split.

---

## File Map

- `dashboard/account_store.py`: invite codes, sessions, workspaces, permissions, audit logs, memories, reports, and skill records.
- `dashboard/auth.py` and `dashboard/session.py`: API key/session helpers and request gating.
- `dashboard/routers/account.py`: invite registration, login/logout, workspace settings, permissions, audit, and invite admin APIs.
- `dashboard/openclaw_service.py`: managed OpenClaw CLI install/start/stop lifecycle and generated config.
- `dashboard/openclaw_gateway.py`: HTTP adapter for the external OpenClaw service.
- `dashboard/openclaw_tools.py`: whitelisted system tools, confirmation tokens, bridge invoke path, audit recording, and research-memory auto capture.
- `dashboard/routers/openclaw.py`: OpenClaw status, setup, chat, bridge, tools, memories, reports, and skills APIs.
- `dashboard/app.py`: middleware order, route registration, and service startup/shutdown.
- `dashboard/templates/index.html`: tab hosts for the OpenClaw workspace and settings surfaces.
- `dashboard/templates/partials/scripts.html`: versioned script ordering for the shell, OpenClaw workbench, and service worker.
- `dashboard/static/app.js`: bundle manifest and lazy-load wiring for the OpenClaw workbench.
- `dashboard/static/app-bootstrap.js`: auth bootstrap and authenticated session startup.
- `dashboard/static/core/app-shell.js`: tab normalization, app-wide shell behavior, and OpenClaw tab selection.
- `dashboard/static/app-ui-shell.js`: avatar menu, auth modal, and workspace shortcuts.
- `dashboard/static/openclaw-workbench.js`: OpenClaw workspace page and settings page rendering/binding.
- `dashboard/static/sw.js`: cache manifest and offline behavior for the shell assets.
- `dashboard/static/style.css`: OpenClaw layout, auth shell, and menu styling.
- `.env.example`, `docker-compose.yml`, `README.md`, `docs/ARCHITECTURE.md`: runtime flags and operator guidance.
- `tests/test_session_gate.py`, `tests/test_openclaw_tools.py`, `tests/test_openclaw_account.py`, `tests/test_openclaw_service.py`, `tests/e2e/openclaw.spec.cjs`: auth, tool, service, and browser regression coverage.

### Task 1: Finish Invite, Session, and Workspace Bootstrap

**Files:**
- Modify: `dashboard/account_store.py`
- Modify: `dashboard/auth.py`
- Modify: `dashboard/session.py`
- Modify: `dashboard/routers/account.py`
- Modify: `dashboard/app.py`
- Test: `tests/test_session_gate.py`
- Create: `tests/test_openclaw_account.py`

- [ ] **Step 1: Write the failing test**

```python
def test_register_bootstraps_workspace_and_audit(client):
    payload = {
        "username": "alice",
        "password": "Playwright123!",
        "invite_code": "LOCAL1",
        "display_name": "Alice",
        "email": None,
    }
    resp = client.post("/api/account/register", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "alice"
    assert body["workspace"]["openclaw_workspace_id"].startswith("ocw_")
    assert body["permissions"]["chat"] is True
    assert "quant_session=" in resp.headers["set-cookie"]
```

- [ ] **Step 2: Run the test to verify the current behavior is still incomplete**

Run: `pytest tests/test_session_gate.py tests/test_openclaw_account.py -q`

Expected: one or more assertions fail until the invite/session bootstrap path, workspace creation, or audit logging is fully aligned.

- [ ] **Step 3: Implement the minimal account and session changes**

```python
# dashboard/account_store.py
def create_user(username: str, password: str, invite_code: str, display_name: str | None = None, email: str | None = None) -> dict:
    code = normalize_invite_code(invite_code)
    conn = self._conn()
    conn.execute("BEGIN IMMEDIATE")
    invite = conn.execute("SELECT * FROM invite_codes WHERE code = ?", (code,)).fetchone()
    if not invite:
        raise ValueError("邀请码无效")
    if invite["disabled"]:
        raise ValueError("邀请码已停用")
    if invite["used_count"] >= invite["max_uses"]:
        raise ValueError("邀请码已被用完")
    # create the user row, workspace row, invite usage row, and auth.register audit row in the same transaction

# dashboard/session.py
async def current_account(account: dict | None = Depends(optional_account)) -> dict:
    if not account:
        raise HTTPException(status_code=401, detail="请先登录")
    return account

# dashboard/routers/account.py
@router.post("/register")
async def register(req: RegisterRequest, request: Request, response: Response):
    account = account_store.create_user(
        username=req.username,
        password=req.password,
        invite_code=req.invite_code,
        display_name=req.display_name,
        email=req.email,
    )
    token, session_meta = account_store.create_session(
        account["user"]["id"],
        user_agent=request.headers.get("user-agent", ""),
        ip_address=client_ip(request),
    )
    set_session_cookie(response, token, max_age=14 * 24 * 3600)
    return {"success": True, "authenticated": True, **account, "session": session_meta}
```

- [ ] **Step 4: Run the focused tests again**

Run: `pytest tests/test_session_gate.py tests/test_openclaw_account.py -q`

Expected: PASS, with `api/account/me` returning `authenticated: false` before login and the register response issuing a usable `quant_session` cookie.

- [ ] **Step 5: Commit**

```bash
git add dashboard/account_store.py dashboard/auth.py dashboard/session.py dashboard/routers/account.py dashboard/app.py tests/test_session_gate.py tests/test_openclaw_account.py
git commit -m "feat: finish invite and workspace bootstrap"
```

### Task 2: Harden Invite Code Storage and Permission Boundaries

**Files:**
- Modify: `dashboard/account_store.py`
- Modify: `dashboard/routers/account.py`
- Modify: `dashboard/session.py`
- Test: `tests/test_openclaw_account.py`

- [ ] **Step 1: Write the failing test**

```python
def test_invite_codes_store_only_hash_and_remain_lookupable():
    import hashlib

    from dashboard.account_store import account_store, normalize_invite_code
    from utils.db import get_connection

    invite = account_store.create_invite_code(None, code="Ab12cD", max_uses=2, note="bootstrap")
    expected_hash = hashlib.sha256(normalize_invite_code("Ab12cD").encode("utf-8")).hexdigest()

    conn = get_connection(account_store.db_path, readonly=True)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(invite_codes)").fetchall()}
        row = conn.execute("SELECT * FROM invite_codes WHERE code_hash = ?", (expected_hash,)).fetchone()
    finally:
        conn.close()

    assert "code" not in columns
    assert "code_hash" in columns
    assert row["code_hash"] == expected_hash
    assert invite["code"] == "AB12CD"


def test_failed_invite_attempt_is_recorded():
    from dashboard.account_store import account_store

    before = account_store.list_invite_code_usages(limit=10)
    try:
        account_store.create_user("bob", "Password123!", "AAAAAA")
    except ValueError as exc:
        assert "邀请码" in str(exc)

    after = account_store.list_invite_code_usages(limit=10)
    assert len(after) == len(before) + 1
    latest = after[0]
    assert latest["status"] == "failed"
    assert latest["reason"]
```

- [ ] **Step 2: Run the test to verify invite persistence still needs tightening**

Run: `pytest tests/test_openclaw_account.py -q`

Expected: FAIL if invite storage still depends on plaintext lookups or if the stored/public code shape is not stable.

- [ ] **Step 3: Implement the invite-code hardening**

```python
# dashboard/account_store.py
# Add code_hash and code_display to invite_codes, plus status and reason to
# invite_code_usages. Write one migration that hashes existing bootstrap data
# and preserves the LOCAL1 invite.
#
# create_invite_code():
# - normalize the 6-character invite code once
# - store only the hash in invite_codes
# - return the plaintext code once in the API payload for admins to copy
#
# create_user():
# - hash the submitted invite code before lookup
# - reject expired, disabled, or exhausted invites
# - insert one invite_code_usages row for both success and failure
#
# list_invite_code_usages(limit=100):
# - return newest-first rows with status, reason, user_id, code_hash, code_display, and used_at
```

- [ ] **Step 4: Run the invite and permission tests again**

Run: `pytest tests/test_openclaw_account.py tests/test_session_gate.py -q`

Expected: PASS, including 403 coverage for admin-only invite and permission endpoints.

- [ ] **Step 5: Commit**

```bash
git add dashboard/account_store.py dashboard/routers/account.py dashboard/session.py tests/test_openclaw_account.py
git commit -m "feat: harden invite code storage"
```

### Task 3: Finish Managed OpenClaw Service Startup and Gateway Adapter

**Files:**
- Modify: `config/settings.py`
- Modify: `dashboard/openclaw_service.py`
- Modify: `dashboard/openclaw_gateway.py`
- Modify: `dashboard/routers/openclaw.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `tests/test_openclaw_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_openclaw_gateway_headers_include_workspace_and_token():
    from dashboard.openclaw_gateway import OpenClawGateway

    gw = OpenClawGateway("http://127.0.0.1:18789", "secret-token")
    headers = gw._headers("ocw_workspace_123")

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-API-Key"] == "secret-token"
    assert headers["X-OpenClaw-Workspace"] == "ocw_workspace_123"
    assert headers["x-openclaw-session-key"] == "ocw_workspace_123"
```

- [ ] **Step 2: Run the test to verify the adapter contract is still loose**

Run: `pytest tests/test_openclaw_service.py -q`

Expected: FAIL until the adapter and managed-service status surface are stable and consistent with the workspace model.

- [ ] **Step 3: Implement the managed service lifecycle and adapter tightening**

```python
# dashboard/openclaw_service.py
# Keep the managed-service flow split into:
# - _ensure_openclaw_cli(): install the bundled tarball into node_modules when missing
# - _ensure_managed_config(): write data/openclaw/openclaw.json and provider config
# - start(): launch `openclaw gateway run` on loopback and wait for /healthz or /readyz
# - stop()/shutdown(): terminate the managed process cleanly
#
# dashboard/openclaw_gateway.py
# Keep the gateway adapter thin and explicit:
# - _headers(workspace_id): include bearer token, X-API-Key, and workspace-scoped headers
# - health(): probe /readyz, /healthz, /v1/models, then /
# - list_native_tools(): probe /tools, /api/tools, and /v1/tools in order
# - invoke_native_tool(): probe /tools/invoke, /api/tools/invoke, and /v1/tools/invoke
```

- [ ] **Step 4: Run the service tests again**

Run: `pytest tests/test_openclaw_service.py -q`

Expected: PASS, and the service status should clearly distinguish `managed`, `external`, `running`, `starting`, and `failed`.

- [ ] **Step 5: Commit**

```bash
git add config/settings.py dashboard/openclaw_service.py dashboard/openclaw_gateway.py dashboard/routers/openclaw.py docker-compose.yml .env.example tests/test_openclaw_service.py
git commit -m "feat: harden openclaw service integration"
```

### Task 4: Close Tool Bridging, Memories, Reports, and Skills

**Files:**
- Modify: `dashboard/openclaw_tools.py`
- Modify: `dashboard/routers/openclaw.py`
- Modify: `dashboard/account_store.py`
- Modify: `dashboard/static/openclaw-workbench.js`
- Test: `tests/test_openclaw_tools.py`
- Create: `tests/test_openclaw_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio

from dashboard import openclaw_tools


def test_openclaw_tool_dispatch_records_memory_and_audit(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"write_watchlist": True, "read_portfolio": True, "manage_skills": True},
    }
    created = []

    monkeypatch.setattr(openclaw_tools.storage, "add_to_watchlist", lambda code, workspace_id: True)
    monkeypatch.setattr(openclaw_tools.account_store, "record_audit", lambda *args, **kwargs: {"id": "audit-1"})
    monkeypatch.setattr(openclaw_tools.account_store, "create_memory", lambda **kwargs: created.append(kwargs) or {"id": "memory-1", **kwargs})

    asyncio.run(openclaw_tools.invoke_system_tool(account, "quant.watchlist.add", {"code": "600519", "reason": "稳健现金流"}))

    assert len(created) == 1
    assert created[0]["workspace_id"] == "workspace-1"
    assert created[0]["source"] == "openclaw:auto"
```

- [ ] **Step 2: Run the bridging tests to see the remaining gaps**

Run: `pytest tests/test_openclaw_tools.py tests/test_openclaw_bridge.py -q`

Expected: FAIL if any tool still bypasses audit logging, confirmation gating, or research-memory auto capture.

- [ ] **Step 3: Implement the tool and bridge tightening**

```python
# dashboard/openclaw_tools.py
# Keep SYSTEM_TOOLS limited to:
# - quant.watchlist.add / remove / list
# - quant.stock.open
# - quant.paper.order / close_position / summary
# - quant.valuation.peg
# - quant.data.snapshot
# - quant.qlib.top
# - quant.report.generate_daily / open
# - quant.memory.create / search
# - quant.skill.record
#
# _require_tool_confirmation():
# - require a signed confirmation token for paper orders, close_position, and skill recording
#
# _auto_record_research_memory():
# - write a research memory for watchlist, order, close, and report actions with code, reason, and source
```

- [ ] **Step 4: Run the bridge tests again**

Run: `pytest tests/test_openclaw_tools.py tests/test_openclaw_bridge.py -q`

Expected: PASS, with bridge calls returning only approved tools, paper trading staying in the simulated boundary, and memories/reports/skills being persisted per workspace.

- [ ] **Step 5: Commit**

```bash
git add dashboard/openclaw_tools.py dashboard/routers/openclaw.py dashboard/account_store.py dashboard/static/openclaw-workbench.js tests/test_openclaw_tools.py tests/test_openclaw_bridge.py
git commit -m "feat: finish openclaw tool bridge"
```

### Task 5: Finish the OpenClaw Workspace UI and Account Menu

**Files:**
- Modify: `dashboard/templates/index.html`
- Modify: `dashboard/templates/partials/scripts.html`
- Modify: `dashboard/static/app.js`
- Modify: `dashboard/static/app-bootstrap.js`
- Modify: `dashboard/static/core/app-shell.js`
- Modify: `dashboard/static/app-ui-shell.js`
- Modify: `dashboard/static/openclaw-workbench.js`
- Modify: `dashboard/static/sw.js`
- Modify: `dashboard/static/style.css`
- Test: `tests/e2e/v2-smoke.spec.cjs`
- Create: `tests/e2e/openclaw.spec.cjs`

- [ ] **Step 1: Write the failing browser test**

```js
const { test, expect } = require('@playwright/test');

const TEST_INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const TEST_PASSWORD = 'Playwright123!';

async function waitForAppReady(page) {
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('#stock-offcanvas')).toBeAttached();
    await page.waitForFunction(() => {
        return Boolean(
            window.App
            && window.IntentBus
            && window.GlobalStockStore
            && window.ActionRegistry
            && window.LocalMCP
            && window.BusinessAdapter
            && window.CommandPalette
            && window.RightRailController
            && window.PanelLifecycle
        );
    });
}

async function ensureAuthenticated(page, usernameSuffix = Date.now()) {
    const username = `pw_${usernameSuffix}`.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 32);
    const payload = {
        username,
        password: TEST_PASSWORD,
        invite_code: TEST_INVITE_CODE,
        display_name: username,
        email: null,
    };
    const auth = await page.request.post('/api/account/register', { data: payload });
    const response = auth.ok()
        ? auth
        : await page.request.post('/api/account/login', { data: { username, password: TEST_PASSWORD } });
    expect(response.ok()).toBeTruthy();
    const sessionCookie = response.headers()['set-cookie'] || '';
    const cookieValue = sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '';
    expect(cookieValue).toBeTruthy();
    await page.context().addCookies([{
        name: 'quant_session',
        value: cookieValue,
        domain: '127.0.0.1',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
    return username;
}

test('openclaw menu and settings surface render for an authenticated user', async ({ page }) => {
    await ensureAuthenticated(page, 'openclaw_ui');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await expect(page.locator('#nav-openclaw')).toBeVisible();
    await page.locator('#nav-openclaw').click();
    await expect(page.locator('#tab-openclaw')).toBeVisible();
    await expect(page.locator('#openclaw-workbench')).toBeAttached();

    await page.locator('#user-shell-avatar').click();
    await expect(page.locator('[data-user-action="open-workspace"]')).toBeVisible();
    await expect(page.locator('[data-user-action="open-openclaw-settings"]')).toBeVisible();
    await expect(page.locator('[data-user-action="open-skills"]')).toBeVisible();
    await expect(page.locator('[data-user-action="open-audit"]')).toBeVisible();
    await expect(page.locator('[data-user-action="logout"]')).toBeVisible();

    await page.locator('[data-user-action="open-openclaw-settings"]').click();
    await expect(page.locator('#tab-openclaw-settings')).toBeVisible();
    await expect(page.locator('#openclaw-settings-workbench')).toBeAttached();
});
```

- [ ] **Step 2: Run the browser test to confirm the current shell is still missing pieces**

Run: `npx playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: FAIL if any avatar menu item, settings tab, or OpenClaw workspace pane is not wired end-to-end.

- [ ] **Step 3: Implement the shell and workbench wiring**

```javascript
// dashboard/templates/partials/scripts.html
// Keep app.js, app-ui-shell.js, openclaw-workbench.js, core/app-shell.js,
// and app-bootstrap.js in that order. Bump query versions for changed files.

// dashboard/static/app.js
// Ensure _pageBundles.openclaw includes /static/openclaw-workbench.js and
// that ensureBundle('openclaw') resolves before switchTab initializes the page.

// dashboard/static/core/app-shell.js
// Keep _tabTitles and switchTab handling for openclaw and openclaw-settings.

// dashboard/static/app-ui-shell.js
// Add explicit menu actions for:
// open-workspace, open-openclaw-settings, open-skills, open-audit, logout,
// and open-login for account switching.
//
// dashboard/static/openclaw-workbench.js
// Keep the workspace page and settings page separate and bind them to:
// /api/openclaw/status, /api/openclaw/setup, /api/openclaw/chat,
// /api/openclaw/memories, /api/openclaw/reports/daily, /api/openclaw/skills,
// /api/openclaw/tools, /api/account/audit, /api/account/workspace,
// /api/account/permissions, and /api/account/invites.

// dashboard/static/sw.js
// Include app-ui-shell.js, openclaw-workbench.js, app-bootstrap.js, and
// core/app-shell.js in STATIC_ASSETS, then bump CACHE_NAME.
```

- [ ] **Step 4: Run the browser test again**

Run: `npx playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: PASS, with the OpenClaw tab visible, the settings surface loading the account bundle, and the avatar menu exposing the full workspace/admin navigation.

- [ ] **Step 5: Commit**

```bash
git add dashboard/templates/index.html dashboard/templates/partials/scripts.html dashboard/static/app.js dashboard/static/app-bootstrap.js dashboard/static/core/app-shell.js dashboard/static/app-ui-shell.js dashboard/static/openclaw-workbench.js dashboard/static/sw.js dashboard/static/style.css tests/e2e/v2-smoke.spec.cjs tests/e2e/openclaw.spec.cjs
git commit -m "feat: finish openclaw workspace ui"
```

### Task 6: Update Docs, Env Examples, and Final Acceptance Checks

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/OPENCLAW_INTEGRATION_PLAN.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `package.json`
- Modify: `scripts/e2e.sh`

- [ ] **Step 1: Write the final regression test and command check**

```js
test('dashboard smoke keeps openclaw and core shell alive together', async ({ page }) => {
    await ensureAuthenticated(page, 'final_smoke');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await expect(page.locator('#nav-overview')).toBeVisible();
    await expect(page.locator('#nav-openclaw')).toBeVisible();
    await expect(page.locator('#openclaw-workbench')).toBeAttached();
    await expect(page.locator('#user-shell-avatar')).toBeVisible();
});
```

- [ ] **Step 2: Run the full local verification pass**

Run:

```bash
pytest tests -q
npm run e2e
```

Expected: all Python tests pass and the Playwright smoke suite passes with the authenticated OpenClaw tab available.

- [ ] **Step 3: Update the docs and operator guidance**

```markdown
OpenClaw is a full external service with a managed local wrapper.
Each user gets one workspace, one OpenClaw workspace ID, workspace-scoped tools, and workspace-scoped audit/memory/report records.
The platform exposes only approved tools; live trading remains disabled.
```

- [ ] **Step 4: Run the final doc and smoke pass again**

Run:

```bash
pytest tests/test_session_gate.py tests/test_openclaw_tools.py tests/test_openclaw_account.py tests/test_openclaw_service.py -q
npx playwright test tests/e2e/openclaw.spec.cjs tests/e2e/v2-smoke.spec.cjs --config=playwright.config.cjs
```

Expected: PASS, with no unresolved OpenClaw placeholders left in docs or runtime flags.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/ARCHITECTURE.md docs/OPENCLAW_INTEGRATION_PLAN.md .env.example docker-compose.yml package.json scripts/e2e.sh
git commit -m "docs: finish openclaw integration guidance"
```

## Coverage Check

- Invite registration, login/logout, and workspace bootstrap map to Task 1.
- Invite-code hashing and admin-only invite management map to Task 2.
- Managed OpenClaw startup and gateway compatibility map to Task 3.
- Approved tool exposure, confirmation flow, memory capture, report generation, and skills map to Task 4.
- The top-level OpenClaw tab, avatar menu, and settings page map to Task 5.
- Docs, env flags, and end-to-end acceptance map to Task 6.

## Scope Note

This plan intentionally keeps the quant platform as the business source of truth and does not add live trading exposure. Any future skill marketplace or dedicated per-user OpenClaw deployment should be split into a separate plan after this one is merged.
