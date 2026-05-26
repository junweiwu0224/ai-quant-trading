# OpenClaw ChatGPT Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the OpenClaw page into a To C chat experience with a collapsed right conversation rail, a real stop button beside the composer, and OpenClaw-only conversation history.

**Architecture:** Keep the existing OpenClaw chat/tool backend, but add an OpenClaw-specific conversation surface so its history never mixes with the generic assistant history. The page becomes a three-zone chat shell: the main chat stream, a composer with a real abort action, and a right rail that defaults to a narrow icon strip and expands to 320px. The rail owns search, recent conversations, and switching; service/admin detail stays behind settings so the default screen stays quiet.

**Tech Stack:** FastAPI, SQLite/SQLAlchemy, Vanilla JS, Playwright, pytest, the existing dashboard shell, and the current `openclaw-2026.5.20.tgz` runtime.

---

## File Map

- `data/storage/storage.py`: add `Conversation.surface`, migrate existing rows, and scope lookups by surface.
- `dashboard/routers/openclaw.py`: add OpenClaw-specific conversation endpoints.
- `dashboard/static/core/api-client.js`: accept `signal` so OpenClaw can abort an in-flight chat request.
- `dashboard/static/openclaw-conversations.js`: new right-rail conversation helper for list/search/new/switch/delete/persist.
- `dashboard/static/openclaw-workbench.js`: chat canvas, composer, stop action, and delegation to the conversation helper.
- `dashboard/templates/partials/scripts.html`: load the new OpenClaw helper before the workbench.
- `dashboard/static/style.css`: rail widths, collapsed icon strip, chat layout, composer, and message states.
- `dashboard/static/sw.js`: cache the new helper script.
- `tests/test_openclaw_conversations.py`: backend regression for OpenClaw conversation isolation.
- `tests/e2e/openclaw.spec.cjs`: browser regression for collapsed rail, stop, conversation switching, and reload persistence.

---

### Task 1: Add OpenClaw conversation isolation

**Files:**
- Modify: `data/storage/storage.py`
- Modify: `dashboard/routers/openclaw.py`
- Test: `tests/test_openclaw_conversations.py`

- [ ] **Step 1: Write the failing test**

```python
import importlib

import pytest

from dashboard.account_store import AccountStore
from data.storage.storage import DataStorage


@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch, tmp_path):
    account_store = AccountStore(tmp_path / "accounts.db")
    conversation_store = DataStorage(f"sqlite:///{tmp_path / 'conversations.db'}")

    import dashboard.account_store as account_store_module
    import dashboard.routers.account as account_router
    import dashboard.routers.openclaw as openclaw_router
    import dashboard.session as session_module
    app_module = importlib.import_module("dashboard.app")

    monkeypatch.setattr(account_store_module, "account_store", account_store)
    monkeypatch.setattr(account_router, "account_store", account_store)
    monkeypatch.setattr(openclaw_router, "conversation_store", conversation_store)
    monkeypatch.setattr(session_module, "account_store", account_store)
    monkeypatch.setattr(app_module, "account_store", account_store)
    yield account_store, conversation_store


def test_openclaw_conversations_are_surface_scoped(client, isolated_stores):
    account_store, conversation_store = isolated_stores
    bundle = account_store.create_user("alice", "Password123!", "LOCAL1")
    token, _ = account_store.create_session(bundle["user"]["id"])
    client.cookies.set("quant_session", token)

    conversation_store.save_conversation(
        "llm-1",
        "Generic LLM",
        [{"role": "user", "content": "generic"}],
        workspace_id=bundle["workspace"]["id"],
        surface="llm",
    )

    resp = client.post("/api/openclaw/conversations", json={
        "id": "oc-1",
        "title": "OpenClaw",
        "messages": [{"role": "user", "content": "openclaw"}],
    })
    assert resp.status_code == 200

    openclaw_rows = client.get("/api/openclaw/conversations").json()["items"]
    llm_rows = conversation_store.list_conversations(
        workspace_id=bundle["workspace"]["id"],
        surface="llm",
    )

    assert [row["id"] for row in openclaw_rows] == ["oc-1"]
    assert [row["id"] for row in llm_rows] == ["llm-1"]
    assert client.get("/api/openclaw/conversations/llm-1").status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_openclaw_conversations.py -q`

Expected: fail because `/api/openclaw/conversations` does not exist yet and the `conversations` table still has no `surface` column.

- [ ] **Step 3: Add the storage column and OpenClaw endpoints**

