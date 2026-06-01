# Agent 驱动的 A 股策略研发与模拟交易平台 实施计划

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行此计划。步骤使用复选框 (`- [ ]`) 追踪。

**目标：** 构建真正的 Agent 驱动 A 股策略研发与模拟交易平台，让多智能体投研、AI 策略优化、统一信号市场、回测晋级、模拟盘复制和持续复盘形成闭环。

**架构：** 在现有 Qlib、问财、热点归因、回测、模拟盘、OpenClaw、权限审计基础上新增 `agentic` 领域层。该层以 `TradingSignal`、`AgentProfile`、`ResearchJob`、`StrategyDraft`、`PaperPromotion`、`AgentPerformance` 为核心对象，把 TradingAgents-CN 的多智能体投研流水线与 AI-Trader 的 Agent 信号市场/模拟跟单路径合并为受风控约束的策略生命周期系统。

**技术栈：** Python 3.11、FastAPI、SQLite/SQLAlchemy、APScheduler、Vanilla JS SPA、OpenAI-compatible LLM/OpenClaw、Qlib 兼容服务、pytest、Docker Compose。

---

## 1. 最终版产品边界

用户最终应能完成完整闭环：选择标的或股票池 → 启动多智能体投研 → 生成结构化研究结论 → 转成受限策略 DSL → 回测与 AI 参数迭代 → 通过晋级门槛 → 变成 Strategy Agent → 发布统一 TradingSignal → 用户确认加入模拟盘 → 持续复盘 Agent 表现 → 继续、降权、暂停或回炉优化。

明确不做：不接实盘自动交易；不允许 AI 执行任意 Python 策略代码；不允许未通过回测/风控门槛的 Agent 自动下模拟盘订单；不做公开社交交易市场；不把 LLM 自由文本当成交易信号。

安全原则：AI 只能生成 `StrategyDraft` 和 `TradingSignal`；策略必须使用受限 DSL；模拟盘动作必须写审计日志；自动模拟复制默认关闭；第一版只开放观察模式和人工确认模式。

---

## 2. 文件结构

### 新增领域层

- 新建 `agentic/__init__.py`：Agentic Trading 包声明。
- 新建 `agentic/models.py`：`AgentProfile`、`TradingSignal`、`ResearchJob`、`StrategyDraft`、`BacktestIteration`、`PaperPromotionRule`、`AgentPerformanceSnapshot`。
- 新建 `agentic/repository.py`：SQLite 表创建、增删查改、状态流转和查询聚合。
- 新建 `agentic/registry.py`：内置 Agent 注册表：Qlib、Hotspot、Iwencai、Risk、OpenClaw Research、Strategy Agent。
- 新建 `agentic/signals.py`：信号创建、校验、过期、状态流转、信号到模拟盘意图转换。
- 新建 `agentic/research_pipeline.py`：TradingAgents-CN 风格多智能体投研流水线。
- 新建 `agentic/strategy_dsl.py`：受限策略 DSL schema、校验器、默认模板和安全限制。
- 新建 `agentic/strategy_lab.py`：AI Strategy Lab，负责策略草案、回测迭代、晋级门槛。
- 新建 `agentic/paper_bridge.py`：把通过风控的信号转成模拟盘确认单/订单意图。
- 新建 `agentic/performance.py`：Agent 信号表现与模拟盘复制表现计算。

### API 与前端

- 新建 `dashboard/routers/agentic.py`：Agent Registry、Signal Pool、Research Jobs、Strategy Lab、Paper Promotion、Performance API。
- 修改 `dashboard/app.py`：注册 `agentic` router。
- 修改 `dashboard/templates/index.html`：增加 `AI 策略实验室` 和 `Agent 信号池` 容器。
- 修改 `dashboard/templates/partials/scripts.html`：引入新 JS 模块并提升缓存版本。
- 新建 `dashboard/static/agentic-signals.js`：Signal Pool 页面。
- 新建 `dashboard/static/agentic-research.js`：多智能体投研 job 页面。
- 新建 `dashboard/static/agentic-strategy-lab.js`：AI Strategy Lab 页面。
- 修改 `dashboard/static/style.css`：增加 agentic 页面样式。

