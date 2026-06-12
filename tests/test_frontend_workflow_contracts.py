import subprocess
import shutil
import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_NODE_BIN = ROOT / ".tools/node-bin/node"
RUNTIME_NODE_BIN = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
NODE_BIN = shutil.which("node") or (
    str(REPO_NODE_BIN) if REPO_NODE_BIN.exists() and REPO_NODE_BIN.resolve().exists() else str(RUNTIME_NODE_BIN)
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE_BIN, "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )


def test_stock_detail_clears_stale_header_when_detail_api_fails():
    core = read("dashboard/static/stock-detail-core.js")

    assert "this._renderDetailPending(code, { stock: optionStock, name: optionName });" in core
    assert "_renderDetailUnavailable(code, error)" in core
    assert "本地基础资料暂未覆盖该股票" in core
    assert "this._renderDetailHeader({" in core
    assert "code: safeCode" in core


def test_market_radar_exposes_stable_table_and_stock_name_context():
    radar = read("dashboard/static/overview-radar.js")
    bootstrap = read("dashboard/static/app-bootstrap.js")

    assert 'id="overview-radar-table"' in radar
    assert 'data-testid="overview-radar-table"' in radar
    assert 'data-name="${App.escapeHTML(s.name || \'\')}"' in radar
    assert "const name = typeof link.dataset.name === 'string'" in bootstrap
    assert "name," in bootstrap


def test_data_scope_notes_are_visible_for_research_workbenches():
    template = read("dashboard/templates/index.html")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")

    assert 'id="overview-radar-coverage"' in template
    assert 'id="datahub-scope-note"' in template
    assert 'id="valuation-scope-note"' in template
    assert "当前账号自选，不代表全市场" in datahub
    assert "AI 信号候选池，未验证信号已降权" in datahub
    assert "机构预测 + AI信号覆盖池，不等同全量日线" in valuation
    assert "估值服务全市场扫描，非本地日线全量" in valuation


def test_signal_engine_is_primary_frontend_semantics():
    app = read("dashboard/static/app.js")
    scripts = read("dashboard/templates/partials/scripts.html")
    template = read("dashboard/templates/index.html")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")
    overview = read("dashboard/static/overview.js")
    paper = read("dashboard/static/paper.js")
    manager = read("strategy/manager.py")
    backtest = read("dashboard/routers/backtest.py")
    paper_control = read("dashboard/routers/paper_control.py")
    signal_strategy = read("strategy/qlib_signal.py")
    dashboard_app = read("dashboard/app.py")
    qlib_router = read("dashboard/routers/qlib.py")
    scheduler = read("data/scheduler/scheduler.py")

    assert "/static/intelligence-signals.js?v=20" in app
    assert "/static/intelligence-qlib.js" not in app
    assert "/static/app.js?v=132" in scripts

    assert 'data-ov-opportunity-scope="signal" aria-pressed="true">AI信号 Top</button>' in template
    assert '<option value="signal">AI 信号 Top</option>' in template
    assert '<option value="signal" selected>AI信号覆盖池</option>' in template
    assert '<option value="signal_strategy">AI 信号策略</option>' in template


    assert '<option value="qlib_signal">AI 信号策略</option>' not in template
    assert 'ML 信号策略 (qlib)' not in template
    assert 'title="重新训练 qlib ML 模型"' not in template

    assert "_overviewOpportunityScope: 'signal'" in overview
    assert "scope === 'qlib' ? 'signal' : scope" in overview
    assert "query.set('scope', requestedScope)" in overview
    assert "scope === 'signal'" in datahub
    assert "scope === 'signal'" in valuation
    assert "trainSignalModel" in paper
    assert "globalThis.Paper = Paper" in paper
    assert "开始刷新 AI 信号？" in paper
    assert "AI 信号刷新已启动，请稍后查看结果" in paper
    assert "开始刷新 AI 信号模型" not in paper
    assert "AI 信号模型刷新" not in paper
    assert "训练请求失败" not in paper
    assert "App.fetchJSON('/api/signals/train', { method: 'POST' })" in paper
    assert "App.fetchJSON('/api/signals/train/status')" in paper
    assert "App.fetchJSON('/api/qlib/train'" not in paper
    assert "App.fetchJSON('/api/qlib/train/status')" not in paper
    assert "qlib 训练" not in paper
    assert 'id="pp-train-btn" title="刷新 AI 信号">刷新信号</button>' in template
    assert 'id="ai-train-btn">训练AI模型</button>' in template
    assert "训练ML" not in template
    assert '"name": "signal_strategy"' in manager
    assert '"legacy_alias_for": "signal_strategy"' in manager
    assert "基于 AI 信号分数" in manager
    assert '"type": "信号因子"' in manager
    assert '"需验证"' in manager
    assert '"ML"' not in manager
    assert '"机器学习"' not in manager
    assert "qlib 预测缓存不存在" not in backtest
    assert "qlib 训练" not in backtest
    assert "AI 信号缓存不存在" in backtest
    assert "qlib 服务不可用" not in signal_strategy
    assert "从 qlib 服务加载" not in signal_strategy
    assert "预测分数" not in signal_strategy
    assert "信号分数" in signal_strategy
    assert "AI 信号服务不可用" in signal_strategy
    assert "qlib_signal 需要从 qlib 服务加载预测分数" not in paper_control
    assert '"signal_strategy": QlibSignalStrategy' in paper_control
    assert '"qlib_signal": QlibSignalStrategy' in paper_control
    assert "signal_strategy/qlib_signal 使用 AI 信号服务加载分数" in paper_control
    assert "!s.legacy_alias_for" in read("dashboard/static/backtest-strategies.js")
    assert "!s.legacy_alias_for" in read("dashboard/static/paper-trading.js")
    assert 'tags=["qlib 预测"]' not in dashboard_app
    assert 'tags=["AI 信号兼容接口"]' in dashboard_app
    assert "Qlib 服务健康检查" not in qlib_router
    assert "读取 Qlib 日线覆盖同步状态" not in qlib_router
    assert "读取 Qlib 同步状态失败" not in qlib_router
    assert "计算 Qlib 预测一致性" not in qlib_router
    assert "Qlib 健康检查失败" not in qlib_router
    assert "AI 信号兼容接口健康检查" in qlib_router
    assert "AI 信号一致性" in qlib_router
    assert "Qlib 覆盖池" not in scheduler
    assert "AI 信号覆盖池" in scheduler


def test_overview_datahub_health_surfaces_stock_info_integrity_debt():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const root = { innerHTML: '' };
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'ov-datahub-health' ? root : null,
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));
        App.fetchJSON = async (url) => {
            assert.equal(url, '/api/datahub/health?fast=true');
            return {
                stock_count: 5525,
                stock_daily: { daily_covered: 5525, stock_count: 5525, coverage_pct: 100, latest_date: '2026-06-05', latest_date_covered: 5525 },
                stock_info_integrity: { duplicate_extra_row_count: 318, wrong_prefix_count: 318, merged_blank_industry_count: 0 },
                stock_info_cleanup_preview: { candidate_count: 318, cleanup_ready_count: 0, merge_required_count: 318, skipped_no_canonical_count: 0 },
                full_daily_sync: { status_label: '已完成' },
                quote: { running: false, cache_count: 0, subscriptions: 0 },
                valuation: { coverage_pct: null },
                signal: { status: 'online', cache_age_label: '1小时' },
                shadow: {},
                source_health: { total_active_sources: 2 },
                quality_summary: { total: 0 },
            };
        };

        (async () => {
            await App._loadDataHubHealth();
            assert.match(root.innerHTML, /股票名录/);
            assert.match(root.innerHTML, /5525 · 待清理318/);
            assert.match(root.innerHTML, /名录质量/);
            assert.match(root.innerHTML, /错前缀318 · 需合并318 · 可直删0/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_scope_note_prioritizes_signal_validation_quality():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const note = { innerHTML: '' };
        const scope = { value: 'signal' };

        global.window = global;
        global.document = {
            getElementById: (id) => {
                if (id === 'datahub-scope-note') return note;
                if (id === 'datahub-scope') return scope;
                return null;
            },
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._renderScopeNote({
            total: 10,
            valuation_coverage_pct: 40,
            signal_coverage_pct: 80,
            qlib_coverage_pct: 80,
            signal_quality: {
                label: '未验证',
                sample_days: 0,
                penalty_applied: true,
                message: '历史样本不足，AI信号已降权',
            },
        }, []);

        assert.match(note.innerHTML, /AI信号覆盖 80%/);
        assert.match(note.innerHTML, /未验证/);
        assert.match(note.innerHTML, /已降权/);
        assert.doesNotMatch(note.innerHTML, /Qlib覆盖/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_signal_badge_only_marks_positive_validation():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        const neutral = ResearchDataHub._fmtQlib({
            signal_rank: 12,
            signal_score: 0.612,
            signal_confidence: 'validated_neutral',
            signal_provider: 'local_momentum',
        });
        assert.match(neutral, /验证中性/);
        assert.match(neutral, /本地动量信号/);
        assert.doesNotMatch(neutral, /local_momentum/);
        assert.doesNotMatch(neutral, /datahub-diamond/);
        assert.doesNotMatch(neutral, /已验证/);

        const positive = ResearchDataHub._fmtQlib({
            signal_rank: 3,
            signal_score: 0.912,
            signal_confidence: 'validated_positive',
            signal_provider: 'local_momentum',
        });
        assert.match(positive, /datahub-diamond/);
        assert.match(positive, /验证偏正/);
        assert.doesNotMatch(positive, /已验证/);

        const unverified = ResearchDataHub._fmtQlib({
            signal_rank: 60,
            signal_score: 0.321,
            signal_confidence: 'unverified',
            signal_provider: 'local_momentum',
        });
        assert.match(unverified, /未验证/);
        assert.doesNotMatch(unverified, /datahub-diamond/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_stock_meta_line_compacts_trust_context():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        const meta = ResearchDataHub._stockMetaLine({
            code: '600519',
            industry: '食品饮料',
            quote_source: 'local_stock_daily',
            quote_date: '2026-06-05',
            source: 'local_derived',
            source_version: 'stock_daily+signal+momentum',
            quality_status: 'ok',
            signal_provider: 'local_momentum',
            signal_confidence: 'unverified',
        });

        assert.equal(meta, '600519 · 食品饮料 · 行情 本地日线 2026-06-05 · 估值 本地推导 · AI 未验证');
        assert.doesNotMatch(meta, /local_stock_daily|local_derived|stock_daily\+signal\+momentum|local_momentum/);
        assert.ok(meta.length < 80);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_stock_meta_line_does_not_claim_reports_when_missing():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        const missingReports = ResearchDataHub._stockMetaLine({
            code: '300750',
            quote_source: 'local_stock_daily',
            quote_date: '2026-06-05',
            source: 'astock',
            report_count: 0,
            signal_confidence: 'unverified',
        });
        assert.match(missingReports, /估值 研报缺失/);
        assert.doesNotMatch(missingReports, /估值 研报估值/);

        const coveredReports = ResearchDataHub._stockMetaLine({
            code: '300750',
            quote_source: 'local_stock_daily',
            quote_date: '2026-06-05',
            source: 'astock',
            report_count: 3,
            signal_confidence: 'unverified',
        });
        assert.match(coveredReports, /估值 研报估值/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_risk_cell_separates_data_gaps_from_market_risks():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const handlers = {};
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: (name, handler) => { handlers[name] = handler; },
            dispatchEvent: (event) => {
                if (handlers[event.type]) handlers[event.type](event);
                return true;
            },
            createEvent: () => ({}),
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._render([{
            matrix_rank: 1,
            code: '002475',
            name: '立讯精密',
            decision_score: 69,
            decision_label: '可跟踪',
            risk_level: '高',
            reason_tags: ['PEG合理'],
            risk_tags: ['AI未验证', '无研报预测', '短线破位压力'],
            next_actions: ['加入自选跟踪'],
            signal_rank: 365,
            signal_score: 0.93,
            signal_confidence: 'unverified',
            quote_source: 'local_stock_daily',
            quote_date: '2026-06-05',
            source: 'astock',
            report_count: 0,
        }], { total: 1 });

        assert.match(tbody.innerHTML, /datahub-data-gap-tag[^>]*>AI未验证/);
        assert.match(tbody.innerHTML, /datahub-data-gap-tag[^>]*>无研报预测/);
        assert.match(tbody.innerHTML, /datahub-risk-tag[^>]*>短线破位压力/);
        assert.doesNotMatch(tbody.innerHTML, /datahub-risk-tag[^>]*>AI未验证/);
        assert.doesNotMatch(tbody.innerHTML, /datahub-risk-tag[^>]*>无研报预测/);
        assert.doesNotMatch(tbody.innerHTML, /AI未验证无研报预测/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_risk_cell_surfaces_missing_ai_coverage():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
            dispatchEvent: () => true,
        };
        global.App = { escapeHTML: (value) => String(value ?? '') };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._render([{
            matrix_rank: 1,
            code: '600519',
            name: '贵州茅台',
            decision_score: 52,
            decision_label: '观察',
            risk_level: '中',
            reason_tags: ['PEG合理'],
            risk_tags: ['AI未覆盖'],
            next_actions: ['等待信号覆盖'],
            signal_rank: null,
            signal_score: null,
            quote_source: 'local_stock_daily',
            source: 'astock',
            report_count: 3,
        }], { total: 1 });

        assert.match(tbody.innerHTML, /datahub-data-gap-tag[^>]*>AI未覆盖/);
        assert.match(tbody.innerHTML, /等待信号覆盖/);
        assert.doesNotMatch(tbody.innerHTML, /暂无明显风险/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_next_actions_are_grouped_by_workflow_intent():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._render([{
            matrix_rank: 1,
            code: '300750',
            name: '宁德时代',
            decision_score: 85,
            decision_label: '重点研究',
            risk_level: '中',
            reason_tags: ['PEG≤1'],
            risk_tags: [],
            next_actions: ['补看同业估值', '继续观察', '模拟小仓验证', '问龙虾生成交易计划'],
            signal_rank: 953,
            signal_score: 0.817,
            signal_confidence: 'validated_neutral',
        }], {
            total: 1,
            valuation_coverage_pct: 100,
            signal_coverage_pct: 100,
            signal_status: 'fresh',
            signal_quality: { label: '验证中性', sample_days: 30, penalty_applied: false },
        });

        assert.match(tbody.innerHTML, /datahub-action-tag action-data[^>]*>补看同业估值/);
        assert.match(tbody.innerHTML, /datahub-action-tag action-watch[^>]*>继续观察/);
        assert.match(tbody.innerHTML, /datahub-action-tag action-trade[^>]*>模拟小仓验证/);
        assert.match(tbody.innerHTML, /datahub-action-tag action-research[^>]*>问龙虾生成交易计划/);
        assert.doesNotMatch(tbody.innerHTML, /datahub-next-tag/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_trust_panel_matches_overview_semantics_for_low_coverage():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                className: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-trust': makeElement('datahub-trust'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._render([{
            matrix_rank: 1,
            code: '300750',
            name: '宁德时代',
            decision_score: 88,
            decision_label: '可跟踪',
            risk_level: '中',
            reason_tags: ['AI候选'],
            risk_tags: ['AI未验证'],
            next_actions: ['打开完整矩阵'],
            signal_rank: 1,
            signal_score: 0.99,
            signal_confidence: 'unverified',
        }], {
            total: 8,
            valuation_coverage_pct: 0,
            signal_coverage_pct: 100,
            signal_status: 'fresh',
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
            fast_mode: true,
        });

        assert.match(elements['datahub-trust'].innerHTML, /需复核/);
        assert.match(elements['datahub-trust'].innerHTML, /估值覆盖不足/);
        assert.match(elements['datahub-trust'].innerHTML, /信号未验证/);
        assert.match(elements['datahub-trust'].className, /trust-review/);
        assert.doesNotMatch(elements['datahub-trust'].className, /trust-real/);
        assert.match(elements['datahub-scope-note'].innerHTML, /AI信号覆盖 100%/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_low_trust_rows_hide_paper_trade_action():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                className: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-trust': makeElement('datahub-trust'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        const item = {
            matrix_rank: 1,
            code: '300750',
            name: '宁德时代',
            decision_score: 88,
            decision_label: '重点研究',
            risk_level: '中',
            reason_tags: ['AI候选'],
            risk_tags: ['AI未验证'],
            next_actions: ['模拟小仓验证', '问龙虾生成交易计划'],
            signal_rank: 1,
            signal_score: 0.99,
            signal_confidence: 'unverified',
        };

        ResearchDataHub._render([item], {
            total: 1,
            valuation_coverage_pct: 0,
            signal_coverage_pct: 100,
            signal_status: 'fresh',
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
        });
        assert.match(elements['datahub-trust'].innerHTML, /需复核/);
        assert.doesNotMatch(tbody.innerHTML, /data-datahub-action="paper"/);
        assert.doesNotMatch(tbody.innerHTML, /模拟小仓验证/);
        assert.doesNotMatch(tbody.innerHTML, /问龙虾生成交易计划/);
        assert.match(tbody.innerHTML, /data-datahub-action="ask"/);

        ResearchDataHub._render([{
            ...item,
            signal_confidence: 'validated_neutral',
            risk_tags: [],
        }], {
            total: 1,
            valuation_coverage_pct: 100,
            signal_coverage_pct: 100,
            signal_status: 'fresh',
            signal_quality: { label: '验证中性', sample_days: 30, penalty_applied: false },
        });
        assert.match(elements['datahub-trust'].innerHTML, /真实合成/);
        assert.match(tbody.innerHTML, /data-datahub-action="paper"/);
        assert.match(tbody.innerHTML, /模拟小仓验证/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_trust_panel_marks_default_fallback_and_real_data():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const trust = { innerHTML: '', className: '' };
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'datahub-trust' ? trust : null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._renderTrust({
            used_fallback: true,
            fallback_reason: 'client_timeout_default',
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
        });
        assert.match(trust.innerHTML, /降级预览/);
        assert.match(trust.innerHTML, /默认候选/);
        assert.match(trust.className, /trust-fallback/);

        ResearchDataHub._renderTrust({
            used_fallback: true,
            fallback_reason: 'watchlist_empty',
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
        });
        assert.match(trust.innerHTML, /默认候选/);
        assert.match(trust.innerHTML, /自选股为空/);
        assert.match(trust.innerHTML, /不是自选结果/);
        assert.match(trust.className, /trust-fallback/);

        ResearchDataHub._renderTrust({
            valuation_coverage_pct: 100,
            signal_coverage_pct: 100,
            signal_status: 'fresh',
            signal_quality: { label: '验证中性', sample_days: 30, penalty_applied: false },
        });
        assert.match(trust.innerHTML, /真实合成/);
        assert.match(trust.innerHTML, /可进入估值或模拟盘复核/);
        assert.match(trust.className, /trust-real/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_openclaw_prompt_keeps_signal_trust_boundary():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        let activeTab = '';
        const sent = [];
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            switchTab: async (tab) => { activeTab = tab; },
        };
        global.OpenClawWorkbench = {
            maybeInitForTab: async () => {},
            send: async (prompt) => { sent.push(prompt); },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._items = [{
            code: '300750',
            name: '宁德时代',
            decision_score: 74,
            decision_label: '可跟踪',
            peg_next_year: 0.82,
            growth_next_year_pct: 35,
            upside_pct: 18,
            signal_rank: 2,
            signal_score: 0.998,
            signal_provider: 'local_momentum',
            signal_confidence: 'unverified',
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
            risk_tags: ['AI未验证'],
        }];

        (async () => {
            await ResearchDataHub._askOpenClaw('300750');
            assert.equal(activeTab, 'openclaw');
            assert.equal(sent.length, 1);
            const prompt = sent[0];
            assert.match(prompt, /AI未验证/);
            assert.match(prompt, /样本 0 天/);
            assert.match(prompt, /已降权/);
            assert.match(prompt, /本地动量信号/);
            assert.match(prompt, /仅供观察/);
            assert.match(prompt, /不要给实盘下单建议/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_visible_labels_describe_signals_not_predictions():
    template = read("dashboard/templates/index.html")
    datahub_panel = template[
        template.index('id="research-panel-datahub"') : template.index(
            'id="research-panel-valuation"'
        )
    ]

    assert "AI预测" not in datahub_panel
    assert "AI Top50" not in datahub_panel
    assert "AI覆盖" not in datahub_panel
    assert "AI信号" in datahub_panel
    assert "信号Top50" in datahub_panel
    assert "信号覆盖" in datahub_panel
    assert 'id="datahub-trust"' in datahub_panel


def test_research_datahub_empty_watchlist_stops_before_default_candidates():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'watchlist' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-trust': makeElement('datahub-trust'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        const calls = [];
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async (url) => {
                calls.push(url);
                if (url === '/api/watchlist') return [];
                throw new Error(`decision matrix should not be requested: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        (async () => {
            await ResearchDataHub.load();
            assert.deepEqual(calls, ['/api/watchlist']);
            assert.deepEqual(ResearchDataHub._items, []);
            assert.match(tbody.innerHTML, /自选股为空/);
            assert.match(tbody.innerHTML, /AI 信号 Top/);
            assert.match(tbody.innerHTML, /指定股票/);
            assert.match(tbody.innerHTML, /data-datahub-empty-action="signal"/);
            assert.match(tbody.innerHTML, /data-datahub-empty-action="codes"/);
            assert.match(elements['datahub-scope-note'].innerHTML, /自选股为空/);
            assert.match(elements['datahub-trust'].innerHTML, /等待自选/);
            assert.match(elements['datahub-trust'].innerHTML, /没有使用默认候选/);
            assert.match(elements['datahub-trust'].className, /trust-empty/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_fast_timeout_falls_back_to_full_matrix():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        const calls = [];
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('/api/datahub/decision-matrix') && url.includes('fast=true')) {
                    throw new Error('请求超时');
                }
                if (url.includes('/api/datahub/decision-matrix')) {
                    return {
                        success: true,
                        items: [{
                            matrix_rank: 1,
                            code: '300750',
                            name: '宁德时代',
                            decision_score: 88,
                            decision_label: '补载成功',
                            risk_level: '低',
                            reason_tags: ['完整估值'],
                            risk_tags: [],
                            next_actions: ['打开估值详情'],
                            signal_rank: 8,
                            signal_score: 0.91,
                            signal_confidence: 'validated_neutral',
                        }],
                        summary: {
                            total: 1,
                            valuation_coverage_pct: 100,
                            signal_coverage_pct: 100,
                            signal_date: '2026-06-05',
                            signal_quality: { label: '验证中性', sample_days: 259, penalty_applied: false },
                        },
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        (async () => {
            await ResearchDataHub.load();
            assert.equal(calls.length, 2);
            assert.match(calls[0], /fast=true/);
            assert.match(calls[1], /max_wait_sec=6/);
            assert.doesNotMatch(calls[1], /fast=true/);
            assert.match(tbody.innerHTML, /补载成功/);
            assert.doesNotMatch(tbody.innerHTML, /加载失败/);
            assert.match(elements['datahub-scope-note'].innerHTML, /AI信号覆盖 100%/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_full_timeout_preserves_previous_matrix_rows():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'signal' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        tbody.innerHTML = '<tr><td>旧机会</td></tr>';
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        const calls = [];
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async (url) => {
                calls.push(url);
                throw new Error('请求超时');
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));
        ResearchDataHub._items = [{ code: '300750', name: '宁德时代' }];
        ResearchDataHub._matrixResultKey = 'signal|';

        (async () => {
            await ResearchDataHub.load();
            const matrixCalls = calls.filter((url) => url.includes('/api/datahub/decision-matrix'));
            assert.equal(matrixCalls.length, 3);
            assert.match(matrixCalls[0], /fast=true/);
            assert.match(matrixCalls[1], /max_wait_sec=6/);
            assert.match(matrixCalls[2], /force_fallback=true/);
            assert.match(tbody.innerHTML, /旧机会/);
            assert.doesNotMatch(tbody.innerHTML, /加载失败/);
            assert.match(elements['datahub-scope-note'].innerHTML, /刷新超时/);
            assert.match(elements['datahub-scope-note'].innerHTML, /保留上次结果/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_full_timeout_uses_labeled_default_candidates_without_previous_rows():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'watchlist' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
            'datahub-total': makeElement('datahub-total'),
            'datahub-high-score': makeElement('datahub-high-score'),
            'datahub-cheap': makeElement('datahub-cheap'),
            'datahub-qlib-top': makeElement('datahub-qlib-top'),
            'datahub-valuation-cov': makeElement('datahub-valuation-cov'),
            'datahub-qlib-cov': makeElement('datahub-qlib-cov'),
            'datahub-actionable': makeElement('datahub-actionable'),
            'datahub-high-risk': makeElement('datahub-high-risk'),
            'datahub-pipe-quote': makeElement('datahub-pipe-quote'),
            'datahub-pipe-valuation': makeElement('datahub-pipe-valuation'),
            'datahub-pipe-ai': makeElement('datahub-pipe-ai'),
            'datahub-pipe-shadow': makeElement('datahub-pipe-shadow'),
            'datahub-source-health': makeElement('datahub-source-health'),
            'datahub-quality-summary': makeElement('datahub-quality-summary'),
            'datahub-shadow-summary': makeElement('datahub-shadow-summary'),
            'datahub-version-summary': makeElement('datahub-version-summary'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        const calls = [];
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('force_fallback=true')) {
                    return {
                        items: [{
                            matrix_rank: 1,
                            code: '600519',
                            name: '贵州茅台',
                            decision_score: 61,
                            decision_label: '降级预览',
                            risk_level: '中',
                            reason_tags: ['默认候选'],
                            risk_tags: ['数据源超时'],
                            next_actions: ['稍后刷新'],
                        }],
                        summary: {
                            total: 1,
                            used_fallback: true,
                            fallback_reason: 'client_timeout_default',
                            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                        },
                    };
                }
                throw new Error('请求超时');
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        (async () => {
            await ResearchDataHub.load();
            const matrixCalls = calls.filter((url) => url.includes('/api/datahub/decision-matrix'));
            assert.equal(matrixCalls.length, 3);
            assert.match(matrixCalls[2], /force_fallback=true/);
            assert.match(tbody.innerHTML, /贵州茅台/);
            assert.doesNotMatch(tbody.innerHTML, /加载失败/);
            assert.match(elements['datahub-scope-note'].innerHTML, /默认候选/);
            assert.match(elements['datahub-scope-note'].innerHTML, /降级预览/);
            assert.match(elements['datahub-scope-note'].innerHTML, /请求范围 自选股/);
            assert.match(elements['datahub-scope-note'].innerHTML, /样本来源 默认候选/);
            assert.doesNotMatch(elements['datahub-scope-note'].innerHTML, />范围 自选股</);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_does_not_preserve_rows_after_scope_change():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: id === 'datahub-scope' ? 'codes' : '',
                innerHTML: '',
                textContent: '',
                dataset: {},
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const table = makeElement('datahub-matrix-table');
        const tbody = makeElement('datahub-matrix-tbody');
        tbody.innerHTML = '<tr><td>旧自选机会</td></tr>';
        table.querySelector = (selector) => selector === 'tbody' ? tbody : null;
        const elements = {
            'datahub-matrix-table': table,
            'datahub-scope': makeElement('datahub-scope'),
            'datahub-scope-note': makeElement('datahub-scope-note'),
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async () => { throw new Error('请求超时'); },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));
        ResearchDataHub._items = [{ code: '300750', name: '宁德时代' }];
        ResearchDataHub._matrixResultKey = 'watchlist|';
        ResearchDataHub._selected = [{ code: '600519', name: '贵州茅台' }];

        (async () => {
            await ResearchDataHub.load();
            assert.doesNotMatch(tbody.innerHTML, /旧自选机会/);
            assert.match(tbody.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_datahub_stale_fallback_failure_does_not_overwrite_new_request():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const note = { innerHTML: '新请求状态' };
        const tbody = { innerHTML: '<tr><td>新请求结果</td></tr>' };
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'datahub-scope-note' ? note : null,
            querySelector: (selector) => selector === '#datahub-matrix-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            watchlistCache: [{ code: '300750' }],
            fetchJSON: async () => { throw new Error('请求超时'); },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));
        ResearchDataHub._matrixActiveScope = 'watchlist';
        ResearchDataHub._matrixRequestId = 2;
        ResearchDataHub._items = [{ code: '300750', name: '宁德时代' }];
        ResearchDataHub._matrixResultKey = 'signal|';

        (async () => {
            await ResearchDataHub._loadFallbackMatrix('signal', '', 1, new Error('请求超时'), true);
            assert.equal(note.innerHTML, '新请求状态');
            assert.match(tbody.innerHTML, /新请求结果/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_paper_buy_defaults_to_trade_subtab_and_focuses_order_form():
    adapter = read("dashboard/static/core/business-adapter.js")

    assert "const PAPER_SUB_TAB_CANDIDATES = Object.freeze(['trade', 'console']);" in adapter
    assert "payload.activeTab = payload.activeTab || 'trade';" in adapter
    assert "document.getElementById('pt-order-form')?.scrollIntoView" in adapter


def test_open_stock_detail_direct_mode_resolves_before_slow_detail_load():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let switchedTab = null;
        let syncedCode = null;
        let openCalls = 0;

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async (tab) => { switchedTab = tab; },
            syncActiveStockContext: (code) => { syncedCode = code; },
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async () => {
                openCalls += 1;
                await new Promise(() => {});
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        const timeout = new Promise((resolve) => {
            setTimeout(() => resolve({ ok: false, status: 'timeout' }), 25);
        });
        const result = await Promise.race([
            global.App.openStockDetail('600519', {
                source: 'frontend-contract-test',
                preferDirectOpen: true,
            }),
            timeout,
        ]);

        assert.equal(result.ok, true);
        assert.equal(result.status, 'direct');
        assert.equal(result.code, '600519');
        assert.equal(switchedTab, 'stock');
        assert.equal(syncedCode, '600519');
        assert.equal(openCalls, 1);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_stock_detail_can_explicitly_wait_for_detail_load():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let resolveDetail;
        let openCalls = 0;

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async () => {},
            syncActiveStockContext: () => {},
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async () => {
                openCalls += 1;
                await new Promise((resolve) => { resolveDetail = resolve; });
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        let settled = false;
        const pending = global.App.openStockDetail('600519', {
            source: 'frontend-contract-test',
            preferDirectOpen: true,
            awaitDetailLoad: true,
        }).then((result) => {
            settled = true;
            return result;
        });

        await new Promise((resolve) => setTimeout(resolve, 25));
        assert.equal(settled, false);
        assert.equal(openCalls, 1);

        resolveDetail();
        const result = await pending;
        assert.equal(settled, true);
        assert.equal(result.ok, true);
        assert.equal(result.status, 'direct');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_detail_open_scrolls_workbench_into_view():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let scrollCalls = 0;
        let scrollOptions = null;
        const content = {
            id: 'sd-content',
            style: { display: 'none' },
            classList: { toggle: () => {} },
            setAttribute: () => {},
            scrollIntoView: (options) => {
                scrollCalls += 1;
                scrollOptions = options;
            },
        };
        const placeholder = { id: 'sd-placeholder', style: { display: '' } };

        global.window = global;
        global.App = {
            watchlistCache: [],
            fetchJSON: async () => ({}),
            toast: () => {},
        };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => {
                if (id === 'sd-content') return content;
                if (id === 'sd-placeholder') return placeholder;
                return null;
            },
            querySelector: () => null,
        };
        global.StockDetail = { _openGeneration: 0 };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        Object.assign(global.StockDetail, {
            _renderDetailPending: () => {},
            _connectL2: () => {},
            _loadDetail: async () => {},
            _loadTimeline: async () => {},
            _loadOrderBook: async () => {},
            _loadPeriodReturns: async () => {},
            _loadCapitalFlow: async () => {},
            _loadProfitTrend: async () => {},
            _loadShareholders: async () => {},
            _loadDividends: async () => {},
            _loadAnnouncements: async () => {},
            _loadIndustryComparison: async () => {},
            _loadNorthbound: async () => {},
            _loadChips: async () => {},
            _loadMultiTimeframe: async () => {},
            _loadDragonTiger: async () => {},
            _loadReports: async () => {},
            _loadValuationSnapshot: async () => {},
            _loadAlphaSignals: async () => {},
            _loadNews: async () => {},
        });

        await global.StockDetail.open('600396', {
            stock: { code: '600396', name: '华电辽能' },
            source: 'overview:opportunity',
        });

        assert.equal(content.style.display, '');
        assert.equal(placeholder.style.display, 'none');
        assert.equal(scrollCalls, 1);
        assert.deepEqual(scrollOptions, { block: 'start', inline: 'nearest' });
        assert.equal(global.StockDetail._openGeneration, 1);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_workbench_state_initializes_from_open_context():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const content = {
            id: 'sd-content',
            style: { display: 'none' },
            classList: { toggle: () => {} },
            setAttribute: () => {},
            scrollIntoView: () => {},
        };
        const placeholder = { id: 'sd-placeholder', style: { display: '' } };

        global.window = global;
        global.App = {
            watchlistCache: [],
            fetchJSON: async () => ({}),
            toast: () => {},
        };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => {
                if (id === 'sd-content') return content;
                if (id === 'sd-placeholder') return placeholder;
                return null;
            },
            querySelector: () => null,
        };
        global.StockDetail = { _openGeneration: 0, _currentPeriod: 'timeline', _currentIndicator: '' };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        Object.assign(global.StockDetail, {
            _renderDetailPending: () => {},
            _connectL2: () => {},
            _loadDetail: async () => {},
            _loadTimeline: async () => {},
            _loadOrderBook: async () => {},
            _loadPeriodReturns: async () => {},
            _loadCapitalFlow: async () => {},
            _loadProfitTrend: async () => {},
            _loadShareholders: async () => {},
            _loadDividends: async () => {},
            _loadAnnouncements: async () => {},
            _loadIndustryComparison: async () => {},
            _loadNorthbound: async () => {},
            _loadChips: async () => {},
            _loadMultiTimeframe: async () => {},
            _loadDragonTiger: async () => {},
            _loadReports: async () => {},
            _loadValuationSnapshot: async () => {},
            _loadAlphaSignals: async () => {},
            _loadNews: async () => {},
        });

        await global.StockDetail.open('600396', {
            stock: { code: '600396', name: '华电辽能' },
            source: 'market:sector-heatmap',
            sourceLabel: '板块',
            context_type: 'sector',
            sector_name: '电力',
            rank_reason: '领涨成分股',
            query: '电力板块',
            contextList: [
                { code: '600396', name: '华电辽能', sourceLabel: '板块' },
                { code: '600000', name: '浦发银行', sourceLabel: '板块' },
            ],
        });

        const state = global.App.StockWorkbenchState;
        assert.equal(state.selectedSymbol.code, '600396');
        assert.equal(state.selectedSymbol.name, '华电辽能');
        assert.equal(state.selectedSymbol.asset_type, 'stock');
        assert.equal(state.sourceContext.source, 'market:sector-heatmap');
        assert.equal(state.sourceContext.sourceLabel, '板块');
        assert.equal(state.sourceContext.context_type, 'sector');
        assert.equal(state.sourceContext.sector_name, '电力');
        assert.equal(state.sourceContext.rank_reason, '领涨成分股');
        assert.equal(state.contextList.length, 2);
        assert.equal(state.chartState.period, 'timeline');
        assert.equal(state.chartState.adjust, 'qfq');
        assert.deepEqual(state.indicatorState.main, ['MA']);
        assert.deepEqual(state.indicatorState.sub, ['VOL']);
        assert.equal(state.layoutState.railTab, 'profile');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_chart_period_and_indicator_update_workbench_state_without_losing_context():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let indicatorHandler = null;
        const select = {
            value: '',
            addEventListener: (event, handler) => {
                if (event === 'change') indicatorHandler = handler;
            },
        };
        const tabs = [
            { dataset: { period: 'timeline' }, classList: { toggle: () => {} }, setAttribute: () => {} },
            { dataset: { period: 'weekly' }, classList: { toggle: () => {} }, setAttribute: () => {} },
        ];

        global.window = global;
        global.App = {
            StockWorkbenchState: {
                selectedSymbol: { code: '600396', name: '华电辽能', asset_type: 'stock' },
                sourceContext: { source: 'overview:opportunity', sourceLabel: 'AI信号' },
                contextList: [{ code: '600396', name: '华电辽能' }],
            },
            fetchJSON: async () => ({ klines: [{ timestamp: 1, open: 1, high: 1, low: 1, close: 1, volume: 1 }] }),
        };
        global.document = {
            getElementById: (id) => id === 'sd-indicator-select' ? select : null,
            querySelectorAll: () => tabs,
            querySelector: () => null,
        };
        global.StockDetail = {
            _openGeneration: 0,
            _currentCode: '600396',
            _currentPeriod: 'timeline',
            _currentIndicator: '',
            _currentKlines: [{ timestamp: 1 }],
            _indicatorPaneId: null,
            _klineChart: {
                createIndicator: (name) => `pane-${name}`,
                removeIndicator: () => {},
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-kline.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-timeline.js', 'utf8'));

        global.StockDetail._renderKlineChart = (klines) => { global.StockDetail._currentKlines = klines; };
        global.StockDetail._loadDrawings = () => {};

        await global.StockDetail._loadKline('600396', 'weekly');
        assert.equal(global.App.StockWorkbenchState.chartState.period, 'weekly');
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');
        assert.equal(global.App.StockWorkbenchState.contextList[0].code, '600396');

        global.StockDetail._bindIndicatorSelector();
        assert.equal(typeof indicatorHandler, 'function');
        select.value = 'MACD';
        indicatorHandler();

        assert.equal(global.App.StockWorkbenchState.indicatorState.active, 'MACD');
        assert.deepEqual(global.App.StockWorkbenchState.indicatorState.main, ['MA']);
        assert.deepEqual(global.App.StockWorkbenchState.indicatorState.sub, ['VOL', 'MACD']);
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');
        assert.equal(global.App.StockWorkbenchState.chartState.period, 'weekly');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_chart_state_persists_research_lens_to_session_storage():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let indicatorHandler = null;
        const storage = {
            key: '',
            value: '',
            getItem: () => storage.value,
            setItem: (key, value) => {
                storage.key = key;
                storage.value = value;
            },
        };
        const select = {
            value: '',
            addEventListener: (event, handler) => {
                if (event === 'change') indicatorHandler = handler;
            },
        };
        const tabs = [
            { dataset: { period: 'timeline' }, classList: { toggle: () => {} }, setAttribute: () => {} },
            { dataset: { period: 'weekly' }, classList: { toggle: () => {} }, setAttribute: () => {} },
        ];

        global.window = global;
        global.sessionStorage = storage;
        global.App = {
            _accountState: { workspace: { id: 'qa-workspace' } },
            StockWorkbenchState: {
                selectedSymbol: { code: '600396', name: '华电辽能', asset_type: 'stock' },
                sourceContext: { source: 'overview:opportunity', sourceLabel: 'AI信号' },
                contextList: [{ code: '600396', name: '华电辽能' }],
            },
            fetchJSON: async () => ({ klines: [{ timestamp: 1, open: 1, high: 1, low: 1, close: 1, volume: 1 }] }),
        };
        global.document = {
            getElementById: (id) => id === 'sd-indicator-select' ? select : null,
            querySelectorAll: () => tabs,
            querySelector: () => null,
        };
        global.StockDetail = {
            _openGeneration: 0,
            _currentCode: '600396',
            _currentPeriod: 'timeline',
            _currentIndicator: '',
            _currentKlines: [{ timestamp: 1 }],
            _indicatorPaneId: null,
            _klineChart: {
                createIndicator: (name) => `pane-${name}`,
                removeIndicator: () => {},
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-kline.js', 'utf8'));

        global.StockDetail._renderKlineChart = (klines) => { global.StockDetail._currentKlines = klines; };
        global.StockDetail._loadDrawings = () => {};

        await global.StockDetail._loadKline('600396', 'weekly');
        global.StockDetail._bindIndicatorSelector();
        select.value = 'MACD';
        indicatorHandler();

        assert.equal(storage.key, 'stock_workbench_state:qa-workspace');
        const stored = JSON.parse(storage.value);
        assert.equal(stored.chartState.period, 'weekly');
        assert.equal(stored.indicatorState.active, 'MACD');
        assert.deepEqual(stored.indicatorState.sub, ['VOL', 'MACD']);
        assert.equal(global.StockDetail._currentIndicator, 'MACD');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_open_restores_persisted_period_and_indicator_for_next_symbol():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const storage = {
            value: JSON.stringify({
                chartState: { period: 'weekly', adjust: 'qfq' },
                indicatorState: { main: ['MA'], sub: ['VOL', 'MACD'], active: 'MACD' },
                layoutState: { leftOpen: true, rightOpen: true, bottomTab: 'events', railTab: 'profile' },
            }),
            getItem: () => storage.value,
            setItem: (key, value) => {
                storage.key = key;
                storage.value = value;
            },
        };
        const content = {
            id: 'sd-content',
            style: { display: 'none' },
            classList: { toggle: () => {} },
            setAttribute: () => {},
            scrollIntoView: () => {},
        };
        const placeholder = { id: 'sd-placeholder', style: { display: '' } };
        let loadedKline = null;
        let loadedTimeline = false;

        global.window = global;
        global.sessionStorage = storage;
        global.App = {
            _accountState: { workspace: { id: 'qa-workspace' } },
            watchlistCache: [],
            _stockContextItems: [
                { code: '600726', name: '华电能源', sourceLabel: 'AI信号', rank_reason: '左栏当前选中' },
                { code: '600396', name: '华电辽能', sourceLabel: 'AI信号', rank_reason: '同池候选' },
            ],
            fetchJSON: async () => ({}),
            toast: () => {},
        };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => {
                if (id === 'sd-content') return content;
                if (id === 'sd-placeholder') return placeholder;
                return null;
            },
            querySelector: () => null,
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail.js', 'utf8'));
        assert.equal(global.StockDetail._currentPeriod, 'daily');
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        Object.assign(global.StockDetail, {
            _renderDetailPending: () => {},
            _connectL2: () => {},
            _loadDetail: async () => {},
            _loadTimeline: async () => { loadedTimeline = true; },
            _loadKline: async (code, period) => { loadedKline = { code, period, indicator: global.StockDetail._currentIndicator }; },
            _loadOrderBook: async () => {},
            _loadPeriodReturns: async () => {},
            _loadCapitalFlow: async () => {},
            _loadProfitTrend: async () => {},
            _loadShareholders: async () => {},
            _loadDividends: async () => {},
            _loadAnnouncements: async () => {},
            _loadIndustryComparison: async () => {},
            _loadNorthbound: async () => {},
            _loadChips: async () => {},
            _loadMultiTimeframe: async () => {},
            _loadDragonTiger: async () => {},
            _loadReports: async () => {},
            _loadValuationSnapshot: async () => {},
            _loadAlphaSignals: async () => {},
            _loadNews: async () => {},
        });

        await global.StockDetail.open('600726', {
            stock: { code: '600726', name: '华电能源' },
            source: 'overview:opportunity',
            sourceLabel: 'AI信号',
            contextList: [
                { code: '600396', name: '华电辽能', sourceLabel: 'AI信号' },
                { code: '600726', name: '华电能源', sourceLabel: 'AI信号' },
            ],
        });

        assert.equal(loadedTimeline, false);
        assert.deepEqual(loadedKline, { code: '600726', period: 'weekly', indicator: 'MACD' });
        assert.equal(global.App.StockWorkbenchState.selectedSymbol.code, '600726');
        assert.equal(global.App.StockWorkbenchState.chartState.period, 'weekly');
        assert.equal(global.App.StockWorkbenchState.indicatorState.active, 'MACD');
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');
        assert.equal(global.App.StockWorkbenchState.contextList[0].code, '600726');
        assert.equal(global.App.StockWorkbenchState.contextList[0].rank_reason, '左栏当前选中');
        assert.equal(global.App.StockWorkbenchState.contextList[1].code, '600396');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_detail_refresh_preserves_source_context():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const content = {
            id: 'sd-content',
            style: { display: 'none' },
            classList: { toggle: () => {} },
            setAttribute: () => {},
            scrollIntoView: () => {},
        };
        const placeholder = { id: 'sd-placeholder', style: { display: '' } };

        global.window = global;
        global.App = {
            watchlistCache: [],
            fetchJSON: async () => ({}),
            toast: () => {},
        };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => {
                if (id === 'sd-content') return content;
                if (id === 'sd-placeholder') return placeholder;
                return null;
            },
            querySelector: () => null,
        };
        global.StockDetail = { _openGeneration: 0, _currentPeriod: 'timeline', _currentIndicator: '' };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        Object.assign(global.StockDetail, {
            _renderDetailPending: () => {},
            _connectL2: () => {},
            _loadDetail: async () => {},
            _loadTimeline: async () => {},
            _loadOrderBook: async () => {},
            _loadPeriodReturns: async () => {},
            _loadCapitalFlow: async () => {},
            _loadProfitTrend: async () => {},
            _loadShareholders: async () => {},
            _loadDividends: async () => {},
            _loadAnnouncements: async () => {},
            _loadIndustryComparison: async () => {},
            _loadNorthbound: async () => {},
            _loadChips: async () => {},
            _loadMultiTimeframe: async () => {},
            _loadDragonTiger: async () => {},
            _loadReports: async () => {},
            _loadValuationSnapshot: async () => {},
            _loadAlphaSignals: async () => {},
            _loadNews: async () => {},
        });

        await global.StockDetail.open('600396', {
            stock: { code: '600396', name: '华电辽能' },
            source: 'overview:opportunity',
            sourceLabel: 'AI信号',
            rank_reason: '数据机会池第 1 名',
            query: '机会池',
            contextList: [{ code: '600396', name: '华电辽能', sourceLabel: 'AI信号' }],
        });
        assert.equal(global.App.StockWorkbenchState.sourceContext.source, 'overview:opportunity');
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');

        await global.StockDetail.refresh();

        assert.equal(global.App.StockWorkbenchState.sourceContext.source, 'overview:opportunity');
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');
        assert.equal(global.App.StockWorkbenchState.sourceContext.rank_reason, '数据机会池第 1 名');
        assert.equal(global.App.StockWorkbenchState.sourceContext.query, '机会池');
        assert.equal(global.App.StockWorkbenchState.selectedSymbol.code, '600396');
        assert.equal(global.StockDetail._sourceContext.sourceLabel, 'AI信号');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_chart_state_changes_keep_evidence_rail_content():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let indicatorHandler = null;
        const makeElement = (id) => ({
            id,
            textContent: '',
            innerHTML: '',
            className: '',
            style: {},
            dataset: {},
            addEventListener: (event, handler) => {
                if (id === 'sd-indicator-select' && event === 'change') indicatorHandler = handler;
            },
            classList: { toggle: () => {} },
            setAttribute: () => {},
        });
        const elements = Object.fromEntries([
            'sd-header',
            'sd-name',
            'sd-code',
            'sd-price',
            'sd-change',
            'sd-industry',
            'sd-sector',
            'sd-concepts',
            'sd-positioning',
            'sd-trust-strip',
            'stock-evidence-rail',
            'sd-indicator-select',
        ].map((id) => [id, makeElement(id)]));
        elements['sd-indicator-select'].value = '';
        const tabs = [
            { dataset: { period: 'timeline' }, classList: { toggle: () => {} }, setAttribute: () => {} },
            { dataset: { period: 'weekly' }, classList: { toggle: () => {} }, setAttribute: () => {} },
        ];

        global.window = global;
        global.globalThis = global;
        global.App = {
            fetchJSON: async () => ({ klines: [{ timestamp: 1, open: 1, high: 1, low: 1, close: 1, volume: 1 }] }),
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#tab-stock .stock-detail-header' ? elements['sd-header'] : null,
            querySelectorAll: () => tabs,
            createElement: (tag) => makeElement(tag),
        };
        global.StockDetail = {
            _openGeneration: 0,
            _currentCode: '600396',
            _currentPeriod: 'timeline',
            _currentIndicator: '',
            _currentKlines: [{ timestamp: 1 }],
            _indicatorPaneId: null,
            _sourceContext: {
                source: 'overview:opportunity',
                sourceLabel: 'AI信号',
                rank_reason: '数据机会池第 1 名',
            },
            _klineChart: {
                createIndicator: (name) => `pane-${name}`,
                removeIndicator: () => {},
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-kline.js', 'utf8'));

        global.StockDetail._renderKlineChart = (klines) => { global.StockDetail._currentKlines = klines; };
        global.StockDetail._loadDrawings = () => {};

        global.StockDetail._renderDetailHeader({
            code: '600396',
            name: '华电辽能',
            price: 19.11,
            industry: '电力',
            main_business: '电力、热力生产和供应业',
            description: '长资料正文应留在证据栏。',
            peg_next_year: 0.74,
            ai_coverage: { covered: false, reason: 'AI 未验证原因' },
            signal_coverage: { covered: false, reason: 'Signal 未验证原因' },
        });
        const beforeRail = elements['stock-evidence-rail'].innerHTML;
        assert.match(beforeRail, /AI信号/);
        assert.match(beforeRail, /数据机会池第 1 名/);
        assert.match(beforeRail, /长资料正文应留在证据栏/);

        await global.StockDetail._loadKline('600396', 'weekly');
        global.StockDetail._bindIndicatorSelector();
        elements['sd-indicator-select'].value = 'MACD';
        indicatorHandler();

        const afterRail = elements['stock-evidence-rail'].innerHTML;
        assert.match(afterRail, /AI信号/);
        assert.match(afterRail, /数据机会池第 1 名/);
        assert.match(afterRail, /长资料正文应留在证据栏/);
        assert.match(afterRail, /AI 未验证/);
        assert.equal(global.App.StockWorkbenchState.chartState.period, 'weekly');
        assert.equal(global.App.StockWorkbenchState.indicatorState.active, 'MACD');
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, 'AI信号');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_business_adapter_open_stock_detail_uses_nonblocking_direct_open():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let receivedOptions = null;

        global.window = global;
        global.document = {
            querySelector: () => null,
            getElementById: () => null,
        };
        global.StockDetail = {
            open: async () => {},
            init: () => {},
        };
        global.App = {
            _activeStockCode: '',
            ensureBundle: async () => {},
            openStockDetail: async (code, options) => {
                receivedOptions = { code, ...options };
                return { ok: true, code };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/business-adapter.js', 'utf8'));

        (async () => {
            const result = await global.BusinessAdapter.openStockDetail({
                payload: { code: '600519' },
            });

            assert.equal(result.ok, true);
            assert.equal(receivedOptions.code, '600519');
            assert.equal(receivedOptions.preferDirectOpen, true);
            assert.equal(receivedOptions.awaitDetailLoad, false);
            assert.equal(receivedOptions.awaitDeferredLoad, false);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_stock_detail_builds_context_list_with_source_badges():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const contextList = {
            innerHTML: '',
            dataset: {},
            addEventListener(event, handler) {
                if (event === 'click') this.clickHandler = handler;
            },
        };
        let switchedTab = null;
        const stockOpenCalls = [];

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => id === 'stock-context-list' ? contextList : null,
            querySelector: () => null,
        };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async (tab) => { switchedTab = tab; },
            syncActiveStockContext: () => {},
            StockWorkbenchState: {
                selectedSymbol: {},
                contextList: [],
            },
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async (code, options) => {
                stockOpenCalls.push({ code, options });
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        await global.App.openStockDetail('300308', {
            stock: { code: '300308', name: '中际旭创' },
            source: 'signal:top',
            preferDirectOpen: true,
        });
        await global.App.openStockDetail('002484', {
            stock: { code: '002484', name: '江海股份' },
            source: 'opportunity:matrix',
            preferDirectOpen: true,
        });
        await global.App.openStockDetail('600519', {
            stock: { code: '600519', name: '贵州茅台' },
            source: 'watchlist',
            preferDirectOpen: true,
        });

        assert.equal(switchedTab, 'stock');
        assert.equal(stockOpenCalls.length, 3);
        assert.match(contextList.innerHTML, /中际旭创/);
        assert.match(contextList.innerHTML, /江海股份/);
        assert.match(contextList.innerHTML, /贵州茅台/);
        assert.match(contextList.innerHTML, /AI信号/);
        assert.match(contextList.innerHTML, /机会池/);
        assert.match(contextList.innerHTML, /自选/);
        assert.match(contextList.innerHTML, /data-code="600519"/);
        assert.match(contextList.innerHTML, /is-active/);
        assert.match(contextList.innerHTML, /aria-current="true"/);
        assert.equal(global.App._stockContextItems.length, 3);
        assert.equal(global.App.StockWorkbenchState.contextList.length, 3);
        assert.equal(global.App.StockWorkbenchState.contextList[0].code, '600519');
        assert.equal(global.App.StockWorkbenchState.selectedSymbol.code, '600519');
        assert.equal(global.App.StockWorkbenchState.selectedSymbol.name, '贵州茅台');

        let reopened = null;
        global.App.openStockDetail = async (code, options) => { reopened = { code, options }; };
        contextList.clickHandler({
            preventDefault: () => {},
            target: {
                closest: (selector) => selector === '[data-stock-context-code]' ? { dataset: { stockContextCode: '300308' } } : null,
            },
        });

        assert.equal(reopened.code, '300308');
        assert.equal(reopened.options.source, 'signal:top');
        assert.equal(reopened.options.sourceLabel, 'AI信号');
        assert.equal(reopened.options.stock.name, '中际旭创');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_context_click_keeps_each_pool_item_original_source_label():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const contextList = {
            innerHTML: '',
            dataset: {},
            addEventListener(event, handler) {
                if (event === 'click') this.clickHandler = handler;
            },
        };

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => id === 'stock-context-list' ? contextList : null,
            querySelector: () => null,
        };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async () => {},
            syncActiveStockContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        await global.App.openStockDetail('300308', {
            stock: { code: '300308', name: '中际旭创' },
            source: 'signal:top',
            preferDirectOpen: true,
        });
        await global.App.openStockDetail('002484', {
            stock: { code: '002484', name: '江海股份' },
            source: 'opportunity:matrix',
            preferDirectOpen: true,
        });
        await global.App.openStockDetail('600519', {
            stock: { code: '600519', name: '贵州茅台' },
            source: 'watchlist',
            preferDirectOpen: true,
        });

        contextList.clickHandler({
            preventDefault: () => {},
            target: {
                closest: (selector) => selector === '[data-stock-context-code]' ? { dataset: { stockContextCode: '300308' } } : null,
            },
        });
        await new Promise((resolve) => setTimeout(resolve, 0));

        const byCode = Object.fromEntries(global.App._stockContextItems.map((item) => [item.code, item]));
        assert.equal(global.App._stockContextItems[0].code, '300308');
        assert.equal(byCode['300308'].sourceLabel, 'AI信号');
        assert.equal(byCode['002484'].sourceLabel, '机会池');
        assert.equal(byCode['600519'].sourceLabel, '自选');
        assert.match(contextList.innerHTML, /AI信号/);
        assert.match(contextList.innerHTML, /机会池/);
        assert.match(contextList.innerHTML, /自选/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_context_click_preserves_iwencai_source_context():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const contextList = {
            innerHTML: '',
            dataset: {},
            addEventListener(event, handler) {
                if (event === 'click') this.clickHandler = handler;
            },
        };
        const sourceContext = {
            source: 'iwencai',
            sourceLabel: '问财',
            context_type: 'iwencai',
            result_pool_id: 'iwencai:test-pool',
            parsed_conditions: [{ raw_text: '高股息', hit_count: 473 }],
            condition_hit_count: { '高股息': 473 },
            rank_reason: '问财条件: 高股息',
        };

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => id === 'stock-context-list' ? contextList : null,
            querySelector: () => null,
        };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async () => {},
            syncActiveStockContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        await global.App.openStockDetail('600000', {
            stock: { code: '600000', name: '浦发银行' },
            source: 'iwencai',
            sourceLabel: '问财',
            context_type: 'iwencai',
            query: '高股息低估值近5日放量',
            source_context: sourceContext,
            preferDirectOpen: true,
            contextList: [
                { code: '600000', name: '浦发银行', sourceLabel: '问财', context_type: 'iwencai', source_context: sourceContext },
                { code: '000001', name: '平安银行', sourceLabel: '问财', context_type: 'iwencai', source_context: { ...sourceContext, rank_reason: '同一问财候选池' } },
            ],
        });

        let reopened = null;
        global.App.openStockDetail = async (code, options) => { reopened = { code, options }; };
        contextList.clickHandler({
            preventDefault: () => {},
            target: {
                closest: (selector) => selector === '[data-stock-context-code]' ? { dataset: { stockContextCode: '000001' } } : null,
            },
        });

        assert.equal(reopened.code, '000001');
        assert.equal(reopened.options.sourceLabel, '问财');
        assert.equal(reopened.options.source_context.result_pool_id, 'iwencai:test-pool');
        assert.deepEqual(reopened.options.source_context.parsed_conditions, [{ raw_text: '高股息', hit_count: 473 }]);
        assert.equal(reopened.options.source_context.condition_hit_count['高股息'], 473);
        assert.equal(reopened.options.source_context.rank_reason, '同一问财候选池');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_stock_detail_uses_sector_candidate_pool_for_context_list():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const contextList = {
            innerHTML: '',
            dataset: {},
            addEventListener(event, handler) {
                if (event === 'click') this.clickHandler = handler;
            },
        };

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: (id) => id === 'stock-context-list' ? contextList : null,
            querySelector: () => null,
        };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async () => {},
            syncActiveStockContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            toast: () => {},
            _uiActionPending: {},
        };
        global.StockDetail = {
            init: () => {},
            open: async () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        await global.App.openStockDetail('000001', {
            stock: { code: '000001', name: '平安银行' },
            source: 'market:sector-heatmap',
            context_type: 'sector',
            sector_name: '银行',
            rank_reason: '银行板块领涨',
            preferDirectOpen: true,
            contextList: [
                { code: '000001', name: '平安银行', price: 11.2, change_pct: 2.0, rank_reason: '银行板块领涨' },
                { code: '600000', name: '浦发银行', source: 'local_stock_daily', price: 8.5, change_pct: -1.0, rank_reason: '银行板块成分' },
            ],
        });

        assert.equal(global.App._stockContextItems.length, 2);
        assert.equal(global.App._stockContextItems[0].code, '000001');
        assert.equal(global.App._stockContextItems[1].code, '600000');
        assert.equal(global.App._stockContextItems[0].context_type, 'sector');
        assert.equal(global.App._stockContextItems[0].rank_reason, '银行板块领涨');
        assert.match(contextList.innerHTML, /平安银行/);
        assert.match(contextList.innerHTML, /浦发银行/);
        assert.match(contextList.innerHTML, /板块/);
        assert.match(contextList.innerHTML, /data-code="000001"/);
        assert.match(contextList.innerHTML, /is-active/);

        contextList.clickHandler({
            preventDefault: () => {},
            target: {
                closest: (selector) => selector === '[data-stock-context-code]' ? { dataset: { stockContextCode: '600000' } } : null,
            },
        });
        await Promise.resolve();
        await Promise.resolve();

        assert.equal(global.App._stockContextItems[0].code, '600000');
        assert.equal(global.App._stockContextItems[0].sourceLabel, '板块');
        assert.notEqual(global.App._stockContextItems[0].sourceLabel, 'AI信号');
        assert.equal(global.App._stockContextItems[0].sector_name, '银行');
        assert.equal(global.App._stockContextItems[0].context_type, 'sector');
        assert.equal(global.App._stockContextItems[0].rank_reason, '银行板块成分');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_page_has_workbench_context_and_evidence_shell():
    template = read("dashboard/templates/index.html")
    styles = read("dashboard/static/style.css")
    stock_detail_core = read("dashboard/static/stock-detail-core.js")

    assert 'id="sd-content" class="stock-workbench"' in template
    assert 'id="stock-context-list"' in template
    assert 'aria-label="股票上下文"' in template
    assert 'id="stock-evidence-rail"' in template
    assert 'aria-label="证据栏"' in template
    assert "暂无上下文股票" in template
    assert ".stock-workbench" in styles
    assert ".stock-context-list" in styles
    assert ".stock-evidence-rail" in styles
    assert "content.style.display = 'block'" not in stock_detail_core
    assert "content.style.display = ''" in stock_detail_core


def test_stock_page_declares_bottom_event_panel_shell():
    template = read("dashboard/templates/index.html")
    styles = read("dashboard/static/style.css")
    stock_detail_core = read("dashboard/static/stock-detail-core.js")

    assert 'id="stock-bottom-panel"' in template
    assert 'aria-label="股票事件中心"' in template or 'aria-label="底部事件中心"' in template
    assert "stock-bottom-panel" in styles
    assert "stock-bottom-tabs" in styles
    assert "stock-event-list" in styles
    assert "stock-bottom-panel" in stock_detail_core
    assert "data-stock-bottom-tab" in stock_detail_core
    assert "id=\"stock-bottom-events\"" in stock_detail_core


def test_stock_workbench_default_state_keeps_event_selection_and_bottom_tab():
    stock_detail_core = read("dashboard/static/stock-detail-core.js")

    default_state = stock_detail_core[
        stock_detail_core.index("_defaultStockWorkbenchState()") : stock_detail_core.index(
            "_stockWorkbenchStateStorageKey()"
        )
    ]
    ensure_start = stock_detail_core.index("_ensureStockWorkbenchState()")
    ensure_state = stock_detail_core[
        ensure_start : stock_detail_core.index("_syncWorkbenchOpenState(", ensure_start)
    ]

    assert "selectedEvent: null" in default_state
    assert "chartState: { period: 'timeline', adjust: 'qfq', visibleRange: null, selectedCandle: null, eventFocus: null, eventGroupFocus: null, eventOverlay: true, eventOverlayEvents: [], eventOverlayCount: 0 }" in default_state
    assert "layoutState: { leftOpen: true, rightOpen: true, bottomTab: 'events', railTab: 'profile' }" in default_state
    assert "if (value === null)" in ensure_state
    assert "if (!(key in state)) state[key] = null" in ensure_state
    assert "state.layoutState = { ...state.layoutState, ...stored.layoutState }" in ensure_state


def test_stock_workbench_bottom_event_core_contracts_are_wired():
    stock_detail_core = read("dashboard/static/stock-detail-core.js")

    expected_functions = [
        "_setWorkbenchEvents(",
        "_renderStockBottomPanel(",
        "_setStockBottomTab(",
        "_syncWorkbenchSelectedEvent(",
        "_selectStockEvent(",
        "_renderStockChartEventLayer(",
        "_onStockChartEventClick(",
        "_filteredWorkbenchEvents(",
        "_renderStockEventList(",
        "_renderStockEventGroupFocus(",
        "_syncWorkbenchEventGroupFocus(",
        "_eventGroupAction(",
        "_bindStockBottomPanel(",
    ]

    missing_functions = [name for name in expected_functions if name not in stock_detail_core]
    assert missing_functions == []
    assert "document.getElementById('stock-bottom-panel')" in stock_detail_core
    assert "data-stock-bottom-tab" in stock_detail_core
    assert "data-stock-event-id" in stock_detail_core
    assert "data-chart-event-id" in stock_detail_core
    assert "data-stock-event-group-date" in stock_detail_core
    assert "data-stock-event-group-action" in stock_detail_core
    assert "eventOverlayEvents" in stock_detail_core
    assert "eventGroupFocus" in stock_detail_core
    assert "role=\"tablist\"" in stock_detail_core
    assert "role=\"list\"" in stock_detail_core
    assert "state.selectedEvent" in stock_detail_core
    assert "点击事件可同步图表焦点" in stock_detail_core


def test_stock_workbench_event_sources_feed_bottom_panel_contract():
    stock_detail_core = read("dashboard/static/stock-detail-core.js")
    stock_detail_data = read("dashboard/static/stock-detail-data.js")
    stock_detail_research = read("dashboard/static/stock-detail-research.js")
    stock_detail_timeline_overlays = read("dashboard/static/stock-detail-timeline-overlays.js")
    stock_detail_dragon = read("dashboard/static/stock-detail-market-dragon.js")
    combined = "\n".join([
        stock_detail_core,
        stock_detail_data,
        stock_detail_research,
        stock_detail_timeline_overlays,
        stock_detail_dragon,
    ])

    event_types = [
        "news",
        "announcement",
        "research_report",
        "alpha_signal",
        "dividend",
        "northbound",
        "capital_flow",
        "dragon_tiger",
    ]
    missing_types = [
        event_type
        for event_type in event_types
        if f"'{event_type}'" not in combined and f'"{event_type}"' not in combined
    ]
    missing_aggregation = [
        event_type
        for event_type in event_types
        if (
            f"_setWorkbenchEvents('{event_type}'" not in combined
            and f'_setWorkbenchEvents("{event_type}"' not in combined
            and f"_setWorkbenchEvents?.('{event_type}'" not in combined
            and f'_setWorkbenchEvents?.("{event_type}"' not in combined
        )
    ]

    assert missing_types == []
    assert missing_aggregation == []
    assert "missing_reason" in stock_detail_core
    assert "status === 'ready'" in stock_detail_core
    assert "state.dataQuality" in stock_detail_core


def test_stock_workbench_empty_event_source_keeps_missing_reason_without_ready():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const elements = {
            'stock-evidence-rail': { innerHTML: '', querySelectorAll: () => [] },
            'stock-bottom-panel': {
                innerHTML: '',
                dataset: {},
                addEventListener: () => {},
                querySelectorAll: () => [],
            },
        };

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            createElement: () => ({ appendChild: () => {}, className: '', textContent: '' }),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };
        global.StockDetail = {
            _headerData: {},
            _buildStockIdentitySummary: () => ({}),
            _renderStockEvidenceRail: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        const events = global.StockDetail._setWorkbenchEvents('news', [], {
            type: 'news',
            title: '新闻',
            status: 'missing',
            missing_reason: '新闻源暂不可用',
        });

        const state = global.App.StockWorkbenchState;
        assert.equal(events.length, 1);
        assert.equal(events[0].status, 'missing');
        assert.equal(events[0].missing_reason, '新闻源暂不可用');
        assert.equal(events[0].detail, '新闻源暂不可用');
        assert.notEqual(state.dataQuality.news_research?.status, 'ready');
        assert.match(elements['stock-bottom-panel'].innerHTML, /新闻源暂不可用/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_workbench_select_event_updates_selected_event_and_chart_focus():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '',
                textContent: '',
                title: '',
                className: '',
                dataset: {},
                addEventListener: () => {},
                appendChild(child) {
                    if (child.className === 'stock-selected-event-marker') this.marker = child;
                    if (child.className === 'stock-chart-event-layer') this.eventLayer = child;
                },
                querySelector(selector) {
                    if (selector === '.stock-selected-event-marker') return this.marker || null;
                    if (selector === '.stock-chart-event-layer') return this.eventLayer || null;
                    return null;
                },
            };
        }

        const elements = {
            'stock-bottom-panel': makeElement('stock-bottom-panel'),
            'sd-kline-chart': makeElement('sd-kline-chart'),
            'stock-evidence-rail': makeElement('stock-evidence-rail'),
        };

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            StockWorkbenchState: {
                chartState: { period: 'daily', adjust: 'qfq', selectedCandle: null },
                layoutState: { bottomTab: 'events', railTab: 'profile' },
                eventFeed: [{
                    id: 'news-2026-06-10',
                    type: 'news',
                    title: '订单增长',
                    detail: '新闻事件详情',
                    at: '2026-06-10',
                    chartTime: '2026-06-10',
                    status: 'ready',
                }],
            },
        };
        global.StockDetail = {
            _headerData: {},
            _currentPeriod: 'daily',
            _buildStockIdentitySummary: () => ({}),
            _renderStockEvidenceRail: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        const selected = global.StockDetail._selectStockEvent('news-2026-06-10');
        const state = global.App.StockWorkbenchState;

        assert.equal(selected.title, '订单增长');
        assert.equal(state.selectedEvent.id, 'news-2026-06-10');
        assert.deepEqual(state.chartState.selectedCandle, {
            event_id: 'news-2026-06-10',
            type: 'news',
            title: '订单增长',
            timestamp: '2026-06-10',
            period: 'daily',
        });
        assert.match(elements['stock-bottom-panel'].innerHTML, /is-selected/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /aria-pressed="true"/);
        assert.equal(elements['sd-kline-chart'].marker.textContent, '新闻 · 订单增长');
        assert.equal(elements['sd-kline-chart'].marker.title, '新闻事件详情');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_workbench_chart_event_overlay_click_reverse_selects_bottom_event():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            let html = '';
            const el = {
                id,
                textContent: '',
                title: '',
                className: '',
                dataset: {},
                children: [],
                listeners: {},
                style: {},
                setAttribute(name, value) {
                    this[name] = value;
                },
                addEventListener(event, handler) {
                    this.listeners[event] = handler;
                },
                appendChild(child) {
                    this.children.push(child);
                    if (child.className) this[child.className] = child;
                    if (child.className === 'stock-chart-event-layer') this.eventLayer = child;
                    if (child.className === 'stock-selected-event-marker') this.marker = child;
                },
                querySelector(selector) {
                    if (selector === '.stock-chart-event-layer') return this.eventLayer || null;
                    if (selector === '.stock-selected-event-marker') return this.marker || null;
                    return null;
                },
                querySelectorAll(selector) {
                    if (selector !== '[data-stock-event-id]') return [];
                    return Array.from(html.matchAll(/data-stock-event-id="([^"]+)"/g)).map((match) => ({
                        dataset: { stockEventId: match[1] },
                        scrollIntoView() { this.scrolled = true; },
                    }));
                },
            };
            Object.defineProperty(el, 'innerHTML', {
                get() { return html; },
                set(value) { html = String(value ?? ''); },
            });
            return el;
        }

        const elements = {
            'stock-bottom-panel': makeElement('stock-bottom-panel'),
            'sd-kline-chart': makeElement('sd-kline-chart'),
            'stock-evidence-rail': makeElement('stock-evidence-rail'),
        };
        const chart = {
            created: [],
            removed: [],
            createOverlay(config) {
                this.created.push(config);
                return `overlay-${this.created.length}`;
            },
            removeOverlay(id) {
                this.removed.push(id);
            },
        };

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            StockWorkbenchState: {
                chartState: { period: 'daily', adjust: 'qfq', selectedCandle: null },
                layoutState: { bottomTab: 'events', railTab: 'profile' },
                eventFeed: [
                    {
                        id: 'capital-2026-06-10',
                        type: 'capital_flow',
                        title: '主力资金净流入',
                        detail: '净流入 1.20亿',
                        at: '2026-06-10',
                        date_key: '2026-06-10',
                        chartTime: '2026-06-10',
                        source_label: '资金流',
                        status: 'ready',
                    },
                    {
                        id: 'announcement-missing',
                        type: 'announcement',
                        title: '公告暂缺',
                        detail: '公告源不可用',
                        at: '',
                        status: 'missing',
                    },
                ],
            },
        };
        global.StockDetail = {
            _headerData: {},
            _currentPeriod: 'daily',
            _klineChart: chart,
            _buildStockIdentitySummary: () => ({}),
            _renderStockEvidenceRail: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        global.StockDetail._renderStockChartEventLayer([
            { timestamp: 1781049600000, date_key: '2026-06-10', high: 12, low: 9, close: 11 },
            { timestamp: 1781136000000, date_key: '2026-06-11', high: 13, low: 10, close: 12 },
        ]);

        const state = global.App.StockWorkbenchState;
        assert.equal(state.chartState.eventOverlayCount, 1);
        assert.equal(state.chartState.eventOverlayEvents[0].id, 'capital-2026-06-10');
        assert.match(elements['sd-kline-chart'].eventLayer.innerHTML, /data-chart-event-id="capital-2026-06-10"/);
        assert.equal(chart.created.length, 1);
        assert.equal(chart.created[0].extendData.stockEventId, 'capital-2026-06-10');

        chart.created[0].onClick();

        assert.equal(state.selectedEvent.id, 'capital-2026-06-10');
        assert.equal(state.layoutState.bottomTab, 'chart');
        assert.equal(state.chartState.eventFocus.event_id, 'capital-2026-06-10');
        assert.match(elements['stock-bottom-panel'].innerHTML, /is-selected/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /aria-pressed="true"/);
        assert.match(elements['sd-kline-chart'].eventLayer.innerHTML, /stock-chart-event-dot is-selected/);
        assert.doesNotMatch(elements['sd-kline-chart'].eventLayer.innerHTML, /announcement-missing/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            let html = '';
            const el = {
                id,
                textContent: '',
                title: '',
                className: '',
                dataset: {},
                children: [],
                listeners: {},
                style: {},
                setAttribute(name, value) {
                    this[name] = value;
                },
                addEventListener(event, handler) {
                    this.listeners[event] = handler;
                },
                appendChild(child) {
                    this.children.push(child);
                    if (child.className) this[child.className] = child;
                    if (child.className === 'stock-chart-event-layer') this.eventLayer = child;
                    if (child.className === 'stock-selected-event-marker') this.marker = child;
                },
                querySelector(selector) {
                    if (selector === '.stock-chart-event-layer') return this.eventLayer || null;
                    if (selector === '.stock-selected-event-marker') return this.marker || null;
                    return null;
                },
                querySelectorAll(selector) {
                    if (selector !== '[data-stock-event-id]') return [];
                    return Array.from(html.matchAll(/data-stock-event-id="([^"]+)"/g)).map((match) => ({
                        dataset: { stockEventId: match[1] },
                        scrollIntoView() { this.scrolled = true; },
                    }));
                },
            };
            Object.defineProperty(el, 'innerHTML', {
                get() { return html; },
                set(value) { html = String(value ?? ''); },
            });
            return el;
        }

        const elements = {
            'stock-bottom-panel': makeElement('stock-bottom-panel'),
            'sd-kline-chart': makeElement('sd-kline-chart'),
            'stock-evidence-rail': makeElement('stock-evidence-rail'),
        };
        const chart = {
            created: [],
            removed: [],
            createOverlay(config) {
                this.created.push(config);
                return `overlay-${this.created.length}`;
            },
            removeOverlay(id) {
                this.removed.push(id);
            },
        };

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            StockWorkbenchState: {
                chartState: { period: 'daily', adjust: 'qfq', selectedCandle: null },
                indicatorState: { active: 'MACD', main: ['MA'], sub: ['VOL', 'MACD'] },
                layoutState: { bottomTab: 'events', railTab: 'ai' },
                dataQuality: {
                    quote: { status: 'ready', updated_at: '2026-06-10' },
                    detail: { status: 'ready' },
                    valuation: { status: 'missing', missing_reason: 'PEG缺失' },
                    signal: { status: 'missing', missing_reason: 'Signal 暂缺' },
                    ai: { status: 'missing', missing_reason: 'AI 暂缺' },
                    news_research: { status: 'missing', missing_reason: '事件暂缺' },
                },
                relatedContext: { sectors: ['光模块'], concepts: ['CPO'], missing_reason: {} },
                sourceContext: { source: 'overview:opportunity', sourceLabel: 'AI信号', context_type: 'signal', rank_reason: 'AI信号第1名' },
                aiContext: { disclaimer: '不构成交易建议。' },
            },
            emitted: [],
            emit(event, payload) {
                this.emitted.push({ event, payload });
            },
        };
        global.StockDetail = {
            _headerData: {
                code: '300308',
                name: '中际旭创',
                price: 123.45,
                change_pct: 1.01,
                industry: '通信',
                sector: '通信设备',
                concepts: ['CPO'],
                updated_at: '2026-06-10',
            },
            _currentPeriod: 'daily',
            _klineChart: chart,
            _sourceContext: { source: 'overview:opportunity', sourceLabel: 'AI信号', context_type: 'signal', rank_reason: 'AI信号第1名' },
            _buildStockIdentitySummary: (data = {}) => ({
                peg: null,
                generatedAt: '2026-06-10',
                positioning: data.name || '基础资料',
                aiCoverage: { covered: false, reason: 'AI 暂缺' },
                signalCoverage: { covered: false, reason: 'Signal 暂缺' },
                tags: data.concepts || [],
                sourceContext: { sourceLabel: 'AI信号' },
                sourceLabel: 'AI信号',
                description: '',
            }),
            _renderStockEvidenceRail: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        const events = global.StockDetail._setWorkbenchEvents('same-day', [
            {
                id: 'news-1',
                type: 'news',
                title: '订单增长',
                detail: '新闻事件详情',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '新闻',
            },
            {
                id: 'announcement-1',
                type: 'announcement',
                title: '签订重大合同',
                detail: '公告事件详情',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '公告',
            },
            {
                id: 'capital-1',
                type: 'capital_flow',
                title: '主力资金净流入',
                detail: '净流入 1.20亿',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '资金流',
            },
            {
                id: 'report-1',
                type: 'research_report',
                title: '研报上调盈利预测',
                detail: '研报事件详情',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '研报',
            },
            {
                id: 'report-dup',
                type: 'report',
                title: '研报上调盈利预测',
                detail: '重复转载研报',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '资讯转载',
            },
            {
                id: 'note-1',
                type: 'note',
                title: '同日人工便签',
                detail: '不是 K 线事件组成员',
                at: '2026-06-10',
                date_key: '2026-06-10',
                chartTime: '2026-06-10',
                status: 'ready',
                source_label: '便签',
            },
        ], { source_label: 'QA同日事件' });

        global.StockDetail._renderStockChartEventLayer([
            { timestamp: 1781049600000, date_key: '2026-06-10', high: 12, low: 9, close: 11 },
            { timestamp: 1781136000000, date_key: '2026-06-11', high: 13, low: 10, close: 12 },
        ]);

        const state = global.App.StockWorkbenchState;
        assert.equal(events.filter((event) => event.status === 'ready' && event.date_key === '2026-06-10').length, 5);
        const report = events.find((event) => event.type === 'research_report');
        assert.equal(report.duplicate_count, 2);
        assert.ok(report.duplicate_ids.some((id) => /report-dup/.test(id)));
        assert.equal(state.chartState.eventOverlayCount, 1);
        assert.equal(state.chartState.eventOverlayEvents[0].cluster_count, 4);
        assert.deepEqual(state.chartState.eventOverlayEvents[0].event_ids.length, 4);
        assert.match(elements['sd-kline-chart'].eventLayer.innerHTML, /class="stock-chart-event-dot is-cluster"/);
        assert.match(elements['sd-kline-chart'].eventLayer.innerHTML, /data-chart-event-count="4"/);
        assert.ok(elements['sd-kline-chart'].eventLayer.innerHTML.includes('>4</span>'));
        assert.equal(chart.created.length, 1);
        assert.equal(chart.created[0].extendData.stockEventClusterCount, 4);

        assert.match(elements['stock-bottom-panel'].innerHTML, /订单增长/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /签订重大合同/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /主力资金净流入/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /研报上调盈利预测/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /同日 5 条/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /合并 2 条/);

        chart.created[0].onClick();
        assert.equal(state.selectedEvent.id, 'capital-1-capital-flow-2026-06-10-2026-06-10-主力资金净流入-same-day');
        assert.equal(state.chartState.eventFocus.date_key, '2026-06-10');
        assert.equal(state.chartState.eventGroupFocus.date_key, '2026-06-10');
        assert.equal(state.chartState.eventGroupFocus.event_ids.length, 4);
        assert.equal(state.chartState.eventGroupFocus.raw_count, 5);
        assert.equal(state.chartState.eventGroupFocus.source_context.sourceLabel, 'AI信号');
        assert.equal(state.chartState.eventGroupFocus.source_context.evidence_scope, 'stock_event_group');
        assert.equal(state.chartState.eventGroupFocus.source_context.row_evidence_status, 'not_applicable');
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.source, 'stock:event-group');
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.evidence_scope, 'stock_event_group');
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.stock_code, '300308');
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.event_count, 4);
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.raw_count, 5);
        assert.equal(state.chartState.eventGroupFocus.source_context.event_group.duplicate_count, 1);
        assert.match(state.chartState.eventGroupFocus.source_context.event_group.dedupe_policy, /重复转载/);
        assert.equal(state.aiContext.event_group_diagnosis.active, true);
        assert.equal(state.aiContext.event_group_diagnosis.raw_count, 5);
        assert.equal(state.aiContext.event_group_diagnosis.independent_count, 4);
        assert.equal(state.aiContext.event_group_diagnosis.duplicate_count, 1);
        assert.match(state.aiContext.event_group_diagnosis.counter_evidence, /重复转载 1 条/);
        assert.match(state.aiContext.event_group_diagnosis.missing_evidence, /回测验证/);
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'event_group').focus, true);
        assert.match(state.aiContext.diagnosis.find((item) => item.key === 'event_group').counter_evidence, /重复转载/);
        assert.equal(state.aiContext.diagnosis_focus_event_id, state.selectedEvent.id);
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'capital').focus, true);
        assert.equal(state.indicatorState.active, 'MACD');
        assert.equal(state.layoutState.railTab, 'ai');
        assert.match(elements['stock-bottom-panel'].innerHTML, /data-stock-event-group-date="2026-06-10"/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /2026-06-10 同日事件组/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /主事件:/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /重复转载不作为独立证据加权/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /缺少事件后 N 日回测验证/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /回测草案/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /篮子草案/);
        assert.doesNotMatch(elements['stock-bottom-panel'].innerHTML, /undefined|\\[object Object\\]/);

        const announcementId = events.find((event) => event.type === 'announcement').id;
        global.StockDetail._selectStockEvent(announcementId, { focusChart: true });
        assert.equal(state.selectedEvent.id, announcementId);
        assert.equal(state.chartState.eventFocus.date_key, '2026-06-10');
        assert.equal(state.chartState.eventGroupFocus.date_key, '2026-06-10');
        assert.match(elements['sd-kline-chart'].eventLayer.innerHTML, /stock-chart-event-dot is-cluster is-selected/);
        assert.match(elements['stock-bottom-panel'].innerHTML, /stock-event-group-item is-selected/);

        const noteId = events.find((event) => event.type === 'note').id;
        global.StockDetail._selectStockEvent(noteId, { focusChart: true });
        assert.equal(state.selectedEvent.id, noteId);
        assert.equal(state.chartState.eventGroupFocus, null);
        assert.doesNotMatch(elements['stock-bottom-panel'].innerHTML, /stock-event-group-item is-selected/);

        chart.created[0].onClick();
        assert.equal(state.chartState.eventGroupFocus.date_key, '2026-06-10');

        const payload = global.StockDetail._eventGroupAction('draft-backtest');
        assert.equal(global.App.emitted.at(-1).event, 'iwencai:draft-backtest');
        assert.equal(payload.source_context.sourceLabel, 'AI信号');
        assert.equal(payload.source_context.evidence_scope, 'stock_event_group');
        assert.equal(payload.source_context.row_evidence_status, 'not_applicable');
        assert.equal(payload.source_context.event_group.event_date, '2026-06-10');
        assert.equal(payload.source_context.event_group.event_ids.length, 4);
        assert.equal(payload.event_group_diagnosis.independent_count, 4);
        assert.equal(payload.event_group_diagnosis.raw_count, 5);
        assert.match(payload.event_group_diagnosis.dedupe_policy, /重复转载不作为独立证据加权/);
        assert.equal(payload.backtest_draft.requires_confirmation, true);
        assert.equal(payload.backtest_draft.conditions.event_date, '2026-06-10');
        assert.equal(payload.backtest_draft.conditions.event_ids.length, 4);
        assert.equal(payload.backtest_draft.conditions.primary_event_id, payload.event_group_diagnosis.primary_event_id);
        assert.match(payload.backtest_draft.conditions.entry_rule, /次一交易日开盘/);
        assert.ok(payload.backtest_draft.conditions.holding_periods.includes(5));
        assert.match(payload.backtest_draft.conditions.dedupe_policy, /重复转载/);
        assert.match(payload.backtest_draft.conditions.counter_evidence_filters.join('；'), /回测验证|重复转载/);
        assert.equal(payload.backtest_draft.draft_type, 'event_group_backtest_draft');
        assert.equal(payload.backtest_draft.evidence_scope, 'stock_event_group');
        assert.equal(payload.backtest_draft.row_evidence_status, 'not_applicable');
        assert.equal(payload.backtest_draft.source_context.evidence_scope, 'stock_event_group');
        assert.equal(payload.backtest_draft.execution_policy, 'manual_only');
        assert.equal(payload.backtest_draft.execution_status, 'not_executed');
        assert.deepEqual(payload.backtest_draft.allowed_actions, ['view', 'edit', 'run_backtest_after_confirmation']);
        assert.equal(payload.events.length, 4);
        assert.equal(payload.candidates[0].code, '300308');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_basket_backtest_draft_panel_renders_and_edits_manual_only_conditions():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList(initial = '') {
            const values = new Set(String(initial || '').split(/\s+/).filter(Boolean));
            return {
                add: (...items) => items.forEach((item) => values.add(item)),
                remove: (...items) => items.forEach((item) => values.delete(item)),
                contains: (item) => values.has(item),
                toggle: (item, force) => {
                    if (force === false) { values.delete(item); return false; }
                    if (force === true || !values.has(item)) { values.add(item); return true; }
                    values.delete(item);
                    return false;
                },
                toString: () => Array.from(values).join(' '),
            };
        }

        function makeElement(id, className = '') {
            return {
                id,
                className,
                classList: makeClassList(className),
                dataset: {},
                children: [],
                textContent: '',
                innerHTML: '',
                value: '',
                appendChild(child) { this.children.push(child); return child; },
            };
        }

        const elements = {
            'basket-candidates': makeElement('basket-candidates'),
            'basket-backtest-draft': makeElement('basket-backtest-draft', 'basket-backtest-draft hidden'),
            'basket-backtest-draft-fields': makeElement('basket-backtest-draft-fields'),
            'basket-backtest-draft-conditions': makeElement('basket-backtest-draft-conditions'),
            'basket-backtest-draft-error': makeElement('basket-backtest-draft-error', 'basket-backtest-draft-error hidden'),
            'basket-backtest-draft-title': makeElement('basket-backtest-draft-title'),
            'basket-backtest-draft-summary': makeElement('basket-backtest-draft-summary'),
            'basket-backtest-draft-status': makeElement('basket-backtest-draft-status'),
            'basket-backtest-summary': makeElement('basket-backtest-summary'),
            'basket-draft-audit-study': makeElement('basket-draft-audit-study', 'basket-draft-audit-study hidden'),
            'basket-warning-list': makeElement('basket-warning-list'),
            'basket-cash': makeElement('basket-cash'),
            'basket-allocation': makeElement('basket-allocation'),
            'basket-rebalance': makeElement('basket-rebalance'),
        };
        const toasts = [];

        global.window = global;
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'loading',
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            toast: (message, type) => toasts.push({ message, type }),
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/alpha-tools.js', 'utf8'));

        App.renderBasketBacktestDraft(null);
        assert.equal(elements['basket-backtest-draft'].classList.contains('hidden'), false);
        assert.equal(elements['basket-backtest-draft'].classList.contains('is-empty'), true);
        assert.match(elements['basket-backtest-draft-summary'].textContent, /草案不会自动执行/);
        assert.match(elements['basket-backtest-draft-status'].textContent, /空态/);

        App.renderBasketBacktestDraft({
            draft_type: 'iwencai_basket_backtest_draft',
            conditions: { hypothesis: '问财候选池需要验证', candidate_count: 2 },
            source_context: { sourceLabel: '问财选股', query: '高股息 低估值' },
        });
        assert.equal(elements['basket-backtest-draft-title'].textContent, '候选池回测草案');
        assert.match(elements['basket-backtest-draft-summary'].textContent, /问财候选池需要验证/);

        const draft = {
            draft_type: 'event_group_backtest',
            status: 'executed',
            requires_confirmation: false,
            execution_status: 'executed',
            allowed_actions: ['view', 'run_live_trade'],
            conditions: {
                hypothesis: '中际旭创 <事件> 需要验证',
                event_date: '2026-06-10',
                primary_event_title: '<公告>签订重大合同',
                entry_rule: '次一交易日开盘',
                exit_rule: '持有 5 日或出现反证退出',
                holding_periods: [1, 3, 5],
                benchmark: '沪深300',
                dedupe_policy: '重复转载只计一次',
                counter_evidence_filters: ['缺少回测验证'],
            },
            source_context: {
                source: 'overview:opportunity',
                sourceLabel: 'AI信号',
                query: '中际旭创 事件组',
                event_group: {
                    stock_code: '300308',
                    stock_name: '中际旭创',
                    event_date: '2026-06-10',
                    event_count: 4,
                    raw_count: 5,
                    event_types: ['capital_flow', 'announcement'],
                    dedupe_policy: '重复转载只计一次',
                    rank_reason: '2026-06-10 同日事件组',
                },
            },
        };

        App.renderBasketBacktestDraft(draft);
        assert.equal(elements['basket-backtest-draft'].classList.contains('hidden'), false);
        assert.equal(elements['basket-backtest-draft'].dataset.executionPolicy, 'manual_only');
        assert.equal(elements['basket-backtest-draft'].dataset.executionStatus, 'not_executed');
        assert.equal(App._iwencaiBasketDraft.backtest_draft.status, 'draft');
        assert.match(elements['basket-backtest-draft-title'].textContent, /中际旭创/);
        assert.match(elements['basket-backtest-draft-title'].textContent, /300308/);
        assert.match(elements['basket-backtest-draft-summary'].textContent, /需要验证/);
        assert.match(elements['basket-backtest-draft-status'].textContent, /手动计划回测/);
        assert.match(elements['basket-backtest-draft-status'].textContent, /提交后端审计/);
        assert.equal(elements['basket-backtest-draft-fields'].children.length >= 10, true);
        const fieldText = elements['basket-backtest-draft-fields'].children.map((child) => child.children.map((node) => node.textContent).join(':')).join('|');
        assert.match(fieldText, /来源:AI信号/);
        assert.match(fieldText, /原始查询:中际旭创 事件组/);
        assert.match(fieldText, /事件数:4 独立 \/ 5 原始/);
        assert.match(fieldText, /事件类型:capital_flow \/ announcement/);
        assert.match(elements['basket-backtest-draft-conditions'].value, /"event_date": "2026-06-10"/);
        assert.match(elements['basket-candidates'].dataset.backtestDraft, /manual_only/);
        assert.doesNotMatch(elements['basket-candidates'].dataset.backtestDraft, /run_live_trade/);
        assert.equal(App._iwencaiBasketDraft.backtest_draft.requires_confirmation, true);
        assert.equal(App._iwencaiBasketDraft.backtest_draft.execution_policy, 'manual_only');
        assert.equal(App._iwencaiBasketDraft.backtest_draft.execution_status, 'not_executed');
        assert.deepEqual(App._iwencaiBasketDraft.backtest_draft.allowed_actions, ['view', 'edit', 'run_backtest_after_confirmation']);

        elements['basket-backtest-draft-conditions'].value = '{"entry_rule":';
        App.updateBasketBacktestDraftFromEditor();
        assert.equal(elements['basket-backtest-draft-error'].classList.contains('hidden'), false);
        assert.match(elements['basket-backtest-draft-error'].textContent, /JSON 格式不正确/);

        elements['basket-backtest-draft-conditions'].value = JSON.stringify(App._iwencaiBasketDraft.backtest_draft.conditions);
        const edited = JSON.parse(elements['basket-backtest-draft-conditions'].value);
        edited.entry_rule = '突破事件日高点后确认';
        edited.holding_periods = [3, 5, 10];
        elements['basket-backtest-draft-conditions'].value = JSON.stringify(edited);
        App.updateBasketBacktestDraftFromEditor();
        const saved = JSON.parse(elements['basket-candidates'].dataset.backtestDraft);
        assert.equal(saved.conditions.entry_rule, '突破事件日高点后确认');
        assert.deepEqual(saved.conditions.holding_periods, [3, 5, 10]);
        assert.equal(saved.requires_confirmation, true);
        assert.equal(saved.execution_policy, 'manual_only');
        assert.equal(saved.execution_status, 'not_executed');
        assert.equal(App._iwencaiBasketDraft.backtest_draft.conditions.entry_rule, '突破事件日高点后确认');
        assert.match(toasts.at(-1).message, /手动执行计划回测/);

        (async () => {
            const postCalls = [];
            App.postJSON = async (url, body) => {
                postCalls.push({ url, body });
                return {
                    success: true,
                    metrics: {},
                    draft_audit: {
                        manual_only: true,
                        conditions_applied_to_backtest: false,
                        execution_status: 'not_executed',
                        sample_status: 'ready',
                        sample_count: 1,
                        candidate_count: 1,
                        coverage_ratio: 1,
                        event_date: '2026-06-10',
                        holding_periods: [1, 3, 5],
                        event_statistics: {
                            status: 'ready',
                            method: 'next_bar_open_to_holding_close',
                            unit: 'percent',
                            calculation_status: 'computed',
                            cost_model: {
                                available: true,
                                calculation_status: 'computed',
                                source: 'draft_conditions',
                                estimated_round_trip_cost_pct: 0.24,
                            },
                            benchmark: {
                                available: true,
                                calculation_status: 'computed',
                                code: '000300',
                                name: '沪深300',
                                data_source: 'price_data',
                            },
                            holding_periods: [1, 3, 5],
                            candidate_count: 1,
                            ready_sample_count: 1,
                            missing_sample_count: 0,
                            coverage_ratio: 1,
                            by_holding_period: {
                                '1': { period: 1, sample_count: 1, mean_return_pct: 1.23, mean_cost_pct: 0.24, mean_net_return_pct: 0.99, mean_benchmark_return_pct: 0.30, mean_excess_return_pct: 0.69, median_return_pct: 1.23, win_rate: 1, best_return_pct: 1.23, worst_return_pct: 1.23, t_stat_excess_return: 2.34, significance_status: 'computed_descriptive' },
                                '3': { period: 3, sample_count: 1, mean_return_pct: -0.45, mean_cost_pct: 0.24, mean_net_return_pct: -0.69, mean_benchmark_return_pct: 0.12, mean_excess_return_pct: -0.81, median_return_pct: -0.45, win_rate: 0, best_return_pct: -0.45, worst_return_pct: -0.45, t_stat_excess_return: -1.12, significance_status: 'computed_descriptive' },
                                '5': { period: 5, sample_count: 0, mean_return_pct: null, mean_cost_pct: null, mean_net_return_pct: null, mean_benchmark_return_pct: null, mean_excess_return_pct: null, median_return_pct: null, win_rate: null, best_return_pct: null, worst_return_pct: null, significance_status: 'insufficient_sample' },
                            },
                            best_period: { period: 1, mean_return_pct: 1.23, sample_count: 1 },
                            methodology: '按草案 event_date 定位样本，净收益扣除估算双边成本，基准可用时计算净超额收益。',
                            limitations: ['未执行草案 entry_rule/exit_rule 风控逻辑', 't-stat 仅为描述性统计'],
                        },
                        warnings: ['1 只候选缺少事件日或价格数据'],
                        note: '草案审计仅用于验证样本覆盖和持有期收益；草案条件不会改变本次篮子回测规则，也不会自动交易或模拟盘下单。',
                    },
                };
            };
            elements['basket-candidates'].value = JSON.stringify([{ code: '300308', name: '中际旭创' }]);
            elements['basket-cash'].value = '1000000';
            elements['basket-allocation'].value = 'equal';
            elements['basket-rebalance'].value = '5';

            const submitEdited = JSON.parse(elements['basket-backtest-draft-conditions'].value);
            submitEdited.entry_rule = '编辑器内临时改动，无需点击更新';
            elements['basket-backtest-draft-conditions'].value = JSON.stringify(submitEdited);
            await App.loadBasketBacktest();

            assert.equal(postCalls.length, 1);
            assert.equal(postCalls[0].url, '/api/alpha/basket/backtest');
            assert.equal(postCalls[0].body.backtest_draft.conditions.entry_rule, '编辑器内临时改动，无需点击更新');
            assert.equal(postCalls[0].body.backtest_draft.execution_policy, 'manual_only');
            assert.equal(postCalls[0].body.backtest_draft.execution_status, 'not_executed');
            assert.deepEqual(postCalls[0].body.backtest_draft.allowed_actions, ['view', 'edit', 'run_backtest_after_confirmation']);
            assert.doesNotMatch(JSON.stringify(postCalls[0].body.backtest_draft), /run_live_trade/);
            assert.deepEqual(postCalls[0].body.backtest_draft_conditions.holding_periods, [3, 5, 10]);
            assert.match(elements['basket-backtest-draft-status'].textContent, /后端已审计草案/);
            assert.equal(elements['basket-draft-audit-study'].classList.contains('hidden'), false);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /事件样本统计/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /覆盖率/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /100.0%/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /2026-06-10/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /1日/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /1.23%/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /净收益/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /成本/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /基准/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /超额/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /t值/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /沪深300/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /0.99%/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /0.69%/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /-0.81%/);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /未执行草案 entry_rule/);
            assert.match(elements['basket-warning-list'].innerHTML, /未改变本次篮子回测执行规则/);

            App.clearBasketBacktestDraft();
            assert.equal(elements['basket-draft-audit-study'].classList.contains('hidden'), true);
            assert.doesNotMatch(elements['basket-draft-audit-study'].innerHTML, /0.99%/);
            App.renderBasketBacktestDraft(saved);
            elements['basket-backtest-draft-conditions'].value = JSON.stringify(saved.conditions);

            App.renderBasketBacktest({ success: true, metrics: {} });
            assert.equal(elements['basket-draft-audit-study'].classList.contains('hidden'), true);
            assert.match(elements['basket-draft-audit-study'].innerHTML, /暂无草案审计/);
            assert.equal(elements['basket-warning-list'].innerHTML, '暂无警告');
            assert.doesNotMatch(elements['basket-backtest-draft-status'].textContent, /后端已审计草案/);
            assert.doesNotMatch(elements['basket-draft-audit-study'].innerHTML, /0.99%/);
            assert.match(elements['basket-backtest-draft-status'].textContent, /待后端审计/);

            elements['basket-backtest-draft-conditions'].value = '{"entry_rule":';
            await App.loadBasketBacktest();
            assert.equal(postCalls.length, 1);
            assert.match(elements['basket-backtest-draft-error'].textContent, /JSON 格式不正确/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_multi_timeframe_renders_degraded_state_when_periods_missing():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '' };
        global.document = {
            getElementById: (id) => id === 'sd-multitimeframe' ? container : null,
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-market-mtf.js', 'utf8'));

        global.StockDetail._renderMultiTimeframe({ success: true, strength: 0 });

        assert.match(container.innerHTML, /多周期数据暂缺/);
        assert.match(container.innerHTML, /日线/);
        assert.match(container.innerHTML, /周线/);
        assert.match(container.innerHTML, /月线/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_detail_header_compresses_identity_and_moves_long_profile_to_evidence_rail():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                textContent: '',
                innerHTML: '',
                className: '',
                style: {},
                dataset: {},
                appendChild(child) {
                    this.children = this.children || [];
                    this.children.push(child);
                },
            };
        }

        const elements = Object.fromEntries([
            'sd-header',
            'sd-name',
            'sd-code',
            'sd-price',
            'sd-change',
            'sd-industry',
            'sd-sector',
            'sd-concepts',
            'sd-positioning',
            'sd-trust-strip',
            'stock-evidence-rail',
        ].map((id) => [id, makeElement(id)]));

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#tab-stock .stock-detail-header' ? elements['sd-header'] : null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };
        global.StockDetail = {
            _sourceContext: {
                source: 'signal:top',
                sourceLabel: 'AI信号',
                context_type: 'signal',
                rank_reason: '强动能前 5%',
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        const longDescription = '公司是一家专注于高速光模块、光通信器件、数据中心互联和算力网络核心部件的企业。'.repeat(8);
        global.StockDetail._renderDetailHeader({
            code: '300308',
            name: '中际旭创',
            price: 123.45,
            change: 1.2,
            change_pct: 1.01,
            industry: '通信设备',
            sector: '光模块',
            concepts: ['CPO', '算力', '光通信', 'AI服务器', '高速连接', '出口链', '第七个概念'],
            main_business: '高速光模块与数据中心互联',
            description: longDescription,
            peg_next_year: null,
            ai_coverage: { covered: false, reason: '本地 AI 信号未覆盖该股票' },
            signal_coverage: { covered: false, reason: 'Signal Engine 暂无验证样本' },
            source: 'stock_detail_api',
            generated_at: '2026-06-10T09:30:00',
        });

        const headerText = [
            elements['sd-header'].innerHTML,
            elements['sd-positioning'].textContent,
            elements['sd-trust-strip'].innerHTML,
            elements['sd-concepts'].innerHTML,
        ].join(' ');
        const railText = elements['stock-evidence-rail'].innerHTML;

        assert.equal(elements['sd-name'].textContent, '中际旭创');
        assert.equal(elements['sd-code'].textContent, '300308');
        assert.match(elements['sd-positioning'].textContent, /高速光模块与数据中心互联/);
        assert.match(headerText, /PEG 缺失/);
        assert.match(headerText, /AI 未覆盖/);
        assert.match(headerText, /Signal 未覆盖/);
        assert.match(headerText, /AI信号/);
        assert.doesNotMatch(headerText, /公司是一家专注于高速光模块/);
        assert.doesNotMatch(headerText, /Qlib覆盖/);
        assert.match(railText, /资料/);
        assert.match(railText, /盘口/);
        assert.match(railText, /资金/);
        assert.match(railText, /AI/);
        assert.match(railText, /舆情/);
        assert.match(railText, /公司是一家专注于高速光模块/);
        assert.match(railText, /本地 AI 信号未覆盖该股票/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_workbench_evidence_state_completes_with_missing_reasons_and_tab_state():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            const el = {
                id,
                textContent: '',
                className: '',
                style: {},
                dataset: {},
                appendChild(child) {
                    this.children = this.children || [];
                    this.children.push(child);
                },
            };
            let html = '';
            Object.defineProperty(el, 'innerHTML', {
                get() { return html; },
                set(value) {
                    html = String(value ?? '');
                    if (id === 'stock-evidence-rail') {
                        el.buttons = Array.from(html.matchAll(/data-stock-evidence-tab="([^"]+)"/g)).map((match) => ({
                            dataset: { stockEvidenceTab: match[1] },
                            addEventListener(event, handler) {
                                if (event === 'click') this.clickHandler = handler;
                            },
                            click() {
                                if (this.clickHandler) this.clickHandler({ preventDefault: () => {} });
                            },
                        }));
                    }
                },
            });
            el.querySelectorAll = (selector) => selector === '[data-stock-evidence-tab]' ? (el.buttons || []) : [];
            return el;
        }

        const elements = Object.fromEntries([
            'sd-header',
            'sd-name',
            'sd-code',
            'sd-price',
            'sd-change',
            'sd-industry',
            'sd-sector',
            'sd-concepts',
            'sd-positioning',
            'sd-trust-strip',
            'stock-evidence-rail',
        ].map((id) => [id, makeElement(id)]));

        global.window = global;
        global.globalThis = global;
        global.sessionStorage = { setItem: () => {} };
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#tab-stock .stock-detail-header' ? elements['sd-header'] : null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };
        global.StockDetail = {
            _sourceContext: {
                source: 'market:sector-heatmap',
                sourceLabel: '板块',
                context_type: 'sector',
                sector_name: '光模块',
                rank_reason: '板块成分股第 1 名',
                query: '光模块板块',
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        global.StockDetail._renderDetailHeader({
            code: '300308',
            name: '中际旭创',
            price: 123.45,
            change: 1.2,
            change_pct: 1.01,
            market_status: 'open',
            industry: '通信',
            sector: '通信设备',
            concepts: ['CPO', '算力'],
            main_business: '高速光模块与数据中心互联',
            description: '证据栏保留长资料。',
            peg_next_year: null,
            ai_coverage: { covered: false, reason: 'AI 证据未覆盖该股票' },
            signal_coverage: { covered: false, reason: 'Signal Engine 暂无验证样本' },
            source: 'stock_detail_api',
            updated_at: '2026-06-10T09:30:00',
        });

        const state = global.App.StockWorkbenchState;
        assert.equal(state.quoteSnapshot.price, 123.45);
        assert.equal(state.quoteSnapshot.market_status, 'open');
        assert.equal(state.fundamentalSnapshot.industry, '通信');
        assert.equal(state.dataQuality.quote.status, 'ready');
        assert.equal(state.dataQuality.detail.status, 'ready');
        assert.equal(state.dataQuality.valuation.status, 'missing');
        assert.match(state.dataQuality.valuation.missing_reason, /PEG/);
        assert.equal(state.dataQuality.news_research.status, 'missing');
        assert.match(state.dataQuality.news_research.missing_reason, /尚未汇入工作台状态/);
        assert.deepEqual(state.relatedContext.sectors, ['光模块', '通信设备', '通信']);
        assert.deepEqual(state.relatedContext.concepts, ['CPO', '算力']);
        assert.match(state.relatedContext.missing_reason.indices, /关联指数/);
        assert.match(state.relatedContext.missing_reason.peers, /同业/);
        assert.equal(state.aiContext.aiCoverage.status, 'missing');
        assert.equal(state.aiContext.signalCoverage.status, 'missing');
        assert.match(state.aiContext.disclaimer, /不构成交易建议/);
        assert.ok(state.eventFeed.some((event) => event.type === 'source_context' && event.status === 'ready'));
        assert.ok(state.eventFeed.some((event) => event.type === 'news_research' && event.status === 'missing'));

        const railText = elements['stock-evidence-rail'].innerHTML;
        assert.match(railText, /数据质量/);
        assert.match(railText, /相关上下文/);
        assert.match(railText, /事件/);
        assert.match(railText, /AI\/Signal/);
        assert.match(railText, /新闻、公告、研报事件流尚未汇入工作台状态/);
        assert.match(railText, /data-stock-evidence-tab="profile" role="tab" aria-selected="true"/);
        assert.doesNotMatch(railText, /推荐买入|上涨概率|买入评级/);

        const aiButton = elements['stock-evidence-rail'].buttons.find((button) => button.dataset.stockEvidenceTab === 'ai');
        aiButton.click();
        assert.equal(global.App.StockWorkbenchState.layoutState.railTab, 'ai');
        assert.match(elements['stock-evidence-rail'].innerHTML, /data-stock-evidence-tab="ai" role="tab" aria-selected="true"/);
        assert.equal(global.App.StockWorkbenchState.sourceContext.sourceLabel, '板块');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_ai_diagnosis_consumes_event_focus_and_evidence_state():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            const el = {
                id,
                textContent: '',
                className: '',
                style: {},
                dataset: {},
                addEventListener: () => {},
                appendChild(child) {
                    this.children = this.children || [];
                    this.children.push(child);
                },
                querySelector: () => null,
            };
            let html = '';
            Object.defineProperty(el, 'innerHTML', {
                get() { return html; },
                set(value) {
                    html = String(value ?? '');
                    if (id === 'stock-evidence-rail') {
                        el.buttons = Array.from(html.matchAll(/data-stock-evidence-tab="([^"]+)"/g)).map((match) => ({
                            dataset: { stockEvidenceTab: match[1] },
                            addEventListener(event, handler) {
                                if (event === 'click') this.clickHandler = handler;
                            },
                            click() {
                                if (this.clickHandler) this.clickHandler({ preventDefault: () => {} });
                            },
                        }));
                    }
                },
            });
            el.querySelectorAll = (selector) => selector === '[data-stock-evidence-tab]' ? (el.buttons || []) : [];
            return el;
        }

        const elements = Object.fromEntries([
            'sd-header',
            'sd-name',
            'sd-code',
            'sd-price',
            'sd-change',
            'sd-industry',
            'sd-sector',
            'sd-concepts',
            'sd-positioning',
            'sd-trust-strip',
            'stock-evidence-rail',
            'stock-bottom-panel',
        ].map((id) => [id, makeElement(id)]));

        global.window = global;
        global.globalThis = global;
        global.sessionStorage = { setItem: () => {} };
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#tab-stock .stock-detail-header' ? elements['sd-header'] : null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            StockWorkbenchState: {
                selectedSymbol: { code: '300308', name: '中际旭创', asset_type: 'stock', market: 'A股' },
                chartState: { period: 'daily', adjust: 'qfq', selectedCandle: null, eventFocus: null },
                indicatorState: { active: 'MACD', main: ['MA'], sub: ['VOL', 'MACD'] },
                layoutState: { bottomTab: 'events', railTab: 'ai' },
                contextList: [{ code: '300308', name: '中际旭创', sourceLabel: 'AI信号' }],
            },
        };
        global.StockDetail = {
            _sourceContext: {
                source: 'playwright:ai-diagnosis',
                sourceLabel: 'AI信号',
                context_type: 'signal',
                sector_name: '光模块',
                rank_reason: 'QA诊断证据',
                query: 'AI 强动能',
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        global.StockDetail._renderDetailHeader({
            code: '300308',
            name: '中际旭创',
            price: 123.45,
            change: 1.2,
            change_pct: 1.01,
            market_status: 'open',
            industry: '通信',
            sector: '通信设备',
            concepts: ['CPO', '算力'],
            main_business: '高速光模块与数据中心互联',
            description: '证据栏保留长资料。',
            peg_next_year: 0.88,
            ai_coverage: { covered: false, reason: 'AI 证据未覆盖该股票' },
            signal_coverage: { covered: false, reason: 'Signal Engine 暂无验证样本' },
            source: 'stock_detail_api',
            updated_at: '2026-06-10T09:30:00',
        });

        let state = global.App.StockWorkbenchState;
        assert.deepEqual(state.aiContext.diagnosis.map((item) => item.key), [
            'technical',
            'capital',
            'news',
            'industry',
            'fundamental',
            'valuation',
            'signal',
            'risk',
        ]);
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'capital').status, 'missing');
        assert.match(state.aiContext.diagnosis.find((item) => item.key === 'capital').missing_reason, /资金流/);
        assert.match(state.aiContext.disclaimer, /不构成交易建议/);

        const events = global.StockDetail._setWorkbenchEvents('qa-capital', [{
            id: 'capital-2026-06-10',
            type: 'capital_flow',
            title: '主力资金净流入',
            detail: '净流入 1.20亿',
            at: '2026-06-10',
            date_key: '2026-06-10',
            chartTime: '2026-06-10',
            source_label: '资金流',
            status: 'ready',
        }], { type: 'capital_flow', source_label: '资金流' });
        const capitalEvent = events.find((event) => event.type === 'capital_flow');
        global.StockDetail._selectStockEvent(capitalEvent.id, { focusChart: true, syncBottomTab: true });

        state = global.App.StockWorkbenchState;
        assert.equal(state.selectedEvent.id, capitalEvent.id);
        assert.equal(state.chartState.eventFocus.event_id, capitalEvent.id);
        assert.equal(state.aiContext.diagnosis_focus_event_id, capitalEvent.id);
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'capital').status, 'ready');
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'capital').focus, true);
        assert.equal(state.aiContext.diagnosis.find((item) => item.key === 'technical').focus, true);
        assert.equal(state.layoutState.bottomTab, 'chart');
        assert.equal(state.layoutState.railTab, 'ai');
        assert.equal(state.indicatorState.active, 'MACD');
        assert.equal(state.sourceContext.sourceLabel, 'AI信号');

        const railText = elements['stock-evidence-rail'].innerHTML;
        assert.match(railText, /stock-ai-diagnosis/);
        assert.match(railText, /技术面/);
        assert.match(railText, /资金面/);
        assert.match(railText, /消息面/);
        assert.match(railText, /行业面/);
        assert.match(railText, /基本面/);
        assert.match(railText, /估值/);
        assert.match(railText, /Signal/);
        assert.match(railText, /风险/);
        assert.match(railText, /图表焦点 资金/);
        assert.match(railText, /主力资金净流入/);
        assert.match(railText, /QA诊断证据/);
        assert.match(railText, /不构成交易建议/);
        assert.doesNotMatch(railText, /推荐买入|上涨概率|必涨|undefined|\[object Object\]/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_stock_detail_passes_source_context_into_stock_detail_open():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.sessionStorage = { setItem: () => {} };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
        };
        global.App = {
            ensureBundle: async () => {},
            switchTab: async () => {},
            syncActiveStockContext: () => {},
            escapeHTML: (value) => String(value ?? ''),
            toast: () => {},
            _uiActionPending: {},
        };
        let opened = null;
        global.StockDetail = {
            init: () => {},
            open: async (code, options) => { opened = { code, options }; },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-stock-ops.js', 'utf8'));

        await global.App.openStockDetail('300308', {
            stock: { code: '300308', name: '中际旭创' },
            source: 'signal:top',
            sourceLabel: 'AI信号',
            context_type: 'signal',
            sector_name: '光模块',
            rank_reason: '强动能前 5%',
            query: 'AI 强动能',
            preferDirectOpen: true,
        });

        assert.equal(opened.code, '300308');
        assert.equal(opened.options.source, 'signal:top');
        assert.equal(opened.options.sourceLabel, 'AI信号');
        assert.equal(opened.options.context_type, 'signal');
        assert.equal(opened.options.sector_name, '光模块');
        assert.equal(opened.options.rank_reason, '强动能前 5%');
        assert.equal(opened.options.query, 'AI 强动能');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_valuation_snapshot_updates_header_peg_chip():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                textContent: '',
                innerHTML: '',
                className: '',
                style: {},
                dataset: {},
                appendChild: () => {},
            };
        }

        const elements = Object.fromEntries([
            'sd-header',
            'sd-name',
            'sd-code',
            'sd-price',
            'sd-change',
            'sd-industry',
            'sd-sector',
            'sd-concepts',
            'sd-positioning',
            'sd-trust-strip',
            'stock-evidence-rail',
            'sd-valuation-snapshot',
            'sd-valuation-hint',
            'sd-peer-panel',
        ].map((id) => [id, makeElement(id)]));

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#tab-stock .stock-detail-header' ? elements['sd-header'] : null,
            createElement: (tag) => makeElement(tag),
        };
        global.App = {
            fetchJSON: async () => ({ peers: [], summary: {} }),
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };
        global.StockDetail = {
            _sourceContext: { sourceLabel: 'AI信号' },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-valuation.js', 'utf8'));

        global.StockDetail._renderDetailHeader({
            code: '300308',
            name: '中际旭创',
            concepts: [],
            main_business: '高速光模块',
            peg_next_year: null,
        });
        assert.match(elements['sd-trust-strip'].innerHTML, /PEG 缺失/);

        global.StockDetail._renderValuationSnapshot({
            code: '300308',
            source: 'qa',
            source_version: 'test',
            quality_status: 'ok',
            peg_next_year: 0.88,
            report_count: 2,
        }, null, false);

        assert.match(elements['sd-trust-strip'].innerHTML, /PEG 0.88/);
        assert.match(elements['sd-trust-strip'].innerHTML, /AI信号/);
        assert.doesNotMatch(elements['sd-trust-strip'].innerHTML, /PEG 缺失/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_switch_tab_stock_respects_auto_open_stock_false():
    app_shell = read("dashboard/static/core/app-shell.js")

    stock_branch = app_shell[
        app_shell.index("else if (activeTab === 'stock')") : app_shell.index(
            "else if (activeTab === 'intelligence')"
        )
    ]

    assert "if (options.autoOpenStock === false) {" in stock_branch
    assert "return;" in stock_branch
    assert "const fallbackCode" not in stock_branch


def test_stock_detail_can_explicitly_wait_for_deferred_modules():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement() {
            return {
                style: {},
                classList: { toggle: () => {} },
                setAttribute: () => {},
                innerHTML: '',
                querySelector: () => null,
            };
        }

        let resolveDeferred;
        let settled = false;
        let valuationStarted = false;

        global.window = global;
        global.globalThis = global;
        global.document = {
            getElementById: () => makeElement(),
        };
        global.App = {
            watchlistCache: [],
            syncActiveStockContext: () => {},
        };
        global.GlobalStockStore = { getState: () => ({ identity: {} }) };
        global.StockDetail = {};

        vm.runInThisContext(fs.readFileSync('dashboard/static/stock-detail-core.js', 'utf8'));

        Object.assign(global.StockDetail, {
            _openGeneration: 0,
            _renderDetailPending: () => {},
            _connectL2: () => {},
            _loadDetail: async () => {},
            _loadTimeline: async () => {},
            _loadOrderBook: async () => {},
            _loadPeriodReturns: async () => {},
            _loadCapitalFlow: async () => {},
            _loadProfitTrend: async () => {},
            _loadShareholders: async () => {},
            _loadDividends: async () => {},
            _loadAnnouncements: async () => {},
            _loadIndustryComparison: async () => {},
            _loadNorthbound: async () => {},
            _loadChips: async () => {},
            _loadMultiTimeframe: async () => {},
            _loadDragonTiger: async () => {},
            _loadReports: async () => {},
            _loadValuationSnapshot: async () => {
                valuationStarted = true;
                await new Promise((resolve) => { resolveDeferred = resolve; });
            },
            _loadAlphaSignals: async () => {},
            _loadNews: async () => {},
        });

        const pending = global.StockDetail.open('600519', {
            awaitDeferredLoad: true,
        }).then(() => {
            settled = true;
        });

        await new Promise((resolve) => setTimeout(resolve, 25));
        assert.equal(valuationStarted, true);
        assert.equal(settled, false);

        resolveDeferred();
        await pending;
        assert.equal(settled, true);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_detail_valuation_failure_still_renders_source_evidence():
    valuation = read("dashboard/static/stock-detail-valuation.js")

    assert "source: '估值服务'" in valuation
    assert "source_version: 'unavailable'" in valuation
    assert "quality_status: 'degraded'" in valuation
    assert "估值数据加载失败" not in valuation


def test_open_offcanvas_keeps_right_rail_context_when_detail_fetch_fails():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const panel = {
            classList: {
                values: new Set(),
                add(value) { this.values.add(value); },
                remove(value) { this.values.delete(value); },
                contains(value) { return this.values.has(value); },
            },
            setAttribute(name, value) { this[name] = value; },
        };
        const body = { innerHTML: '' };
        const title = { textContent: '' };
        const overlay = { classList: { add: () => {}, remove: () => {} } };
        let railActivation = null;
        let syncedCode = null;

        global.window = global;
        global.document = {
            getElementById: (id) => {
                if (id === 'stock-offcanvas') return panel;
                if (id === 'offcanvas-overlay') return overlay;
                if (id === 'offcanvas-body') return body;
                if (id === 'offcanvas-title') return title;
                return null;
            },
            addEventListener: () => {},
        };
        global.PanelLifecycle = {
            has: () => true,
            mountRoot: () => {},
        };
        global.RightRailController = {
            activatePanel: (params) => { railActivation = params; },
            syncStockContext: () => {},
        };
        global.App = {
            LLM: {},
            fetchJSON: async () => { throw new Error('detail unavailable'); },
            syncActiveStockContext: (code) => { syncedCode = code; },
            escapeHTML: (value) => String(value ?? ''),
            _fmtVol: (value) => String(value),
            _fmtAmt: (value) => String(value),
            _tabCache: {},
            _tabAlias: {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));

        await global.App.openOffcanvas('600519');

        assert.equal(panel.classList.contains('active'), true);
        assert.equal(panel['aria-hidden'], 'false');
        assert.equal(railActivation?.panelId, 'stock-offcanvas');
        assert.equal(railActivation?.panelParams?.code, '600519');
        assert.equal(railActivation?.autoOpen, true);
        assert.match(body.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_changed_frontend_assets_are_cache_busted():
    app = read("dashboard/static/app.js")
    scripts = read("dashboard/templates/partials/scripts.html")
    template = read("dashboard/templates/index.html")
    search = read("dashboard/static/search.js")
    watchlist = read("dashboard/static/watchlist.js")
    workbench = read("dashboard/static/app-workbench.js")
    compare = read("dashboard/static/compare.js")
    paper_trading = read("dashboard/static/paper-trading.js")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")
    alpha = read("dashboard/static/alpha.js")
    alpha_tools = read("dashboard/static/alpha-tools.js")

    assert "/static/style.css?v=82" in template
    assert "/static/search.js?v=14" in scripts
    assert "/static/watchlist.js?v=10" in scripts
    assert "/static/app.js?v=132" in scripts
    assert "/static/app-stock-ops.js?v=12" in scripts
    assert "/static/core/business-adapter.js?v=5" in scripts
    assert "/static/core/app-shell.js?v=36" in scripts
    assert "/static/core/command-palette.js?v=2" in scripts
    assert "/static/app-ui-shell.js?v=45" in scripts
    assert "/static/app-workbench.js?v=3" in scripts
    assert "/static/openclaw-conversations.js?v=3" in scripts
    assert "/static/openclaw-workbench.js?v=26" in scripts
    assert "/static/app-bootstrap.js?v=25" in scripts
    assert "/static/overview.js?v=32" in scripts
    assert "/static/overview.js?v=32" in app
    assert "/static/alerts.js?v=4" in scripts
    assert "/static/alerts.js?v=4" in app
    assert "/static/overview-radar.js?v=11" in scripts
    assert "/static/overview-radar.js?v=11" in app
    assert "/static/paper.js?v=11" in app
    assert "/static/paper-trading.js?v=8" in app
    assert "/static/backtest-strategies.js?v=2" in app
    assert "/static/compare.js?v=5" in app
    assert "/static/alpha.js?v=6" in app
    assert "/static/alpha-tools.js?v=13" in app
    assert "/static/screener-ai.js?v=2" in app
    assert "/static/research-datahub.js?v=25" in app
    assert "/static/research-valuation.js?v=16" in app
    assert "/static/stock-detail-core.js?v=21" in app
    assert "/static/stock-detail-research.js?v=2" in app
    assert "/static/stock-detail-timeline.js?v=6" in app
    assert "/static/stock-detail-kline.js?v=5" in app
    assert "/static/stock-detail-data.js?v=2" in app
    assert "/static/stock-detail-market-mtf.js?v=2" in app
    assert "/static/stock-detail-valuation.js?v=14" in app
    assert "/static/openclaw-conversations.js?v=3" in app
    assert "/static/openclaw-workbench.js?v=26" in app
    assert "/static/intelligence.js?v=17" in app

    assert "minQueryLength" in search
    assert "stockSearchEmptyScopeItems" in search
    assert "globalThis.App || (typeof App !== 'undefined' ? App : {})" in search
    assert "minQueryLength: 1" in watchlist
    assert "/api/stock/search?q=&limit=6000" not in workbench
    assert "/api/stock/search?q=&limit=6000" not in watchlist
    assert "/api/stock/search?limit=200" not in compare
    assert "App._allStocks" not in paper_trading
    assert "if (!q) return [];" in watchlist
    assert "watchlist-empty-state" in watchlist
    assert ".watchlist-empty-state" in read("dashboard/static/style.css")
    assert "当前账号" in watchlist
    assert "当前工作区" in watchlist
    assert "emptyScope: 'watchlist'" in workbench
    assert "emptyScope: 'watchlist'" in datahub
    assert "emptyScope: 'watchlist'" in valuation
    assert "minQueryLength: 1" in datahub
    assert "minQueryLength: 1" in valuation
    assert "自选股为空，输入代码或名称搜索全市场" in datahub
    assert "自选股为空，输入代码或名称搜索全市场" in valuation
    assert "自选股为空，输入代码或名称搜索全市场" in paper_trading
    assert "自选股为空，输入代码或名称搜索全市场" in workbench
    assert "_fmtPeg(item.peg_next_year)" in datahub
    assert "_fmtQlib(item)" in datahub
    assert "datahub-empty-state" in datahub
    assert ".datahub-empty-state" in read("dashboard/static/style.css")
    assert "_metaLine" not in datahub
    assert "datahub-stock-meta" in datahub
    assert "datahub-missing-badge" in datahub
    assert "inlineFilter" in search
    assert "sb-no-inline-filter" in search
    assert "initFormulaBasketPickers" in alpha
    assert "_alphaActionHandlersBound" in alpha
    assert "_alphaInitDone" not in alpha
    assert "new SearchBox('formula-code', 'formula-code-dropdown'" in alpha_tools
    assert "new MultiSearchBox('basket-code-input', 'basket-code-dropdown', 'basket-code-tags'" in alpha_tools
    assert "emptyScope: 'watchlist'" in alpha_tools
    assert "minQueryLength: 1" in alpha_tools
    assert "自选股为空，输入代码或名称搜索全市场" in alpha_tools
    assert "basket-use-watchlist" in template
    assert "basket-clear-candidates" in template
    assert "全市场选股" in template
    assert "basket-advanced-json" in template


def test_global_search_top_entry_copy_advertises_market_function_question_router():
    template = read("dashboard/templates/index.html")
    scripts = read("dashboard/templates/partials/scripts.html")
    command_palette = read("dashboard/static/core/command-palette.js")
    combined = "\n".join([template, command_palette])

    assert "/static/core/command-palette.js" in scripts
    assert "global.CommandPalette" in command_palette
    assert 'id="cmd-palette-input"' in template

    placeholder_text = "\n".join(
        value
        for groups in re.findall(
            r'placeholder="([^"]*)"|placeholder:\s*[\'"]([^\'"]*)[\'"]',
            combined,
        )
        for value in groups
        if value
    )
    assert "行情" in placeholder_text
    assert "功能" in placeholder_text
    assert "问句" in placeholder_text


def test_global_search_exposes_golden_questions_for_task_router_contracts():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.IntentBus = { emit: () => {}, createTraceId: (prefix) => `${prefix}:trace` };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async ({ query }) => ({
                status: 'ok',
                results: /600519|贵州茅台/.test(query)
                    ? [{ code: '600519', name: '贵州茅台', market: 'SH', exchange: 'SSE', label: '600519 贵州茅台' }]
                    : [],
            }),
            resolveSelection: async () => ({ ok: true, revision: 1, state: {} }),
        };
        global.LocalMCP = {
            listTools: ({ query }) => [
                {
                    id: 'global-search:function:paper',
                    title: '打开模拟盘',
                    category: 'function',
                    visible: true,
                    enabled: true,
                    keywords: ['打开模拟盘'],
                    metadata: { intent_type: 'function_nav', bucket: 'functions', raw_query: query },
                },
                {
                    id: 'global-search:function:datahub',
                    title: '切到数据中枢',
                    category: 'function',
                    visible: true,
                    enabled: true,
                    keywords: ['切到数据中枢'],
                    metadata: { intent_type: 'function_nav', bucket: 'functions', raw_query: query },
                },
            ],
            invoke: async () => ({ ok: true, status: 'success', output: {} }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        const palette = global.CommandPalette;
        assert.equal(
            typeof palette?.getGoldenQuestions,
            'function',
            'command palette should expose the Global Search/iWencai golden question set for frontend contracts'
        );

        const goldenQuestions = palette.getGoldenQuestions();
        assert.ok(Array.isArray(goldenQuestions), 'golden questions should be returned as an array');
        assert.ok(goldenQuestions.length >= 20, 'golden question set should cover at least 20 router examples');

        const requiredIntents = new Set([
            'stock_lookup',
            'function_nav',
            'natural_language_screener',
            'market_topic',
            'market_question',
        ]);
        const allowedRoutes = new Set(['stock', 'function', 'iwencai']);
        const allowedFailureStatuses = new Set([
            'failed',
            'no_match',
            'degraded_data',
            'partial_result',
            'needs_disambiguation',
            'requires_confirmation',
        ]);
        const requiredFailureStatuses = [
            'failed',
            'no_match',
            'degraded_data',
            'partial_result',
            'requires_confirmation',
        ];
        const statusLikeIdPattern = /failed|failure|timeout|no[_-]?match|degraded|partial|disambiguation|confirmation|requires/i;
        const querySet = new Set();

        function primaryBucket(item) {
            return item.bucket || item.primary_bucket || item.primaryBucket || null;
        }

        function normalizeStatusList(value) {
            if (Array.isArray(value)) return value.filter(Boolean);
            if (typeof value === 'string' && value.trim()) return [value.trim()];
            return [];
        }

        for (const [index, item] of goldenQuestions.entries()) {
            assert.equal(typeof item.query, 'string', `golden question ${index} should have query`);
            assert.ok(item.query.trim(), `golden question ${index} should have a non-empty query`);
            assert.ok(!querySet.has(item.query), `golden question query should be unique: ${item.query}`);
            querySet.add(item.query);
            assert.ok(requiredIntents.has(item.intent_type), `golden question should declare supported intent_type: ${item.query}`);
            assert.ok(primaryBucket(item), `golden question should declare bucket/primary bucket: ${item.query}`);
            assert.ok(allowedRoutes.has(item.route), `golden question should declare route: ${item.query}`);

            const declaredStatuses = [
                ...normalizeStatusList(item.expected_status),
                ...normalizeStatusList(item.allowed_fallback_status),
            ];
            declaredStatuses.forEach((status) => {
                assert.ok(allowedFailureStatuses.has(status), `golden question status should be a known failure/degraded status: ${status}`);
            });
            if (statusLikeIdPattern.test(`${item.id || ''} ${item.query}`)) {
                assert.ok(
                    declaredStatuses.length > 0,
                    `failure/degraded golden question should declare expected_status or allowed_fallback_status: ${item.query}`
                );
            }
        }

        const byIntent = new Map(goldenQuestions.map((item) => [item.intent_type, item]));
        for (const intentType of requiredIntents) {
            assert.ok(byIntent.has(intentType), `golden questions should include ${intentType}`);
        }

        const failureStates = new Set(
            goldenQuestions
                .flatMap((item) => [
                    ...normalizeStatusList(item.expected_status),
                    ...normalizeStatusList(item.allowed_fallback_status),
                ])
        );
        for (const status of requiredFailureStatuses) {
            assert.ok(failureStates.has(status), `golden questions should include ${status} coverage`);
        }

        for (const item of goldenQuestions) {
            const classification = await palette.classifyIntent(item.query);
            assert.equal(classification.type, item.intent_type, `golden query intent should round-trip: ${item.query}`);
            assert.equal(classification.bucket, primaryBucket(item), `golden query bucket should round-trip: ${item.query}`);
            assert.equal(classification.route || item.route, item.route, `golden query route should round-trip: ${item.query}`);
            if (item.expected_status) {
                assert.equal(
                    classification.expected_status,
                    item.expected_status,
                    `golden query expected_status should round-trip: ${item.query}`
                );
            }
        }
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_global_search_task_router_classifies_core_intents():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.IntentBus = {
            emit: () => {},
            createTraceId: (prefix) => `${prefix}:trace`,
        };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async ({ query }) => ({
                status: 'ok',
                results: /600519|贵州茅台/.test(query)
                    ? [{ code: '600519', name: '贵州茅台', market: 'SH', exchange: 'SSE', label: '600519 贵州茅台' }]
                    : [],
            }),
            resolveSelection: async () => ({ ok: true, revision: 1, state: {} }),
        };
        global.LocalMCP = {
            listTools: ({ query }) => [
                {
                    id: 'global-search:function:paper',
                    title: '打开模拟盘',
                    description: '跳转模拟盘',
                    category: 'function',
                    visible: true,
                    enabled: true,
                    keywords: ['打开模拟盘', '功能'],
                    metadata: { intent_type: 'function_nav', bucket: 'functions', raw_query: query },
                },
                {
                    id: 'global-search:function:datahub',
                    title: '数据中枢',
                    description: '跳转数据中枢',
                    category: 'function',
                    visible: true,
                    enabled: true,
                    keywords: ['切到数据中枢', '功能'],
                    metadata: { intent_type: 'function_nav', bucket: 'functions', raw_query: query },
                },
                {
                    id: 'global-search:task:iwencai',
                    title: '问财自然语言选股',
                    description: '路由到 iWencai',
                    category: 'screener',
                    visible: true,
                    enabled: true,
                    keywords: ['ROE', '放量', '自然语言选股'],
                    metadata: { intent_type: 'natural_language_screener', bucket: 'screener', raw_query: query },
                },
                {
                    id: 'global-search:task:market-topic',
                    title: '市场主题问答',
                    description: '路由到市场问答',
                    category: 'question',
                    visible: true,
                    enabled: true,
                    keywords: ['为什么上涨', '半导体'],
                    metadata: { intent_type: 'market_topic', bucket: 'questions', raw_query: query },
                },
            ],
            invoke: async () => ({ ok: true, status: 'success', output: {} }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        function extractIntent(result) {
            if (typeof result === 'string') return result;
            return result?.intent_type
                || result?.intent
                || result?.type
                || result?.activeIntent?.type
                || result?.classification?.intent_type
                || result?.classification?.type
                || null;
        }

        const palette = global.CommandPalette;
        assert.equal(typeof palette?.open, 'function', 'command-palette.js must expose CommandPalette.open');

        async function intentOf(query) {
            if (typeof palette.classifyIntent === 'function') {
                return extractIntent(await palette.classifyIntent(query));
            }
            await palette.open({ query, source: 'global_search' });
            return extractIntent(palette.getState());
        }

        assert.equal(await intentOf('600519'), 'stock_lookup');
        assert.equal(await intentOf('贵州茅台'), 'stock_lookup');
        assert.equal(await intentOf('打开模拟盘'), 'function_nav');
        assert.equal(await intentOf('切到数据中枢'), 'function_nav');
        assert.equal(await intentOf('近5日放量且ROE大于15%'), 'natural_language_screener');
        assert.ok(
            ['market_topic', 'question'].includes(await intentOf('半导体今天为什么上涨？')),
            'market/topic question queries should not be classified as stock/function navigation'
        );
        assert.equal(await intentOf('今天市场最大的风险是什么？'), 'market_question');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_global_search_results_are_grouped_into_actionable_buckets():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.IntentBus = { emit: () => {}, createTraceId: (prefix) => `${prefix}:trace` };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async () => ({ status: 'ok', results: [] }),
            resolveSelection: async () => ({ ok: true, revision: 1, state: {} }),
        };
        global.LocalMCP = {
            listTools: ({ query }) => [
                {
                    id: 'global-search:task:iwencai',
                    title: '问财自然语言选股',
                    description: '近5日放量且ROE大于15%',
                    category: 'screener',
                    visible: true,
                    enabled: true,
                    keywords: ['ROE', '放量'],
                    metadata: {
                        intent_type: 'natural_language_screener',
                        bucket: 'screener',
                        raw_query: query,
                    },
                },
            ],
            invoke: async () => ({ ok: true, status: 'success', output: {} }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        const query = '近5日放量且ROE大于15%';
        await CommandPalette.open({ query, source: 'global_search' });
        const state = CommandPalette.getState();
        const taskResults = [
            ...(Array.isArray(state.taskResults) ? state.taskResults : []),
            ...(Array.isArray(state.mergedResults)
                ? state.mergedResults.filter((item) => item.kind === 'task' || item.type === 'task')
                : []),
        ];
        const buckets = [
            ...(Array.isArray(state.buckets) ? state.buckets : []),
            ...(Array.isArray(state.resultBuckets) ? state.resultBuckets : []),
        ].map((bucket) => bucket.id || bucket.type || bucket.name);
        const screenerTask = taskResults.find((item) => {
            return (item.bucket || item.metadata?.bucket) === 'screener'
                && (item.intent_type || item.metadata?.intent_type) === 'natural_language_screener';
        });

        assert.equal(
            state.activeIntent?.type || state.intent?.type || state.intent_type,
            'natural_language_screener',
            'command palette should classify screener questions as natural_language_screener'
        );
        assert.ok(screenerTask, 'natural language screener should be represented as a task result, not a plain function action');
        assert.ok(buckets.includes('screener'), 'global search task results should keep an actionable screener bucket');
        assert.equal(screenerTask.source_context?.source || screenerTask.metadata?.source_context?.source, 'global_search');
        assert.equal(screenerTask.source_context?.raw_query || screenerTask.metadata?.source_context?.raw_query, query);
        assert.equal(
            screenerTask.source_context?.intent_type || screenerTask.metadata?.source_context?.intent_type,
            'natural_language_screener'
        );
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_global_search_routes_natural_language_screener_to_iwencai_with_context():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        const iwencaiApi = {
            runIwencai: async (params) => { calls.push({ type: 'iwencai', params }); },
            runQuery: async (params) => { calls.push({ type: 'iwencai', params }); },
            submitQuery: async (params) => { calls.push({ type: 'iwencai', params }); },
            search: async (params) => { calls.push({ type: 'iwencai', params }); },
        };
        global.Intelligence = iwencaiApi;
        global.IntelligenceIWenCai = iwencaiApi;
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            switchTab: async (tab, options) => { calls.push({ type: 'switchTab', tab, options }); },
            openStockDetail: async () => { calls.push({ type: 'openStockDetail' }); },
            ensureBundle: async (name) => { calls.push({ type: 'ensureBundle', name }); },
            fetchJSON: async (url, options) => {
                calls.push({ type: 'fetchJSON', url, options });
                return { success: true, data: [], buckets: [], source_context: JSON.parse(options?.body || '{}').source_context };
            },
            toast: () => {},
        };
        global.IntentBus = { emit: () => {}, createTraceId: (prefix) => `${prefix}:trace` };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async () => ({ status: 'ok', results: [] }),
            resolveSelection: async () => ({ ok: true, revision: 1, state: {} }),
        };
        global.LocalMCP = {
            listTools: () => [],
            invoke: async () => ({ ok: true, status: 'success', output: {} }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        const query = '近5日放量且ROE大于15%';
        const sourceContext = {
            source: 'global_search',
            raw_query: query,
            intent_type: 'natural_language_screener',
            bucket: 'screener',
        };
        const taskItem = {
            kind: 'task',
            id: 'global-search:screener:test',
            bucket: 'screener',
            type: 'screener',
            intent_type: 'natural_language_screener',
            title: '问财自然语言选股',
            raw_query: query,
            query,
            source_context: sourceContext,
            metadata: { source_context: sourceContext },
        };

        try {
            await CommandPalette.executeItem({
                item: taskItem,
                closeOnSuccess: false,
                source: 'global_search',
            });
        } catch (error) {
            assert.fail(`command palette should accept global_search task results and route them to iWencai: ${error.message}`);
        }

        assert.ok(
            calls.some((call) => call.type === 'switchTab' && call.tab === 'intelligence'),
            'natural language screener queries should switch to intelligence before running iWencai'
        );

        const iwencaiCall = calls.find((call) => {
            return call.type === 'iwencai'
                || (call.type === 'fetchJSON' && call.url === '/api/llm/iwencai');
        });
        assert.ok(iwencaiCall, 'natural language screener queries should be delegated to iWencai');
        const params = iwencaiCall.type === 'fetchJSON'
            ? JSON.parse(iwencaiCall.options?.body || '{}')
            : (iwencaiCall.params || {});
        assert.equal(params.raw_query || params.rawQuery || params.query, query);
        assert.equal(params.intent_type || params.intentType, 'natural_language_screener');
        assert.equal(params.source_context?.source, 'global_search');
        assert.equal(params.source_context?.raw_query, query);
        assert.equal(params.source_context?.intent_type, 'natural_language_screener');
        assert.ok(!calls.some((call) => call.type === 'openStockDetail'));
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_global_search_task_execution_waits_for_lazy_loaded_run_iwencai():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        const input = { value: '' };
        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: (id) => id === 'intel-iwencai-input' ? input : null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            ensureBundle: async (name) => {
                calls.push({ type: 'ensureBundle', name });
                setTimeout(() => {
                    global.Intelligence = {
                        bindIwencai: () => { calls.push({ type: 'bindIwencai' }); },
                        runIwencai: async (params) => {
                            calls.push({ type: 'runIwencai', params, inputValue: input.value });
                            return {
                                status: 'partial_result',
                                source_context: params.source_context,
                            };
                        },
                    };
                }, 75);
            },
            switchTab: async (tab) => { calls.push({ type: 'switchTab', tab }); },
            toast: () => {},
        };
        global.IntentBus = { emit: () => {}, createTraceId: (prefix) => `${prefix}:trace` };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async () => ({ status: 'ok', results: [] }),
            resolveSelection: async () => ({ ok: true, revision: 1, state: {} }),
        };
        global.LocalMCP = {
            listTools: () => [],
            invoke: async () => ({ ok: true, status: 'success', output: {} }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        const query = '近5日放量且ROE大于15%';
        const result = await CommandPalette.executeItem({
            closeOnSuccess: false,
            source: 'global_search',
            item: {
                kind: 'task',
                id: 'global-search:screener:lazy-iwencai',
                title: '问财自然语言选股',
                query,
                raw_query: query,
                intent: { type: 'natural_language_screener', confidence: 0.86 },
                intent_type: 'natural_language_screener',
                bucket: 'screener',
                source_context: {
                    source: 'global_search',
                    raw_query: query,
                    intent_type: 'natural_language_screener',
                    selected_bucket: 'screener',
                    result_pool_id: 'global-search:lazy-iwencai',
                },
            },
        });

        assert.equal(result.ok, true);
        assert.deepEqual(calls.map((call) => call.type).slice(0, 4), [
            'ensureBundle',
            'switchTab',
            'bindIwencai',
            'runIwencai',
        ]);
        const runCall = calls.find((call) => call.type === 'runIwencai');
        assert.ok(runCall, 'task execution should wait until lazy loaded Intelligence.runIwencai is available');
        assert.equal(runCall.params.query, query);
        assert.equal(runCall.inputValue, query);
        assert.equal(runCall.params.source_context.source, 'global_search');
        assert.equal(runCall.params.source_context.intent_type, 'natural_language_screener');
        assert.equal(result.result.source_context.result_pool_id, 'global-search:lazy-iwencai');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_run_preserves_source_context_and_renders_failure_degraded_states():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const input = makeElement('intel-iwencai-input');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': makeElement('intel-iwencai-btn'),
            'intel-iwencai-result': result,
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            readyState: 'complete',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        const stockRow = { '股票代码': '600000.SH', '股票简称': '浦发银行', '最新价': 8.5, '最新涨跌幅': 1.2 };
        const blockedStatuses = new Set(['failed', 'no_match', 'partial_result', 'degraded_data', 'needs_disambiguation', 'requires_confirmation']);
        const writeOrBulkActionPattern = /data-intel-action="iwencai-(?:send-screener|add-watchlist|add-one-watchlist|create-basket|draft-backtest)"/;
        const cases = [
            {
                status: 'failed',
                label: '失败',
                intentType: 'market_question',
                query: '问财接口超时后保留上下文',
                reason: '问财接口超时',
                response: {
                    success: false,
                    status: 'failed',
                    error: '问财接口超时',
                    total: 0,
                    data: [],
                    parsed_conditions: [
                        { raw_text: '问财接口超时', field: '接口', status: 'failed', unavailable_reason: '问财接口超时' },
                    ],
                },
            },
            {
                status: 'no_match',
                label: '无匹配',
                intentType: 'market_question',
                query: '不存在的奇怪条件abcxyz只看火星概念',
                reason: '无匹配股票',
                response: {
                    success: true,
                    status: 'no_match',
                    missing_reason: '无匹配股票',
                    total: 0,
                    data: [],
                    parsed_conditions: [
                        { raw_text: '火星概念', field: '未知条件', status: 'no_match', hit_count: 0, unavailable_reason: '无匹配股票' },
                    ],
                },
            },
            {
                status: 'degraded_data',
                label: '数据降级',
                intentType: 'natural_language_screener',
                query: '字段命中数不可用时显示原因',
                reason: '命中数待回填',
                response: {
                    success: true,
                    status: 'degraded_data',
                    degraded_reason: '命中数待回填',
                    total: 1,
                    data: [stockRow],
                    parsed_conditions: [
                        { raw_text: '近5日放量', field: '成交量', status: 'degraded_data', unavailable_reason: '命中数待回填' },
                    ],
                },
            },
            {
                status: 'partial_result',
                label: '部分结果',
                intentType: 'market_question',
                query: '只有候选股没有新闻证据时如何处理',
                reason: '新闻证据缺失',
                response: {
                    success: true,
                    status: 'partial_result',
                    missing_reason: '新闻证据缺失',
                    total: 1,
                    data: [stockRow],
                    parsed_conditions: [
                        { raw_text: '候选股', field: '候选池', status: 'ready', hit_count: 1 },
                        { raw_text: '新闻证据', field: '新闻', status: 'degraded_data', unavailable_reason: '新闻证据缺失' },
                    ],
                    buckets: [
                        { id: 'candidates', name: '候选股票', count: 1, items: [stockRow], status: 'partial_result' },
                        { id: 'news', name: '新闻证据', count: 0, items: [], status: 'degraded_data', description: '新闻证据缺失' },
                    ],
                },
            },
            {
                status: 'needs_disambiguation',
                label: '需要澄清',
                intentType: 'market_question',
                query: '银行高股息到底看A股还是港股',
                reason: '需要补充市场范围',
                response: {
                    success: true,
                    status: 'needs_disambiguation',
                    failure_type: 'ambiguous_market_scope',
                    missing_reason: '需要补充市场范围',
                    next_action: '选择 A 股、港股或全部市场后再执行',
                    total: 1,
                    data: [stockRow],
                    actions: ['open_stock', 'add_watchlist', 'send_screener', 'ask_ai', 'create_basket', 'draft_backtest'],
                    parsed_conditions: [
                        { raw_text: '银行高股息', field: '市场范围', status: 'needs_disambiguation', hit_count: 1, unavailable_reason: 'A股/港股范围不明确' },
                    ],
                    buckets: [
                        { id: 'candidates', name: '候选股票', count: 1, items: [stockRow], status: 'needs_disambiguation', description: '需要补充市场范围' },
                        { id: 'clarification', name: '澄清项', count: 0, items: [], status: 'needs_disambiguation', description: '选择 A 股、港股或全部市场' },
                    ],
                },
            },
            {
                status: 'requires_confirmation',
                label: '需要确认',
                intentType: 'market_question',
                query: '把这批股票全部加入自选',
                reason: '写入自选需要确认',
                response: {
                    success: true,
                    status: 'requires_confirmation',
                    failure_type: 'write_confirmation_required',
                    missing_reason: '写入自选需要确认',
                    next_action: '确认写入前先检查候选池',
                    total: 1,
                    data: [stockRow],
                    actions: ['open_stock', 'add_watchlist', 'send_screener', 'ask_ai', 'create_basket', 'draft_backtest'],
                    parsed_conditions: [
                        { raw_text: '全部加入自选', field: '写入动作', status: 'requires_confirmation', hit_count: 1, unavailable_reason: '需要用户确认' },
                    ],
                    buckets: [
                        { id: 'candidates', name: '候选股票', count: 1, items: [stockRow], status: 'requires_confirmation', description: '确认后才能批量写入' },
                    ],
                },
            },
        ];

        for (const item of cases) {
            const resultPoolId = `iwencai:${item.status}:golden`;
            const sourceContext = {
                source: 'global_search',
                sourceLabel: '全局搜索',
                context_type: 'global_search_task',
                raw_query: item.query,
                query: item.query,
                intent_type: item.intentType,
                selected_bucket: 'candidates',
                result_pool_id: resultPoolId,
                rank_reason: `全局搜索: ${item.query}`,
            };

            input.value = item.query;
            App.fetchJSON = async (url, options) => {
                assert.equal(url, '/api/llm/iwencai');
                const body = JSON.parse(options.body);
                assert.equal(body.query, item.query);
                assert.equal(body.intent_type, item.intentType);
                assert.equal(body.source_context.raw_query, item.query);
                return {
                    ...item.response,
                    intent: {
                        type: item.intentType,
                        confidence: 0.81,
                        reason: `按 ${item.intentType} 路由`,
                    },
                    source_context: sourceContext,
                };
            };

            const viewModel = await Intelligence.runIwencai({
                query: item.query,
                source_context: sourceContext,
                selected_bucket: 'candidates',
            });

            assert.equal(viewModel.status, item.status);
            assert.equal(viewModel.intent.type, item.intentType);
            assert.ok(Array.isArray(viewModel.parsed_conditions) && viewModel.parsed_conditions.length > 0);
            assert.ok(viewModel.parsed_conditions.every((condition) => condition.raw_text && condition.field && condition.status));
            assert.deepEqual(viewModel.source_context.parsed_conditions, viewModel.parsed_conditions);
            assert.ok(Array.isArray(viewModel.buckets) && viewModel.buckets.length >= 1);
            assert.ok(viewModel.buckets.some((bucket) => bucket.id === 'candidates'));
            assert.ok(Array.isArray(viewModel.actions) && viewModel.actions.length > 0);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.source, 'global_search');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.result_pool_id, resultPoolId);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.raw_query, item.query);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.intent_type, item.intentType);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.status_reason, item.reason);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.selected_bucket, 'candidates');
            assert.ok(
                Object.prototype.hasOwnProperty.call(
                    Intelligence.state.iwencaiActionState.source_context.condition_hit_count,
                    item.response.parsed_conditions[0].raw_text
                )
            );
            assert.match(result.innerHTML, new RegExp(`data-iwencai-status="${item.status}"`));
            assert.match(result.innerHTML, new RegExp(`status-${item.status}`));
            assert.match(result.innerHTML, new RegExp(item.label));
            assert.match(result.innerHTML, new RegExp(item.reason));
            assert.match(result.innerHTML, /iwencai-status-note/);
            assert.doesNotMatch(result.innerHTML, />undefined</);
            assert.doesNotMatch(result.innerHTML, /类型: undefined/);
            assert.match(result.innerHTML, /iwencai-condition-chip/);
            assert.match(result.innerHTML, /iwencai-bucket-tabs/);
            assert.match(result.innerHTML, /候选股票/);
            assert.match(result.innerHTML, /来源上下文已保留/);
            if (item.status === 'failed' || item.status === 'no_match') {
                assert.match(result.innerHTML, /暂无候选股票/);
                assert.doesNotMatch(result.innerHTML, /iwencai-focused-table/);
            } else {
                assert.match(result.innerHTML, /iwencai-focused-table/);
                assert.match(result.innerHTML, /浦发银行/);
            }
            if (blockedStatuses.has(item.status)) {
                assert.doesNotMatch(
                    result.innerHTML,
                    writeOrBulkActionPattern,
                    `${item.status} should not expose write or bulk actions before unblock/confirmation`
                );
            } else {
                assert.match(result.innerHTML, /data-intel-action="iwencai-send-screener"/);
                assert.match(result.innerHTML, /data-intel-action="iwencai-add-watchlist"/);
            }
        }
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_provider_failure_blocks_write_actions_even_with_cached_candidates():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const input = makeElement('intel-iwencai-input');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': makeElement('intel-iwencai-btn'),
            'intel-iwencai-result': result,
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            readyState: 'complete',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        const stockRow = { '股票代码': '600000.SH', '股票简称': '浦发银行', '最新价': 8.5, '最新涨跌幅': 1.2 };
        const cases = [
            {
                providerStatus: 'rate_limited',
                sourceStatus: 'rate_limited',
                issueType: 'rate_limited',
                reason: '问财源限流或访问频率受限，请稍后重试',
                label: '源限流',
            },
            {
                providerStatus: 'provider_unavailable',
                sourceStatus: 'unavailable',
                issueType: 'provider_unavailable',
                reason: 'pywencai 未安装，问财查询不可用',
                label: '源不可用',
            },
            {
                providerStatus: 'invalid_provider_response',
                sourceStatus: 'invalid_response',
                issueType: 'invalid_provider_response',
                reason: '问财返回格式异常，无法稳定解析为候选池',
                label: '源响应异常',
                cacheStatus: 'live_request',
            },
            {
                providerStatus: 'ok',
                sourceStatus: 'ok',
                issueType: 'stale_cache',
                reason: '当前结果来自旧缓存或数据日期偏旧',
                label: '缓存过期',
                cacheStatus: 'stale_cache',
                omitTopFailureType: true,
            },
        ];
        const writeOrBulkActionPattern = /data-intel-action="iwencai-(?:send-screener|add-watchlist|add-one-watchlist|create-basket|draft-backtest)"/;

        for (const item of cases) {
            input.value = `provider ${item.providerStatus}`;
            App.fetchJSON = async () => ({
                success: true,
                status: 'partial_result',
                failure_type: item.omitTopFailureType ? '' : item.issueType,
                failure_reason: item.reason,
                total: 1,
                data: [stockRow],
                actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
                parsed_conditions: [
                    { raw_text: '高股息', field: '股息率', status: 'ready', hit_count: 1 },
                ],
                buckets: [
                    { id: 'candidates', name: '候选股票', count: 1, items: [stockRow], status: 'partial_result' },
                ],
                source_status: {
                    provider: 'iwencai',
                    status: item.sourceStatus,
                    provider_status: item.providerStatus,
                    type: item.issueType,
                    reason: item.reason,
                    data_as_of: '2026-06-10T10:00:00+00:00',
                    cache_status: item.cacheStatus || 'live_request',
                    response_type: 'FakeResponse',
                },
            });

            const viewModel = await Intelligence.runIwencai({ query: input.value });

            assert.equal(viewModel.status, 'partial_result');
            assert.equal(viewModel.issue.type, item.issueType);
            assert.equal(viewModel.source_context.data_status, item.sourceStatus);
            assert.equal(viewModel.source_context.provider_status, item.providerStatus);
            if (item.cacheStatus) {
                assert.equal(viewModel.source_context.cache_status, item.cacheStatus);
            }
            assert.match(result.innerHTML, new RegExp(item.label));
            assert.match(result.innerHTML, new RegExp(item.reason));
            assert.match(result.innerHTML, /iwencai-focused-table/);
            assert.match(result.innerHTML, /浦发银行/);
            assert.doesNotMatch(
                result.innerHTML,
                writeOrBulkActionPattern,
                `${item.providerStatus} should block write and bulk pool actions even with cached candidates`
            );
            assert.match(result.innerHTML, /data-intel-action="iwencai-analyze"/);
        }
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_action_guard_blocks_partial_and_degraded_status_execution():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            addEventListener: () => {},
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            readyState: 'complete',
        };
        global.App = { escapeHTML: (value) => String(value ?? ''), on: () => {} };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        for (const status of ['partial_result', 'degraded_data']) {
            Intelligence.state.iwencaiActionState = {
                candidates: [{ code: '600000', name: '浦发银行' }],
                pool: ['600000'],
                watchlistCodes: ['600000'],
                source_context: {
                    data_status: 'ok',
                    provider_status: 'ok',
                    cache_status: 'live_request',
                    failure_type: '',
                },
                viewModel: {
                    status,
                    actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
                    raw_response: {
                        source_status: {
                            status: 'ok',
                            provider_status: 'ok',
                            cache_status: 'live_request',
                        },
                    },
                },
            };

            assert.equal(Intelligence._canRunIwencaiAction('open_stock'), true);
            assert.equal(Intelligence._canRunIwencaiAction('analyze'), true);
            assert.equal(Intelligence._canRunIwencaiAction('ask_ai'), true);
            assert.equal(Intelligence._canRunIwencaiAction('send_screener', { requiresPool: true }), false);
            assert.equal(Intelligence._canRunIwencaiAction('add_watchlist', { requiresPool: true }), false);
            assert.equal(Intelligence._canRunIwencaiAction('create_basket', { requiresPool: true }), false);
            assert.equal(Intelligence._canRunIwencaiAction('draft_backtest', { requiresPool: true }), false);
        }
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_global_search_stock_and_function_results_keep_separate_routing_contexts():
    script = textwrap.dedent(
        r"""
        (async () => {
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        global.window = global;
        global.document = {
            readyState: 'complete',
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            ensureBundle: async (name) => { calls.push({ type: 'ensureBundle', name }); },
            switchTab: async (tab, options) => { calls.push({ type: 'switchTab', tab, options }); },
            openStockDetail: async (code, options) => { calls.push({ type: 'openStockDetail', code, options }); },
            toast: () => {},
        };
        global.IntentBus = { emit: () => {}, createTraceId: (prefix) => `${prefix}:trace` };
        global.GlobalStockStore = {};
        global.StockSearchService = {
            cancelActiveSearch: () => {},
            search: async () => ({ status: 'ok', results: [] }),
            resolveSelection: async (params) => {
                calls.push({ type: 'resolveSelection', params });
                return { ok: true, revision: 1, state: { selected: params.item?.code } };
            },
        };
        global.LocalMCP = {
            listTools: () => [],
            invoke: async (params) => {
                calls.push({ type: 'invoke', params });
                return {
                    ok: true,
                    traceId: params.traceId,
                    requestId: params.requestId,
                    status: 'success',
                    output: { navigated: true },
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/command-palette.js', 'utf8'));

        const stockContext = {
            source: 'global_search',
            raw_query: '茅台',
            intent_type: 'stock_lookup',
            bucket: 'stocks',
        };
        await CommandPalette.executeItem({
            item: {
                kind: 'stock',
                id: 'global-search:stock:600519',
                bucket: 'stocks',
                type: 'stock',
                intent_type: 'stock_lookup',
                code: '600519',
                name: '贵州茅台',
                metadata: { source_context: stockContext },
            },
            closeOnSuccess: false,
            source: 'global_search',
        });

        const stockOpen = calls.find((call) => call.type === 'resolveSelection');
        assert.ok(stockOpen, 'stock search results should resolve stock selection');
        assert.equal(stockOpen.params.item.code, '600519');
        assert.equal(stockOpen.params.source, 'global_search');
        assert.ok(!calls.some((call) => call.type === 'invoke'), 'stock search results must not invoke function actions');

        calls.length = 0;
        const functionContext = {
            source: 'global_search',
            raw_query: '打开数据中枢',
            intent_type: 'function_nav',
            bucket: 'functions',
        };
        await CommandPalette.executeItem({
            item: {
                kind: 'action',
                id: 'global-search:function:research-datahub',
                bucket: 'functions',
                type: 'function',
                intent_type: 'function_nav',
                title: '数据中枢',
                metadata: {
                    tab: 'research',
                    subtab: 'datahub',
                    source_context: functionContext,
                },
            },
            closeOnSuccess: false,
            source: 'global_search',
        });

        const functionCall = calls.find((call) => call.type === 'invoke');
        assert.ok(functionCall, 'function search results should invoke a function action');
        assert.equal(functionCall.params.toolId, 'global-search:function:research-datahub');
        assert.equal(functionCall.params.input?.source_context?.source, 'global_search');
        assert.ok(!calls.some((call) => call.type === 'resolveSelection'), 'function search results must not open stock detail');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_service_worker_precache_keeps_large_page_bundles_out_of_install_path():
    sw = read("dashboard/static/sw.js")

    static_assets_body = sw.split("const STATIC_ASSETS = [", 1)[1].split("];", 1)[0]

    assert "'/static/style.css'" in static_assets_body
    assert "'/static/app.js'" in static_assets_body
    assert "'/static/app-bootstrap.js'" in static_assets_body
    for large_bundle in [
        "/static/intelligence-market.js",
        "/static/intelligence-signals.js",
        "/static/research-datahub.js",
        "/static/research-valuation.js",
        "/static/stock-detail-core.js",
        "/static/openclaw-workbench.js",
        "/static/paper.js",
    ]:
        assert large_bundle not in static_assets_body


def test_stock_search_empty_watchlist_scope_renders_cached_watchlist_without_remote_fetch():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList() {
            const classes = new Set();
            return {
                add: (name) => classes.add(name),
                remove: (name) => classes.delete(name),
                toggle: (name, force) => {
                    const shouldAdd = typeof force === 'boolean' ? force : !classes.has(name);
                    if (shouldAdd) classes.add(name);
                    else classes.delete(name);
                    return shouldAdd;
                },
                contains: (name) => classes.has(name),
                toString: () => Array.from(classes).join(' '),
            };
        }

        function createElement(id) {
            const element = {
                id,
                value: '',
                readOnly: false,
                innerHTML: '',
                style: {},
                dataset: {},
                attributes: {},
                listeners: {},
                classList: makeClassList(),
                setAttribute(name, value) { this.attributes[name] = String(value); },
                getAttribute(name) { return this.attributes[name]; },
                addEventListener(name, handler) { this.listeners[name] = handler; },
                querySelector(selector) {
                    if (selector === '.sb-list') return this._list || null;
                    if (selector === '.sb-filter') return this._filter || null;
                    if (selector === '.sb-item.active') return null;
                    return null;
                },
                querySelectorAll() { return []; },
                focus() {},
                dispatchEvent(event) {
                    const handler = this.listeners[event.type || event.name];
                    if (handler) handler(event);
                },
            };
            return element;
        }

        const elements = {
            'stock-input': createElement('stock-input'),
            'stock-dropdown': createElement('stock-dropdown'),
            'basket-input': createElement('basket-input'),
            'basket-dropdown': createElement('basket-dropdown'),
            'basket-tags': createElement('basket-tags'),
        };

        Object.defineProperty(elements['stock-dropdown'], 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = String(value);
                this._list = createElement('stock-input-list');
            },
        });
        Object.defineProperty(elements['basket-dropdown'], 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = String(value);
                this._list = createElement('basket-input-list');
            },
        });

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            addEventListener: () => {},
        };
        global.Event = function Event(type) { this.type = type; };
        global.App = {
            watchlistCache: [
                { code: '300750', name: '宁德时代', industry: '电力设备' },
                { code: '600519', name: '贵州茅台', sector: '食品饮料' },
            ],
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/search.js', 'utf8'));

        let searchCalls = 0;
        const single = new SearchBox('stock-input', 'stock-dropdown', {
            minQueryLength: 1,
            emptyScope: 'watchlist',
            maxResults: 10,
        });
        single.setDataSource(() => {
            searchCalls += 1;
            return [{ code: '000001', name: '平安银行' }];
        });
        single.open();

        assert.equal(searchCalls, 0);
        assert.equal(single._items.length, 2);
        assert.match(single.listEl.innerHTML, /300750/);
        assert.match(single.listEl.innerHTML, /宁德时代/);
        assert.match(single.listEl.innerHTML, /电力设备/);
        assert.doesNotMatch(single.listEl.innerHTML, /输入代码或名称开始搜索/);

        let multiCalls = 0;
        const multi = new MultiSearchBox('basket-input', 'basket-dropdown', 'basket-tags', {
            minQueryLength: 1,
            emptyScope: 'watchlist',
            maxResults: 10,
        });
        multi.setSelected([{ code: '300750', name: '宁德时代' }]);
        multi.setDataSource(() => {
            multiCalls += 1;
            return [{ code: '000001', name: '平安银行' }];
        });
        multi.open();

        assert.equal(multiCalls, 0);
        assert.deepEqual(multi.getSelectedCodes(), ['300750']);
        assert.equal(multi._items.length, 1);
        assert.match(multi.listEl.innerHTML, /600519/);
        assert.doesNotMatch(multi.listEl.innerHTML, /300750/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_stock_search_empty_watchlist_scope_supports_lexical_app_binding():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList() {
            return { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false };
        }

        function createElement(id) {
            return {
                id,
                value: '',
                readOnly: false,
                innerHTML: '',
                style: {},
                dataset: {},
                attributes: {},
                listeners: {},
                classList: makeClassList(),
                setAttribute(name, value) { this.attributes[name] = String(value); },
                addEventListener(name, handler) { this.listeners[name] = handler; },
                querySelector(selector) {
                    if (selector === '.sb-list') return this._list || null;
                    if (selector === '.sb-filter') return null;
                    if (selector === '.sb-item.active') return null;
                    return null;
                },
                querySelectorAll() { return []; },
                focus() {},
                dispatchEvent() {},
            };
        }

        const elements = {
            'stock-input': createElement('stock-input'),
            'stock-dropdown': createElement('stock-dropdown'),
        };
        Object.defineProperty(elements['stock-dropdown'], 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = String(value);
                this._list = createElement('stock-input-list');
            },
        });

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            addEventListener: () => {},
        };
        global.Event = function Event(type) { this.type = type; };
        assert.equal(global.App, undefined);

        vm.runInThisContext(`
            const App = {
                watchlistCache: [{ code: '002594', name: '比亚迪', industry: '汽车' }],
                escapeHTML: (value) => String(value ?? '')
            };
        `);
        vm.runInThisContext(fs.readFileSync('dashboard/static/search.js', 'utf8'));

        let remoteCalls = 0;
        const search = new SearchBox('stock-input', 'stock-dropdown', {
            minQueryLength: 1,
            emptyScope: 'watchlist',
        });
        search.setDataSource(() => {
            remoteCalls += 1;
            return [];
        });
        search.open();

        assert.equal(remoteCalls, 0);
        assert.equal(search._items.length, 1);
        assert.match(search.listEl.innerHTML, /002594/);
        assert.match(search.listEl.innerHTML, /比亚迪/);
        assert.match(search.listEl.innerHTML, /汽车/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_watchlist_empty_state_names_current_workspace():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const tbody = { innerHTML: '' };
        const hint = { textContent: '' };
        const table = {
            _sortBound: false,
            querySelector: (selector) => selector === 'thead tr'
                ? { children: [
                    { textContent: '代码' },
                    { textContent: '名称' },
                    { textContent: '行业' },
                    { textContent: '板块' },
                    { textContent: '概念' },
                    { textContent: '最新价', style: {}, addEventListener: () => {} },
                    { textContent: '涨跌幅', style: {}, addEventListener: () => {} },
                ] }
                : null,
            querySelectorAll: (selector) => selector === 'thead th'
                ? [
                    { textContent: '代码' },
                    { textContent: '名称' },
                    { textContent: '行业' },
                    { textContent: '板块' },
                    { textContent: '概念' },
                    { textContent: '最新价', style: {}, addEventListener: () => {} },
                    { textContent: '涨跌幅', style: {}, addEventListener: () => {} },
                ]
                : [],
        };

        global.window = global;
        global.document = {
            getElementById: (id) => {
                if (id === 'ov-stocks-table') return table;
                if (id === 'ov-stock-hint') return hint;
                return null;
            },
            querySelector: (selector) => selector === '#ov-stocks-table tbody' ? tbody : null,
            addEventListener: () => {},
        };
        global.RealtimeQuotes = { getQuote: () => null };
        global.App = {
            _accountState: {
                user: { username: 'qa_mobile_1780798023605', display_name: 'QA Mobile' },
                workspace: {
                    name: '我的龙虾工作区',
                    slug: 'qa-mobile-1780798023605-acb3bcc7',
                },
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/search.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/watchlist.js', 'utf8'));
        Watchlist.render([]);

        assert.match(tbody.innerHTML, /暂无自选股/);
        assert.match(tbody.innerHTML, /当前工作区/);
        assert.match(tbody.innerHTML, /我的龙虾工作区/);
        assert.match(tbody.innerHTML, /qa-mobile-1780798023605-acb3bcc7/);
        assert.match(tbody.innerHTML, /QA Mobile/);
        assert.match(tbody.innerHTML, /切换账号/);
        assert.equal(hint.textContent, '');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_hash_sync_initializes_default_tab_when_cache_is_empty():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        const panel = {
            id: 'tab-overview',
            classList: { contains: () => true, toggle: () => {} },
            setAttribute: () => {},
            removeAttribute: () => {},
        };

        global.window = global;
        global.dispatchEvent = () => {};
        global.document = {
            getElementById: (id) => id === 'tab-overview' ? panel : null,
            querySelectorAll: () => [],
            querySelector: () => null,
        };
        global.location = { hash: '#overview' };
        global.history = { replaceState: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.App = {
            currentTab: 'overview',
            _tabAlias: {},
            _tabCache: {},
            loadOverview: () => calls.push('loadOverview'),
            _startMarketRefresh: () => calls.push('startMarketRefresh'),
            _stopMarketRefresh: () => calls.push('stopMarketRefresh'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));

        App._syncTabFromHash();

        setImmediate(() => {
            assert.ok(calls.includes('loadOverview'));
            assert.ok(App._tabCache.overview);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_alerts_ignores_navigation_fetch_abort_noise():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const errors = [];
        const listeners = {};
        global.window = {
            addEventListener: (name, handler) => { listeners[name] = handler; },
        };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            visibilityState: 'hidden',
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.console = { ...console, error: (...args) => errors.push(args.join(' ')) };
        global.App = {
            fetchJSON: async () => { throw new TypeError('Failed to fetch'); },
            toast: () => {},
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/alerts.js', 'utf8'));
        if (listeners.pagehide) listeners.pagehide();

        (async () => {
            await App.Alerts.loadRules();
            assert.deepEqual(errors, []);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_alerts_treats_startup_timeout_as_soft_state():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const errors = [];
        global.window = { addEventListener: () => {} };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            visibilityState: 'visible',
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.console = { ...console, error: (...args) => errors.push(args.join(' ')), warn: () => {} };
        global.App = {
            fetchJSON: async () => { throw new Error('请求超时'); },
            toast: () => {},
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/alerts.js', 'utf8'));

        (async () => {
            await App.Alerts.loadRules();
            assert.deepEqual(errors, []);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_timeout_renders_soft_placeholder():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '' };
        const overviewPanel = { classList: { contains: (name) => name === 'active' } };
        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: () => [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'tab-overview') return overviewPanel;
                return null;
            },
        };
        global.App = {
            fetchJSON: async () => { throw new Error('请求超时'); },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));

        (async () => {
            await App.OverviewRadar.loadRadar();
            assert.match(container.innerHTML, /市场雷达暂未返回/);
            assert.doesNotMatch(container.innerHTML, /请求超时|加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_first_paint_uses_fast_market_endpoints():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList(active = false) {
            let isActive = active;
            return {
                contains: (name) => name === 'active' && isActive,
                add: (name) => { if (name === 'active') isActive = true; },
                remove: (name) => { if (name === 'active') isActive = false; },
            };
        }

        const container = { innerHTML: '', offsetWidth: 720 };
        const overviewPanel = { classList: makeClassList(true) };
        const clickHandlers = {};
        const tabs = [
            'gainers',
            'sectors',
            'heatmap',
            'northbound',
        ].map((name, index) => ({
            dataset: { tab: name },
            classList: makeClassList(index === 0),
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandlers[name] = handler;
            },
        }));
        const calls = [];

        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: (selector) => selector === '.radar-tab' ? tabs : [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'tab-overview') return overviewPanel;
                if (id === 'heatmap-grid') return { innerHTML: '', offsetWidth: 720 };
                return null;
            },
        };
        global.App = {
            fetchJSON: async (url, opts = {}) => {
                calls.push(url);
                assert.equal(opts.silent, true);
                assert.equal(opts.timeout, 30000);
                if (url.includes('/api/market/radar')) {
                    return {
                        success: true,
                        source: 'local_stock_daily',
                        local_fallback: true,
                        top_gainers: [{ code: '000001', name: '平安银行', value: 10 }],
                        top_losers: [],
                        top_amplitude: [],
                        top_turnover: [],
                    };
                }
                if (url.includes('/api/market/sectors')) {
                    return { success: true, sectors: [{ name: '银行', change_pct: 1, up_count: 1, down_count: 0, leader: '平安银行' }] };
                }
                if (url.includes('/api/market/heatmap')) {
                    return { success: true, sectors: [{ name: '银行', change_pct: 1, total_mv: 100, up_count: 1, down_count: 0 }] };
                }
                if (url.includes('/api/market/northbound')) {
                    return { success: true, today_net: 0, today_sh_net: 0, today_sz_net: 0, flow: [] };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));
        App.OverviewRadar.init();

        (async () => {
            await App.OverviewRadar.loadRadar();
            assert.equal(calls.pop(), '/api/market/radar?fast=true');

            await clickHandlers.sectors();
            assert.equal(calls.pop(), '/api/market/sectors?type=industry&fast=true');

            await clickHandlers.heatmap();
            assert.equal(calls.pop(), '/api/market/heatmap?fast=true');

            await clickHandlers.northbound();
            assert.equal(calls.pop(), '/api/market/northbound?fast=true');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_updates_coverage_strip_from_fast_local_metadata():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '', offsetWidth: 720 };
        const coverage = { innerHTML: '<span>范围 全A延迟快照</span><span>排序 东方财富服务端</span>' };
        const overviewPanel = { classList: { contains: (name) => name === 'active' } };

        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: () => [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'overview-radar-coverage') return coverage;
                if (id === 'tab-overview') return overviewPanel;
                return null;
            },
        };
        global.App = {
            fetchJSON: async (url) => {
                assert.equal(url, '/api/market/radar?fast=true');
                return {
                    success: true,
                    source: 'local_stock_daily',
                    universe: 'local_stock_daily_coverage_pool',
                    local_fallback: true,
                    latest_date: '2026-06-05',
                    total_stocks: 5525,
                    coverage_note: '本地 stock_daily 覆盖池，按最新交易日涨跌幅排序',
                    generated_at: '2026-06-08T17:30:00',
                    top_gainers: [{ code: '000001', name: '平安银行', value: 10 }],
                    top_losers: [],
                    top_amplitude: [],
                    top_turnover: [],
                };
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));

        (async () => {
            await App.OverviewRadar.loadRadar();
            assert.match(coverage.innerHTML, /范围 本地日线覆盖池/);
            assert.match(coverage.innerHTML, /排序 本地 stock_daily/);
            assert.match(coverage.innerHTML, /有效 5,525只/);
            assert.match(coverage.innerHTML, /更新 2026-06-05/);
            assert.doesNotMatch(coverage.innerHTML, /东方财富服务端/);
            assert.doesNotMatch(coverage.innerHTML, /全A延迟快照/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_northbound_unavailable_does_not_render_zero_as_real_flow():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '' };
        const coverage = { innerHTML: '' };
        const overviewPanel = { classList: { contains: (name) => name === 'active' } };
        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: () => [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'overview-radar-coverage') return coverage;
                if (id === 'tab-overview') return overviewPanel;
                return null;
            },
        };
        global.App = {
            fetchJSON: async (url) => {
                assert.equal(url, '/api/market/northbound?fast=true');
                return {
                    success: true,
                    source: 'eastmoney_northbound',
                    source_unavailable: true,
                    stale: true,
                    stale_reason: 'fast_path_no_cache',
                    coverage_note: '北向资金快路径未请求外部源，当前无可用缓存',
                    today_net: 0,
                    today_sh_net: 0,
                    today_sz_net: 0,
                    flow: [],
                };
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));
        App.OverviewRadar._setCurrentTabForTest('northbound');

        (async () => {
            await App.OverviewRadar.loadRadar();
            assert.match(container.innerHTML, /北向资金源不可用/);
            assert.match(container.innerHTML, /快路径未请求外部源/);
            assert.match(container.innerHTML, /今日净流入/);
            assert.match(container.innerHTML, />--</);
            assert.doesNotMatch(container.innerHTML, /\\+0\\.00 亿/);
            assert.doesNotMatch(container.innerHTML, /text-up\">\\+0/);
            assert.match(coverage.innerHTML, /北向资金源不可用/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_ignores_stale_tab_response_after_user_switches_tab():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '' };
        const coverage = { innerHTML: '' };
        const overviewPanel = { classList: { contains: (name) => name === 'active' } };
        let resolveRadar;
        let resolveNorthbound;
        const calls = [];

        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: () => [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'overview-radar-coverage') return coverage;
                if (id === 'tab-overview') return overviewPanel;
                return null;
            },
        };
        global.App = {
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('/api/market/radar')) {
                    return new Promise((resolve) => {
                        resolveRadar = () => resolve({
                            success: true,
                            source: 'local_stock_daily',
                            universe: 'local_stock_daily_coverage_pool',
                            local_fallback: true,
                            latest_date: '2026-06-05',
                            total_stocks: 5525,
                            coverage_note: '本地 stock_daily 覆盖池',
                            top_gainers: [{ code: '000001', name: '平安银行', value: 10 }],
                            top_losers: [],
                            top_amplitude: [],
                            top_turnover: [],
                        });
                    });
                }
                if (url.includes('/api/market/northbound')) {
                    return new Promise((resolve) => {
                        resolveNorthbound = () => resolve({
                            success: true,
                            source: 'eastmoney_northbound',
                            source_unavailable: true,
                            stale: true,
                            coverage_note: '北向资金源不可用，当前无可用缓存',
                            today_net: 0,
                            today_sh_net: 0,
                            today_sz_net: 0,
                            flow: [],
                        });
                    });
                }
                throw new Error(`unexpected url: ${url}`);
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));

        (async () => {
            const first = App.OverviewRadar.loadRadar();
            App.OverviewRadar._setCurrentTabForTest('northbound');
            const second = App.OverviewRadar.loadRadar();
            resolveNorthbound();
            await second;
            assert.match(container.innerHTML, /北向资金源不可用/);
            assert.match(coverage.innerHTML, /北向资金源不可用/);

            resolveRadar();
            await first;
            assert.match(container.innerHTML, /北向资金源不可用/);
            assert.doesNotMatch(container.innerHTML, /平安银行/);
            assert.match(coverage.innerHTML, /北向资金源不可用/);
            assert.deepEqual(calls, [
                '/api/market/radar?fast=true',
                '/api/market/northbound?fast=true',
            ]);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_heatmap_renders_local_stock_count_weights():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList(active = false) {
            let isActive = active;
            return {
                contains: (name) => name === 'active' && isActive,
                add: (name) => { if (name === 'active') isActive = true; },
                remove: (name) => { if (name === 'active') isActive = false; },
            };
        }

        const container = { innerHTML: '', offsetWidth: 720 };
        const grid = { innerHTML: '', offsetWidth: 720 };
        const overviewPanel = { classList: makeClassList(true) };
        const clickHandlers = {};
        const tabs = ['heatmap'].map((name) => ({
            dataset: { tab: name },
            classList: makeClassList(true),
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandlers[name] = handler;
            },
        }));

        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: (selector) => selector === '.radar-tab' ? tabs : [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'tab-overview') return overviewPanel;
                if (id === 'heatmap-grid') return grid;
                return null;
            },
        };
        global.App = {
            fetchJSON: async (url, opts = {}) => {
                assert.equal(url, '/api/market/heatmap?fast=true');
                assert.equal(opts.silent, true);
                assert.equal(opts.timeout, 30000);
                return {
                    success: true,
                    local_fallback: true,
                    total: 2,
                    sectors: [
                        { name: '深主板', change_pct: 1.2, total_mv: 0, stock_count: 2200, up_count: 1400, down_count: 700, leader: '平安银行' },
                        { name: '科创板', change_pct: -0.8, total_mv: 0, stock_count: 580, up_count: 180, down_count: 360, leader: '华兴源创' },
                    ],
                };
            },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));
        App.OverviewRadar.init();

        (async () => {
            await clickHandlers.heatmap();
            assert.match(container.innerHTML, /口径 覆盖股数权重/);
            assert.match(container.innerHTML, /展示 2\/2/);
            assert.match(grid.innerHTML, /深主板/);
            assert.match(grid.innerHTML, /科创板/);
            assert.match(grid.innerHTML, /2,200只/);
            assert.doesNotMatch(grid.innerHTML, /0亿/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_settings_renders_even_when_conversation_init_fails():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const settingsRoot = {
            innerHTML: '',
            querySelector: () => null,
            querySelectorAll: () => [],
        };

        global.window = global;
        global.globalThis = global;
        global.location = { origin: 'http://127.0.0.1:8001' };
        global.requestAnimationFrame = (fn) => fn();
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => id === 'openclaw-settings-workbench' ? settingsRoot : null,
            body: { appendChild: () => {} },
        };
        global.OpenClawConversations = {
            init: async () => { throw new Error('conversation unavailable'); },
            render: () => {},
        };
        global.App = {
            _accountState: {
                authenticated: true,
                user: { id: 'u1', username: 'tester', display_name: 'Tester', role: 'user' },
                workspace: { id: 'w1', name: 'Workspace', openclaw_workspace_id: 'ocw_1', settings: {} },
                permissions: {},
            },
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async () => null,
            _setAuthGate: () => {},
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));

        (async () => {
            await OpenClawWorkbench.init('openclaw-settings');
            assert.match(settingsRoot.innerHTML, /openclaw-settings-profile/);
            assert.match(settingsRoot.innerHTML, /API Key \/ 安全/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_restores_active_conversation_before_slow_status_payloads():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const elements = {};
        function makeElement(id) {
            return elements[id] || (elements[id] = {
                id,
                value: '',
                innerHTML: '',
                scrollTop: 0,
                scrollHeight: 0,
                classList: { toggle: () => {}, remove: () => {} },
                querySelector: () => null,
                querySelectorAll: () => [],
            });
        }
        const root = makeElement('openclaw-workbench');
        Object.defineProperty(root, 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = value;
                makeElement('openclaw-messages');
                makeElement('openclaw-input');
                makeElement('openclaw-composer-hint');
                makeElement('openclaw-chat-subtitle');
                makeElement('openclaw-conversation-rail');
            },
        });

        global.window = global;
        global.globalThis = global;
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.openclaw-chat-shell'
                ? { classList: { toggle: () => {} } }
                : null,
            querySelectorAll: () => [],
        };
        global.OpenClawConversations = {
            render: () => {},
            getActiveConversationId: () => 'oc_1',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async (url) => {
                if (String(url).includes('/api/openclaw/conversations/oc_1')) {
                    return {
                        success: true,
                        data: {
                            id: 'oc_1',
                            messages: [
                                { role: 'user', content: '今天 600519 怎么样' },
                                { role: 'assistant', content: '回复：今天 600519 怎么样' },
                            ],
                        },
                    };
                }
                return new Promise(() => {});
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));
        void OpenClawWorkbench.refresh('openclaw');

        setTimeout(() => {
            try {
                assert.match(elements['openclaw-messages'].innerHTML, /600519/);
            } catch (error) {
                console.error(error);
                process.exit(1);
            }
        }, 30);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_refresh_preserves_skill_command_draft_and_hint():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const elements = {};
        function makeElement(id) {
            return elements[id] || (elements[id] = {
                id,
                value: '',
                innerHTML: '',
                scrollTop: 0,
                scrollHeight: 0,
                classList: { toggle: () => {}, remove: () => {} },
                querySelector: () => null,
                querySelectorAll: () => [],
            });
        }
        const root = makeElement('openclaw-workbench');
        makeElement('openclaw-input').value = '/skill record openclaw';
        Object.defineProperty(root, 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = value;
                elements['openclaw-messages'] = makeElement('openclaw-messages');
                elements['openclaw-input'] = {
                    ...makeElement('openclaw-input'),
                    value: '',
                    innerHTML: '',
                    classList: { toggle: () => {}, remove: () => {} },
                    querySelector: () => null,
                    querySelectorAll: () => [],
                };
                makeElement('openclaw-composer-hint');
                makeElement('openclaw-chat-subtitle');
                makeElement('openclaw-conversation-rail');
            },
        });

        global.window = global;
        global.globalThis = global;
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.openclaw-chat-shell'
                ? { classList: { toggle: () => {} } }
                : null,
            querySelectorAll: () => [],
        };
        global.OpenClawConversations = {
            render: () => {},
            getActiveConversationId: () => '',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async () => null,
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));

        (async () => {
            await OpenClawWorkbench.refresh('openclaw');
            assert.equal(elements['openclaw-input'].value, '/skill record openclaw');
            assert.match(elements['openclaw-composer-hint'].innerHTML, /技能命令/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_realtime_websocket_initial_sends_are_disconnect_guarded():
    source = read("dashboard/routers/realtime_quotes.py")

    assert "async def _safe_ws_send_text" in source
    assert "except (WebSocketDisconnect, ClientDisconnected)" in source
    assert "await _safe_ws_send_text(ws, json.dumps({" in source
    assert "if not await _safe_ws_send_text(ws, json.dumps({" in source