```python
# data/storage/storage.py
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), index=True, default="")
    surface = Column(String(32), nullable=False, default="llm", index=True)
    title = Column(String(200), default="新对话")
    messages_json = Column(Text, default="[]")
    created_at = Column(String(30))
    updated_at = Column(String(30))


def list_conversations(self, limit: int = 50, workspace_id: str = "", surface: str = "llm") -> list[dict]:
    session = self._get_session()
    try:
        query = session.query(Conversation).order_by(Conversation.updated_at.desc())
        query = query.filter(Conversation.workspace_id == (workspace_id or ""))
        query = query.filter(Conversation.surface == (surface or "llm"))
        rows = query.limit(limit).all()
        return [{"id": r.id, "title": r.title, "created_at": r.created_at, "updated_at": r.updated_at} for r in rows]
    finally:
        session.close()


def get_conversation(self, conv_id: str, workspace_id: str = "", surface: str = "llm") -> dict | None:
    session = self._get_session()
    try:
        query = session.query(Conversation).filter(Conversation.id == conv_id)
        query = query.filter(Conversation.workspace_id == (workspace_id or ""))
        query = query.filter(Conversation.surface == (surface or "llm"))
        row = query.first()
        if not row:
            return None
        return {
            "id": row.id,
            "title": row.title,
            "messages": _json_loads(row.messages_json, []),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    finally:
        session.close()


def save_conversation(self, conv_id: str, title: str, messages: list, workspace_id: str = "", surface: str = "llm") -> None:
    session = self._get_session()
    try:
        query = session.query(Conversation).filter(Conversation.id == conv_id)
        query = query.filter(Conversation.workspace_id == (workspace_id or ""))
        query = query.filter(Conversation.surface == (surface or "llm"))
        row = query.first()
        now = _now_iso()
        payload = _json_dumps(messages or [])
        if row:
            row.title = title
            row.messages_json = payload
            row.updated_at = now
        else:
            session.add(Conversation(
                id=conv_id,
                workspace_id=workspace_id or "",
                surface=surface or "llm",
                title=title,
                messages_json=payload,
                created_at=now,
                updated_at=now,
            ))
        session.commit()
    finally:
        session.close()


def delete_conversation(self, conv_id: str, workspace_id: str = "", surface: str = "llm") -> bool:
    session = self._get_session()
    try:
        query = session.query(Conversation).filter(Conversation.id == conv_id)
        query = query.filter(Conversation.workspace_id == (workspace_id or ""))
        query = query.filter(Conversation.surface == (surface or "llm"))
        deleted = query.delete()
        session.commit()
        return deleted > 0
    finally:
        session.close()
```

```python
# dashboard/routers/openclaw.py
from data.storage.storage import DataStorage

conversation_store = DataStorage()


class ConversationSaveRequest(BaseModel):
    id: str
    title: str = "新对话"
    messages: list[ChatMessage] = Field(default_factory=list)


@router.get("/conversations")
async def list_conversations(account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    return {
        "success": True,
        "items": conversation_store.list_conversations(workspace_id=workspace_id, surface="openclaw"),
    }


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    conv = conversation_store.get_conversation(conv_id, workspace_id=workspace_id, surface="openclaw")
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "data": conv}


@router.post("/conversations")
async def save_conversation(req: ConversationSaveRequest, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    conversation_store.save_conversation(req.id, req.title, msgs, workspace_id=workspace_id, surface="openclaw")
    return {"success": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    ok = conversation_store.delete_conversation(conv_id, workspace_id=workspace_id, surface="openclaw")
    return {"success": True, "removed": ok}
```

- [ ] **Step 4: Run the focused test again**

Run: `pytest tests/test_openclaw_conversations.py -q`

Expected: PASS, with OpenClaw rows isolated from the generic `llm` surface.

- [ ] **Step 5: Commit**

```bash
git add data/storage/storage.py dashboard/routers/openclaw.py tests/test_openclaw_conversations.py
git commit -m "feat: separate OpenClaw conversation history"
```

### Task 2: Make the OpenClaw composer abortable and ChatGPT-like

**Files:**
- Modify: `dashboard/static/core/api-client.js`
- Modify: `dashboard/static/openclaw-workbench.js`
- Modify: `dashboard/static/style.css`
- Test: `tests/e2e/openclaw.spec.cjs`

- [ ] **Step 1: Write the failing browser test**