### 测试

- 新建 `tests/test_agentic_models.py`
- 新建 `tests/test_agentic_registry.py`
- 新建 `tests/test_agentic_repository.py`
- 新建 `tests/test_agentic_signals.py`
- 新建 `tests/test_agentic_research_pipeline.py`
- 新建 `tests/test_agentic_strategy_dsl.py`
- 新建 `tests/test_agentic_strategy_lab.py`
- 新建 `tests/test_agentic_paper_bridge.py`
- 新建 `tests/test_agentic_performance.py`
- 新建 `tests/test_agentic_api.py`
- 新建 `tests/test_agentic_frontend.py`

---
## 3. 阶段一：Agentic Core

### 任务 1: 核心模型

**文件：**
- 新建: `agentic/__init__.py`
- 新建: `agentic/models.py`
- 测试: `tests/test_agentic_models.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_agentic_models.py` 写入：

```python
from agentic.models import AgentProfile, TradingSignal, normalize_signal_code


def test_normalize_signal_code_accepts_exchange_suffix():
    assert normalize_signal_code("605066.SH") == "605066"
    assert normalize_signal_code("sz000001") == "000001"


def test_trading_signal_requires_structured_reason_and_risk():
    signal = TradingSignal(
        id="sig_1",
        agent_id="qlib_agent",
        source="qlib",
        code="605066.SH",
        direction="buy",
        confidence=0.72,
        time_horizon="3-10d",
        entry_reasons=["Qlib score top 5", "close above MA20"],
        risk_notes=["break MA20 invalidates signal"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.12,
        status="new",
        created_at="2026-06-01T15:00:00+08:00",
        expires_at="2026-06-08T15:00:00+08:00",
    )

    assert signal.code == "605066"
    assert signal.confidence == 0.72
    assert signal.entry_reasons[0] == "Qlib score top 5"
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_models.py -q`  
预期: 失败，提示 `ModuleNotFoundError: No module named 'agentic'`。

- [ ] **步骤 3：编写最小实现**

在 `agentic/__init__.py` 写入：

```python
"""Agent-driven research, signal, strategy, and paper-trading domain."""
```

在 `agentic/models.py` 写入：

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

SignalDirection = Literal["buy", "sell", "hold", "risk"]
SignalStatus = Literal["new", "watching", "backtested", "paper_pending", "paper_active", "expired", "invalidated", "closed"]


def normalize_signal_code(code: str) -> str:
    cleaned = re.sub(r"[^0-9]", "", code or "")
    if len(cleaned) < 6:
        raise ValueError("stock code must contain 6 digits")
    return cleaned[-6:]


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    kind: str
    description: str
    permissions: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class TradingSignal:
    id: str
    agent_id: str
    source: str
    code: str
    direction: SignalDirection
    confidence: float
    time_horizon: str
    entry_reasons: list[str]
    risk_notes: list[str]
    suggested_position: float
    stop_loss: float | None
    take_profit: float | None
    status: SignalStatus
    created_at: str
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "code", normalize_signal_code(self.code))
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.entry_reasons:
            raise ValueError("entry_reasons is required")
        if not self.risk_notes:
            raise ValueError("risk_notes is required")
        if not 0 <= float(self.suggested_position) <= 1:
            raise ValueError("suggested_position must be between 0 and 1")
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_models.py -q`  
预期: `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/__init__.py agentic/models.py tests/test_agentic_models.py
git commit -m "feat: add agentic core models"
```

### 任务 2: Agent Registry

**文件：**
- 新建: `agentic/registry.py`
- 测试: `tests/test_agentic_registry.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.registry import AgentRegistry