```javascript
test('OpenClaw starts collapsed and stop cancels a pending reply', async ({ page }) => {
    await ensureAuthenticated(page, 'rail_stop');
    await page.goto('/#openclaw');

    await expect(page.locator('.openclaw-shell')).toHaveClass(/is-rail-collapsed/);
    await expect(page.locator('.openclaw-rail')).toHaveClass(/is-collapsed/);

    await page.locator('[data-openclaw-action="toggle-rail"]').click();
    await expect(page.locator('.openclaw-shell')).toHaveClass(/is-rail-open/);

    await page.route('**/api/openclaw/chat', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        await route.fulfill({
            json: { success: true, mode: 'native', content: 'long reply' },
        });
    });

    await page.locator('#openclaw-input').fill('帮我分析 600519');
    await page.locator('[data-openclaw-action="send"]').click();
    await page.locator('[data-openclaw-action="stop"]').click();

    await expect(page.locator('.openclaw-message.is-canceled')).toContainText('已停止');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm exec -- playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: fail because the current shell still exposes the bulky workbench, the rail is not a collapsed icon strip, and the composer cannot abort an in-flight request.

- [ ] **Step 3: Add abort support and the compact shell**

```javascript
// dashboard/static/core/api-client.js
async function fetchJSON(url, opts = {}) {
    const {
        timeout = 15000,
        silent = false,
        retries = 0,
        label = '',
        onToast,
        signal,
        ...fetchOpts
    } = opts;

    const controller = signal ? null : new AbortController();
    const requestSignal = signal || controller.signal;
    const res = await fetch(url, { ...fetchOpts, headers, signal: requestSignal });
}
```

```javascript
// dashboard/static/openclaw-workbench.js
this._chatAbortController?.abort();
this._chatAbortController = new AbortController();

const data = await App.fetchJSON('/api/openclaw/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, history }),
    timeout: 60000,
    signal: this._chatAbortController.signal,
});

async stopGenerating() {
    this._chatAbortController?.abort();
    const pending = this._messages.findLast?.((m) => m.pending) || this._messages.find((m) => m.pending);
    if (pending) {
        pending.pending = false;
        pending.canceled = true;
        pending.content = '已停止';
    }
    this._renderMessages();
}
```

```css
/* dashboard/static/style.css */
.openclaw-shell {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 56px;
    min-height: calc(100vh - 64px);
    transition: grid-template-columns 180ms ease;
}
.openclaw-shell.is-rail-open {
    grid-template-columns: minmax(0, 1fr) 320px;
}
.openclaw-rail {
    width: 56px;
    overflow: hidden;
    border-left: 1px solid var(--border-color);
}
.openclaw-shell.is-rail-open .openclaw-rail {
    width: 320px;
}
.openclaw-composer {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 8px;
    align-items: end;
}
.openclaw-message.is-canceled {
    opacity: 0.7;
}
```

- [ ] **Step 4: Run the browser test again**

Run: `npm exec -- playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: PASS, with the rail collapsed by default, the rail width expanding to 320px, and the stop action aborting the pending request and leaving a canceled assistant bubble.

- [ ] **Step 5: Commit**

```bash
git add dashboard/static/core/api-client.js dashboard/static/openclaw-workbench.js dashboard/static/style.css tests/e2e/openclaw.spec.cjs
git commit -m "feat: add chatgpt-style openclaw shell"
```

### Task 3: Add the right-rail conversation manager and persist OpenClaw history

**Files:**
- Create: `dashboard/static/openclaw-conversations.js`
- Modify: `dashboard/static/openclaw-workbench.js`
- Modify: `dashboard/templates/partials/scripts.html`
- Modify: `dashboard/static/sw.js`
- Modify: `dashboard/static/style.css`
- Test: `tests/e2e/openclaw.spec.cjs`

- [ ] **Step 1: Write the failing browser test**