def test_builtin_agents_cover_quant_research_and_signal_sources():
    registry = AgentRegistry.default()

    assert registry.get("qlib_agent").name == "Qlib Momentum Agent"
    assert registry.get("hotspot_agent").kind == "signal"
    assert registry.get("risk_agent").permissions == ["read_market", "publish_risk_signal"]
    assert "publish_signal" in registry.get("openclaw_research_agent").permissions
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_registry.py -q`  
预期: 失败，提示 `No module named 'agentic.registry'`。

- [ ] **步骤 3：编写最小实现**

在 `agentic/registry.py` 写入：

```python
from __future__ import annotations

from agentic.models import AgentProfile


class AgentRegistry:
    def __init__(self, agents: list[AgentProfile]):
        self._agents = {agent.id: agent for agent in agents}

    @classmethod
    def default(cls) -> "AgentRegistry":
        return cls([
            AgentProfile("qlib_agent", "Qlib Momentum Agent", "signal", "Publishes ranked momentum signals from Qlib.", ["read_market", "read_qlib", "publish_signal"]),
            AgentProfile("hotspot_agent", "Hotspot Attribution Agent", "signal", "Publishes theme and sector-driven signals.", ["read_market", "publish_signal"]),
            AgentProfile("iwencai_agent", "Iwencai Screening Agent", "signal", "Publishes signals from saved iWencai result pools.", ["read_market", "publish_signal"]),
            AgentProfile("risk_agent", "Risk Review Agent", "risk", "Publishes risk warnings only.", ["read_market", "publish_risk_signal"]),
            AgentProfile("openclaw_research_agent", "OpenClaw Research Agent", "research", "Synthesizes structured research conclusions.", ["read_market", "read_qlib", "publish_signal", "create_research_job"]),
        ])

    def get(self, agent_id: str) -> AgentProfile:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def list(self) -> list[AgentProfile]:
        return list(self._agents.values())
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_registry.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/registry.py tests/test_agentic_registry.py
git commit -m "feat: register built-in trading agents"
```

### 任务 3: Repository 与信号持久化

**文件：**
- 新建: `agentic/repository.py`
- 新建: `agentic/signals.py`
- 测试: `tests/test_agentic_repository.py`
- 测试: `tests/test_agentic_signals.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_agentic_repository.py` 写入：

```python
from agentic.models import TradingSignal
from agentic.repository import AgenticRepository


def test_repository_saves_and_lists_signals(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    signal = TradingSignal("sig_1", "qlib_agent", "qlib", "605066.SH", "buy", 0.72, "3-10d", ["Qlib score top 5"], ["break MA20 invalidates"], 0.1, 0.05, 0.12, "new", "2026-06-01T15:00:00+08:00")

    repo.save_signal(signal)
    rows = repo.list_signals()

    assert len(rows) == 1
    assert rows[0].id == "sig_1"
    assert rows[0].code == "605066"
```

在 `tests/test_agentic_signals.py` 写入：

```python
from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_service_publishes_signal_with_generated_id(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))

    signal = service.publish(
        agent_id="qlib_agent",
        source="qlib",
        code="605066.SH",
        direction="buy",
        confidence=0.71,
        time_horizon="3-10d",
        entry_reasons=["Qlib Top", "MA20 uptrend"],
        risk_notes=["Break MA20 invalidates"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.12,
    )

    assert signal.id.startswith("sig_")
    assert signal.status == "new"
    assert service.list(limit=1)[0].id == signal.id
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_repository.py tests/test_agentic_signals.py -q`  
预期: 失败，提示 repository/signals 模块不存在。

- [ ] **步骤 3：编写最小实现**

`agentic/repository.py` 实现 SQLite 表 `agentic_signals`，字段包含 `id, agent_id, source, code, direction, confidence, time_horizon, entry_reasons, risk_notes, suggested_position, stop_loss, take_profit, status, created_at, expires_at, metadata`。使用 `utils.db.get_connection()`，JSON 字段用 `json.dumps(..., ensure_ascii=False)` 保存，读取后转回 `TradingSignal`。

`agentic/signals.py` 实现：

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from agentic.models import TradingSignal
from agentic.repository import AgenticRepository


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalService:
    def __init__(self, repo: AgenticRepository):
        self.repo = repo

    def publish(self, *, agent_id: str, source: str, code: str, direction: str, confidence: float, time_horizon: str, entry_reasons: list[str], risk_notes: list[str], suggested_position: float, stop_loss: float | None = None, take_profit: float | None = None, expires_at: str | None = None, metadata: dict | None = None) -> TradingSignal:
        signal = TradingSignal(f"sig_{uuid.uuid4().hex[:12]}", agent_id, source, code, direction, confidence, time_horizon, entry_reasons, risk_notes, suggested_position, stop_loss, take_profit, "new", iso_now(), expires_at, metadata or {})
        self.repo.save_signal(signal)
        return signal

    def list(self, limit: int = 100) -> list[TradingSignal]:
        return self.repo.list_signals(limit=limit)
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_repository.py tests/test_agentic_signals.py -q`  
预期: `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/repository.py agentic/signals.py tests/test_agentic_repository.py tests/test_agentic_signals.py
git commit -m "feat: persist and publish agent trading signals"
```

---

## 4. 阶段二：Agentic API 与信号池 UI

### 任务 4: Agentic API

**文件：**
- 新建: `dashboard/routers/agentic.py`
- 修改: `dashboard/app.py`
- 测试: `tests/test_agentic_api.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_agentic_agents_endpoint_lists_builtin_agents(client):
    resp = client.get("/api/agentic/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert any(item["id"] == "qlib_agent" for item in body["agents"])


def test_agentic_signals_endpoint_returns_list(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService
    monkeypatch.setattr(agentic_router, "signal_service", SignalService(AgenticRepository(tmp_path / "agentic.db")))
    resp = client.get("/api/agentic/signals")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "signals": []}
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_api.py -q`  
预期: 失败，提示 404 或 router 不存在。

- [ ] **步骤 3：编写最小实现**

在 `dashboard/routers/agentic.py` 新建 `APIRouter(prefix="/api/agentic")`，提供：

```python
@router.get("/agents")
def list_agents():
    return {"success": True, "agents": [asdict(agent) for agent in registry.list()]}

@router.get("/signals")
def list_signals(limit: int = 100):
    return {"success": True, "signals": [asdict(signal) for signal in signal_service.list(limit=limit)]}

@router.get("/health")
def health():
    return {"success": True, "components": {"registry": "online", "signals": "online"}}
```

在 `dashboard/app.py` 注册：

```python
from dashboard.routers import agentic
app.include_router(agentic.router)
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_api.py -q`  
预期: 全部通过。

- [ ] **步骤 5：提交**

```bash
git add dashboard/routers/agentic.py dashboard/app.py tests/test_agentic_api.py
git commit -m "feat: expose agentic registry and signals api"
```

### 任务 5: Signal Pool UI

**文件：**
- 修改: `dashboard/templates/index.html`
- 修改: `dashboard/templates/partials/scripts.html`
- 新建: `dashboard/static/agentic-signals.js`
- 修改: `dashboard/static/style.css`
- 测试: `tests/test_agentic_frontend.py`

- [ ] **步骤 1：编写失败测试**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_agentic_signal_pool_container_and_script_are_registered():
    html = (ROOT / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")
    scripts = (ROOT / "dashboard" / "templates" / "partials" / "scripts.html").read_text(encoding="utf-8")
    assert 'id="agentic-signal-pool"' in html
    assert 'data-agentic-signal-list' in html
    assert 'agentic-signals.js' in scripts


def test_agentic_signal_frontend_fetches_signal_api():
    js = (ROOT / "dashboard" / "static" / "agentic-signals.js").read_text(encoding="utf-8")
    assert "/api/agentic/signals" in js
    assert "renderSignalCard" in js
    assert "promote-paper" in js
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_frontend.py -q`  
预期: 失败，提示容器或脚本不存在。

- [ ] **步骤 3：编写最小实现**

在页面加入 `#agentic-signal-pool` 容器，含 `[data-agentic-signal-list]`。`agentic-signals.js` 负责 `fetch('/api/agentic/signals')`、`renderSignalCard(signal)`、状态筛选和按钮 `watch/backtest/promote-paper`。样式使用现有 dashboard 卡片/表格风格，卡片半径不超过 8px。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_frontend.py -q`  
预期: `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add dashboard/templates/index.html dashboard/templates/partials/scripts.html dashboard/static/agentic-signals.js dashboard/static/style.css tests/test_agentic_frontend.py
git commit -m "feat: add agent signal pool UI"
```

---
## 5. 阶段三：Multi-Agent Research

### 任务 6: ResearchJob 与流水线

**文件：**
- 修改: `agentic/models.py`
- 修改: `agentic/repository.py`
- 新建: `agentic/research_pipeline.py`
- 测试: `tests/test_agentic_research_pipeline.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.repository import AgenticRepository
from agentic.research_pipeline import ResearchPipeline


def test_research_pipeline_generates_five_role_report(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)
    job = pipeline.run(code="605066", context={"qlib_score": 0.72, "theme": "电网设备"})
    assert job.status == "completed"
    assert set(job.roles) == {"qlib", "market", "theme", "bear", "decision"}
    assert job.final_report["decision"] in {"observe", "paper_candidate", "reject"}
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_research_pipeline.py -q`  
预期: 失败，提示 `ResearchPipeline` 或 `ResearchJob` 不存在。

- [ ] **步骤 3：编写最小实现**

在 `agentic/models.py` 增加 `ResearchJob`，字段为 `id, code, status, roles, final_report, created_at, updated_at, error`，`code` 复用 `normalize_signal_code()`。

在 `agentic/repository.py` 增加表 `agentic_research_jobs` 和方法 `save_research_job(job)`、`get_research_job(job_id)`。

在 `agentic/research_pipeline.py` 实现同步流水线：固定五个角色 `qlib/market/theme/bear/decision`；第一版不调用 LLM，只用上下文生成结构化结果；当 `qlib_score >= 0.6` 时 `final_report.decision = 'paper_candidate'`，否则为 `observe`。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_research_pipeline.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/models.py agentic/repository.py agentic/research_pipeline.py tests/test_agentic_research_pipeline.py
git commit -m "feat: add multi-agent research pipeline"
```

---

## 6. 阶段四：Strategy DSL + AI Strategy Lab

### 任务 7: 受限策略 DSL

**文件：**
- 新建: `agentic/strategy_dsl.py`
- 测试: `tests/test_agentic_strategy_dsl.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.strategy_dsl import StrategyDSL, validate_strategy_dsl


def test_strategy_dsl_accepts_ranked_rotation_template():
    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [{"close_above_ma": 20}], "daily", 5, 0.05, 0.12, 10)
    assert validate_strategy_dsl(dsl).max_holdings == 5


def test_strategy_dsl_rejects_unsafe_strategy_type():
    dsl = StrategyDSL("python_exec", "all", "custom_code", [], "tick", 50, None, None, None)
    try:
        validate_strategy_dsl(dsl)
    except ValueError as exc:
        assert "unsupported strategy_type" in str(exc)
    else:
        raise AssertionError("unsafe DSL should be rejected")
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_strategy_dsl.py -q`  
预期: 失败，提示模块不存在。

- [ ] **步骤 3：编写最小实现**

`agentic/strategy_dsl.py` 定义 dataclass `StrategyDSL(strategy_type, universe, rank_by, filters, rebalance, max_holdings, stop_loss, take_profit, max_holding_days)`。支持 `ranked_rotation/threshold_signal/mean_reversion`，支持 `daily/weekly`，支持 `qlib_score/momentum_20d/volume_adjusted_momentum`，强制 `max_holdings` 在 1-20，强制 `stop_loss` 在 `(0, 0.2]`。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_strategy_dsl.py -q`  
预期: `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/strategy_dsl.py tests/test_agentic_strategy_dsl.py
git commit -m "feat: add safe strategy DSL"
```

### 任务 8: Strategy Lab 晋级评估

**文件：**
- 新建: `agentic/strategy_lab.py`
- 测试: `tests/test_agentic_strategy_lab.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.strategy_dsl import StrategyDSL
from agentic.strategy_lab import PromotionGate, StrategyLab


def test_strategy_lab_promotes_only_when_metrics_pass_gate():
    lab = StrategyLab(PromotionGate(min_trades=10, max_drawdown=0.12, min_sharpe=0.8))
    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [{"close_above_ma": 20}], "daily", 5, 0.05, 0.12, 10)
    result = lab.evaluate_iteration(dsl, {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1, "annual_return": 0.22})
    assert result.promoted is True
    assert result.reason == "passed promotion gate"
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_strategy_lab.py -q`  
预期: 失败，提示模块不存在。

- [ ] **步骤 3：编写最小实现**

`agentic/strategy_lab.py` 定义 `PromotionGate(min_trades=10, max_drawdown=0.15, min_sharpe=0.7)`、`StrategyIterationResult` 和 `StrategyLab.evaluate_iteration()`。先调用 `validate_strategy_dsl()`，再检查 `trades/max_drawdown/sharpe`，全部通过时返回 `promoted=True`。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_strategy_lab.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/strategy_lab.py tests/test_agentic_strategy_lab.py
git commit -m "feat: evaluate AI strategy lab promotion gates"
```

---
## 7. 阶段五：Promotion Gate + Paper Bridge

### 任务 9: 信号晋级状态流转

**文件：**
- 修改: `agentic/repository.py`
- 修改: `agentic/signals.py`
- 测试: `tests/test_agentic_promotion_gate.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_can_move_to_paper_pending_after_manual_confirmation(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(agent_id="qlib_agent", source="qlib", code="605066", direction="buy", confidence=0.75, time_horizon="3-10d", entry_reasons=["Qlib Top"], risk_notes=["stop loss required"], suggested_position=0.1, stop_loss=0.05)
    updated = service.mark_paper_pending(signal.id, confirmed_by="user_1")
    assert updated.status == "paper_pending"
    assert updated.metadata["confirmed_by"] == "user_1"
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_promotion_gate.py -q`  
预期: 失败，提示 `mark_paper_pending` 不存在。

- [ ] **步骤 3：编写最小实现**

在 repository 增加 `get_signal(signal_id)`。在 `SignalService` 增加 `mark_paper_pending(signal_id, confirmed_by)`：仅允许从 `new/watching/backtested` 进入 `paper_pending`，metadata 写入 `confirmed_by` 和 `paper_pending_at`，保存后返回更新对象。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_promotion_gate.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/repository.py agentic/signals.py tests/test_agentic_promotion_gate.py
git commit -m "feat: gate agent signals before paper promotion"
```

### 任务 10: 模拟盘桥接

**文件：**
- 新建: `agentic/paper_bridge.py`
- 测试: `tests/test_agentic_paper_bridge.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.models import TradingSignal
from agentic.paper_bridge import PaperBridge, PaperIntent


class FakeOrderManager:
    def __init__(self):
        self.orders = []
    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"id": "order_1", **kwargs}


def test_paper_bridge_creates_order_intent_not_direct_order_by_default():
    bridge = PaperBridge(order_manager=FakeOrderManager())
    signal = TradingSignal("sig_1", "qlib_agent", "qlib", "605066", "buy", 0.75, "3-10d", ["Qlib Top"], ["stop loss required"], 0.1, 0.05, 0.12, "paper_pending", "2026-06-01T15:00:00+08:00")
    intent = bridge.create_intent(signal, cash=50000)
    assert isinstance(intent, PaperIntent)
    assert intent.code == "605066"
    assert intent.amount == 5000
    assert bridge.order_manager.orders == []
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_paper_bridge.py -q`  
预期: 失败，提示模块不存在。

- [ ] **步骤 3：编写最小实现**

`agentic/paper_bridge.py` 定义 `PaperIntent(signal_id, agent_id, code, direction, amount, reason, requires_confirmation=True)` 和 `PaperBridge.create_intent(signal, cash)`。只接受 `paper_pending` 状态和 `buy/sell` 方向，按 `cash * suggested_position` 生成金额，默认不调用 `order_manager.create_order()`。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_paper_bridge.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/paper_bridge.py tests/test_agentic_paper_bridge.py
git commit -m "feat: create paper trading intents from agent signals"
```

---

## 8. 阶段六：Agent Performance

### 任务 11: Agent 表现评分

**文件：**
- 新建: `agentic/performance.py`
- 测试: `tests/test_agentic_performance.py`

- [ ] **步骤 1：编写失败测试**

```python
from agentic.performance import AgentPerformanceCalculator


def test_agent_performance_calculates_win_rate_and_average_return():
    calc = AgentPerformanceCalculator()
    snapshot = calc.calculate("qlib_agent", [{"return": 0.05, "max_drawdown": 0.02}, {"return": -0.02, "max_drawdown": 0.04}, {"return": 0.03, "max_drawdown": 0.01}])
    assert snapshot["agent_id"] == "qlib_agent"
    assert snapshot["signal_count"] == 3
    assert snapshot["win_rate"] == 2 / 3
    assert round(snapshot["avg_return"], 4) == 0.02
    assert snapshot["max_drawdown"] == 0.04
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_performance.py -q`  
预期: 失败，提示模块不存在。

- [ ] **步骤 3：编写最小实现**

`agentic/performance.py` 实现 `AgentPerformanceCalculator.calculate(agent_id, outcomes)`，返回 `agent_id/signal_count/win_rate/avg_return/max_drawdown`。空列表返回 0 指标。

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_performance.py -q`  
预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add agentic/performance.py tests/test_agentic_performance.py
git commit -m "feat: calculate agent signal performance"
```

---
## 9. 阶段七：集成验证与 Docker

### 任务 12: 综合 API 健康检查

**文件：**
- 修改: `dashboard/routers/agentic.py`
- 测试: `tests/test_agentic_api.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_agentic_health_reports_core_components(client):
    resp = client.get("/api/agentic/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["components"]["registry"] == "online"
    assert body["components"]["signals"] == "online"
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_agentic_api.py::test_agentic_health_reports_core_components -q`  
预期: 若尚未实现 health 则 404；如果任务 4 已实现，则应通过。

- [ ] **步骤 3：编写最小实现**

确保 `dashboard/routers/agentic.py` 中存在：

```python
@router.get("/health")
def agentic_health():
    return {"success": True, "components": {"registry": "online", "signals": "online", "research": "online", "strategy_lab": "online"}}
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_agentic_api.py -q`  
预期: 全部通过。

- [ ] **步骤 5：提交**

```bash
git add dashboard/routers/agentic.py tests/test_agentic_api.py
git commit -m "feat: expose agentic health check"
```

### 任务 13: 最终测试与 Docker 验证

**文件：**
- 可能修改: `docker-compose.yml`
- 可能修改: `docs/superpowers/plans/2026-06-01-agent-driven-a-share-strategy-platform.md`

- [ ] **步骤 1：运行 Agentic 全量测试**

运行：

```powershell
python -m pytest tests/test_agentic_models.py tests/test_agentic_registry.py tests/test_agentic_repository.py tests/test_agentic_signals.py tests/test_agentic_research_pipeline.py tests/test_agentic_strategy_dsl.py tests/test_agentic_strategy_lab.py tests/test_agentic_promotion_gate.py tests/test_agentic_paper_bridge.py tests/test_agentic_performance.py tests/test_agentic_api.py tests/test_agentic_frontend.py -q
```

预期：全部通过。

- [ ] **步骤 2：运行模拟盘回归**

运行：

```powershell
python -m pytest tests/test_paper.py tests/test_api_v2_full.py::TestPaperTrading tests/test_dashboard.py::TestSystemAPI -q
```

预期：全部通过。

- [ ] **步骤 3：构建 Docker**

运行：

```powershell
docker compose up -d --build dashboard
```

预期：`dashboard` 和 `openclaw` 容器为 `Up`。

- [ ] **步骤 4：验证 Docker API**

运行：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/agentic/health'
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/agentic/agents'
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/agentic/signals'
Invoke-RestMethod -Uri 'http://127.0.0.1:8002/health'
```

预期：Agentic health success；agents 包含 `qlib_agent`；signals 返回数组；Qlib health 为 `online` 或返回可解释的缓存状态。

- [ ] **步骤 5：提交验证结果**

```bash
git status --short
git add .
git commit -m "test: verify agentic platform integration"
```

---

## 10. 最终验收标准

功能验收：

- `/api/agentic/agents` 能列出内置 Agent。
- `/api/agentic/signals` 能列出结构化信号。
- Signal Pool UI 能展示信号、筛选状态、提供观察/回测/加入模拟盘入口。
- 多智能体投研 job 能输出五角色结构化结果。
- Strategy DSL 拒绝 unsafe strategy type 和无止损策略。
- Strategy Lab 能根据回测指标判断是否晋级。
- Paper Bridge 默认只创建需确认的模拟盘意图，不直接下单。
- Agent Performance 能统计信号表现。
- Docker dashboard 正常启动，`8001` 首页和 agentic API 可访问。

风控验收：

- 没有任何 API 允许 AI 直接绕过确认下模拟盘订单。
- 所有进入模拟盘的信号必须先变成 `paper_pending`。
- 自动模拟复制开关默认关闭。
- 所有信号包含 `entry_reasons` 和 `risk_notes`。
- 所有策略 DSL 必须包含 `stop_loss`。

最终测试命令：

```powershell
python -m pytest tests/test_agentic_models.py tests/test_agentic_registry.py tests/test_agentic_repository.py tests/test_agentic_signals.py tests/test_agentic_research_pipeline.py tests/test_agentic_strategy_dsl.py tests/test_agentic_strategy_lab.py tests/test_agentic_promotion_gate.py tests/test_agentic_paper_bridge.py tests/test_agentic_performance.py tests/test_agentic_api.py tests/test_agentic_frontend.py tests/test_paper.py tests/test_api_v2_full.py::TestPaperTrading tests/test_dashboard.py::TestSystemAPI -q
```

---

## 11. 后续高级阶段

本计划完成后，另写计划实现：

1. `Agentic Worker Service`：把 research 和 strategy lab 长任务从 dashboard 拆到 worker。
2. `LLM Provider Router`：按任务类型选择便宜模型/强模型/OpenClaw/本地模型。
3. `Backtest Compiler`：把 Strategy DSL 真正编译到现有 `engine.backtest_engine`。
4. `Paper Copy Rules`：实现自动模拟复制，受 max exposure、daily trades、cooldown 约束。
5. `Agent Scoreboard`：可视化 Agent 排名和近 7/30/90 天表现。
6. `Research Report Export`：导出 Markdown/PDF 投研报告。

## 12. 执行建议

推荐使用 `superpowers:subagent-driven-development`：

- Agent A：模型、repository、registry。
- Agent B：signals、promotion gate、paper bridge。
- Agent C：research pipeline、strategy DSL、strategy lab。
- Agent D：API 和前端。
- 主会话负责整合、测试、Docker 验证和最终提交。

每个阶段完成后都运行相关 pytest，并单独提交。不要跨阶段堆积未提交改动。