```javascript
test('OpenClaw rail can create, search, switch, and reload its own history', async ({ page }) => {
    await ensureAuthenticated(page, 'rail_history');
    await page.goto('/#openclaw');

    await page.locator('[data-openclaw-action="new-chat"]').click();
    await page.locator('#openclaw-input').fill('今天 600519 怎么样');
    await page.locator('[data-openclaw-action="send"]').click();

    await page.locator('[data-openclaw-action="new-chat"]').click();
    await page.locator('#openclaw-input').fill('帮我看 000001');
    await page.locator('[data-openclaw-action="send"]').click();

    await page.locator('[data-openclaw-action="toggle-rail"]').click();
    await page.locator('[data-openclaw-action="search-conversation"]').fill('600519');
    await expect(page.locator('.openclaw-conversation-item')).toContainText('600519');

    await page.locator('.openclaw-conversation-item').first().click();
    await expect(page.locator('.openclaw-message.is-user')).toContainText('600519');

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.locator('.openclaw-conversation-item.is-active')).toContainText('600519');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm exec -- playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: fail because there is no OpenClaw-specific right rail, no conversation persistence, and no reload restore for the active conversation.

- [ ] **Step 3: Build the reusable rail helper and wire the shell**

```javascript
// dashboard/static/openclaw-conversations.js
const OpenClawConversations = {
    state: {
        workspaceId: '',
        railOpen: false,
        activeConversationId: '',
        items: [],
        query: '',
    },

    async init({ workspaceId }) {
        this.state.workspaceId = workspaceId || '';
        this.state.railOpen = this._readRailOpen();
        this.state.activeConversationId = this._readActiveConversationId();
        await this.refresh();
        this.render();
    },

    async refresh() {
        const resp = await App.fetchJSON('/api/openclaw/conversations', { silent: true });
        this.state.items = resp?.items || [];
        if (!this.state.activeConversationId && this.state.items[0]) {
            this.state.activeConversationId = this.state.items[0].id;
        }
        this._persistActiveConversationId();
    },

    async openConversation(id) {
        const resp = await App.fetchJSON(`/api/openclaw/conversations/${id}`, { silent: true });
        this.state.activeConversationId = id;
        this._persistActiveConversationId();
        return resp?.data || null;
    },

    async saveConversation(payload) {
        await App.fetchJSON('/api/openclaw/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        await this.refresh();
    },

    async deleteConversation(id) {
        await App.fetchJSON(`/api/openclaw/conversations/${id}`, {
            method: 'DELETE',
            silent: true,
        });
        if (this.state.activeConversationId === id) {
            this.state.activeConversationId = this.state.items[0]?.id || '';
            this._persistActiveConversationId();
        }
        await this.refresh();
    },

    toggleRail(force) {
        this.state.railOpen = typeof force === 'boolean' ? force : !this.state.railOpen;
        this._persistRailOpen();
        this.render();
    },

    setQuery(query) {
        this.state.query = String(query || '').trim();
        this.render();
    },

    filteredItems() {
        const query = this.state.query.toLowerCase();
        return this.state.items.filter((item) => {
            if (!query) return true;
            return String(item.title || '').toLowerCase().includes(query);
        });
    },

    render() {
        const shell = document.querySelector('.openclaw-shell');
        if (!shell) return;
        shell.classList.toggle('is-rail-open', this.state.railOpen);
        shell.classList.toggle('is-rail-collapsed', !this.state.railOpen);
    },

    _persistRailOpen() {
        localStorage.setItem(this._railKey(), this.state.railOpen ? '1' : '0');
    },

    _readRailOpen() {
        return localStorage.getItem(this._railKey()) === '1';
    },

    _persistActiveConversationId() {
        localStorage.setItem(this._activeKey(), this.state.activeConversationId || '');
    },

    _readActiveConversationId() {
        return localStorage.getItem(this._activeKey()) || '';
    },

    _railKey() {
        return `openclaw:rail-open:${this.state.workspaceId || 'default'}`;
    },

    _activeKey() {
        return `openclaw:active-conversation:${this.state.workspaceId || 'default'}`;
    },
};
```

```html
<!-- dashboard/templates/partials/scripts.html -->
<script src="/static/openclaw-conversations.js?v=1" defer></script>
<script src="/static/openclaw-workbench.js?v=16" defer></script>
```

```javascript
// dashboard/static/openclaw-workbench.js
await OpenClawConversations.init({
    workspaceId: App._accountState?.workspace?.id || '',
});
```

```javascript
// dashboard/static/sw.js
const openclawScripts = [
    '/static/openclaw-conversations.js?v=1',
    '/static/openclaw-workbench.js?v=16',
];
```

- [ ] **Step 4: Run the browser test again**

Run: `npm exec -- playwright test tests/e2e/openclaw.spec.cjs --config=playwright.config.cjs`

Expected: PASS, with the right rail showing OpenClaw-only history, search filtering the list, conversation switching restoring the right thread, and reload preserving the active conversation.

- [ ] **Step 5: Commit**

```bash
git add dashboard/static/openclaw-conversations.js dashboard/static/openclaw-workbench.js dashboard/templates/partials/scripts.html dashboard/static/sw.js dashboard/static/style.css tests/e2e/openclaw.spec.cjs
git commit -m "feat: add openclaw conversation rail"
```
