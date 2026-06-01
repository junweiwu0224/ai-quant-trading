(function () {
  const state = { signals: [], filter: 'all', sample: null, backtest: null };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'
    }[ch]));
  }

  function buildDefaultStrategyDSL() {
    return {
      strategy_type: 'ranked_rotation',
      universe: 'qlib_top',
      rank_by: 'qlib_score',
      filters: [{ qlib_score_min: 0.5 }],
      rebalance: 'daily',
      max_holdings: 5,
      stop_loss: 0.05,
      take_profit: 0.12,
      max_holding_days: 10,
    };
  }

  function renderSampleStatus() {
    const el = document.querySelector('[data-agentic-sample-status]');
    if (!el) return;
    if (!state.sample) {
      el.innerHTML = `
        <div class="agentic-sample-pill"><span>样本</span><strong>未就绪</strong></div>
        <div class="agentic-sample-pill"><span>区间</span><strong>-</strong></div>
        <div class="agentic-sample-pill"><span>交易日</span><strong>-</strong></div>
      `;
      return;
    }
    const codes = (state.sample.codes || []).join(' / ');
    el.innerHTML = `
      <div class="agentic-sample-pill"><span>样本</span><strong>${esc(codes || '-')}</strong></div>
      <div class="agentic-sample-pill"><span>区间</span><strong>${esc(state.sample.start_date)} 至 ${esc(state.sample.end_date)}</strong></div>
      <div class="agentic-sample-pill"><span>交易日</span><strong>${esc(state.sample.trading_days)}</strong></div>
    `;
  }

  function renderBacktestResult(message) {
    const el = document.querySelector('[data-agentic-backtest-result]');
    if (!el) return;
    if (message) {
      el.textContent = message;
      return;
    }
    if (!state.backtest) {
      el.textContent = '等待样本回测';
      return;
    }
    const promotion = state.backtest.promotion || {};
    const metrics = state.backtest.metrics || {};
    el.innerHTML = `
      <strong>${promotion.promoted ? '通过晋级门槛' : '未晋级'}</strong>
      <span>${esc(promotion.reason || '-')}</span>
      <span>交易 ${esc(metrics.trades ?? '-')} · 回撤 ${esc(metrics.max_drawdown ?? '-')} · Sharpe ${esc(metrics.sharpe ?? '-')}</span>
    `;
  }

  async function loadBacktestSample() {
    const holder = document.querySelector('[data-agentic-sample-status]');
    if (!holder) return;
    try {
      const resp = await fetch('/api/agentic/backtest-sample?min_days=60&max_codes=5');
      const data = await resp.json();
      if (!resp.ok || !data.success) throw new Error(data.detail || 'sample unavailable');
      state.sample = data.sample;
      renderSampleStatus();
    } catch (error) {
      state.sample = null;
      renderSampleStatus();
      renderBacktestResult('本地样本不可用，请先同步 Qlib/日线覆盖数据');
    }
  }

  async function runSampleBacktest() {
    if (!state.sample) await loadBacktestSample();
    if (!state.sample) return;
    renderBacktestResult('回测运行中...');
    try {
      const resp = await fetch('/api/agentic/strategy/run-backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dsl: buildDefaultStrategyDSL(),
          codes: state.sample.codes,
          start_date: state.sample.start_date,
          end_date: state.sample.end_date,
          initial_cash: 1000000,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.success) throw new Error(data.detail || 'backtest failed');
      state.backtest = data;
      renderBacktestResult();
    } catch (error) {
      state.backtest = null;
      renderBacktestResult('样本回测失败：' + (error.message || error));
    }
  }

  function renderSignalCard(signal) {
    return `
      <article class="agentic-signal-card" data-signal-id="${esc(signal.id)}">
        <header>
          <strong>${esc(signal.code)}</strong>
          <span>${esc(signal.agent_id)}</span>
          <b>${Math.round(Number(signal.confidence || 0) * 100)}%</b>
        </header>
        <div class="agentic-signal-meta">
          <span>${esc(signal.direction)}</span>
          <span>${esc(signal.time_horizon)}</span>
          <span>${esc(signal.status)}</span>
        </div>
        <p>${esc((signal.entry_reasons || [])[0] || '')}</p>
        <div class="agentic-signal-actions">
          <button data-agentic-action="watch" data-signal-id="${esc(signal.id)}">观察</button>
          <button data-agentic-action="backtest" data-signal-id="${esc(signal.id)}">回测</button>
          <button data-agentic-action="promote-paper" data-signal-id="${esc(signal.id)}">加入模拟盘</button>
        </div>
      </article>
    `;
  }

  function render() {
    const list = document.querySelector('[data-agentic-signal-list]');
    if (!list) return;
    const items = state.filter === 'all'
      ? state.signals
      : state.signals.filter(item => item.status === state.filter);
    list.innerHTML = items.length
      ? items.map(renderSignalCard).join('')
      : '<div class="empty-state">暂无 Agent 信号</div>';
  }

  async function loadSignals() {
    const list = document.querySelector('[data-agentic-signal-list]');
    if (!list) return;
    list.innerHTML = '<div class="empty-state">加载中...</div>';
    try {
      const resp = await fetch('/api/agentic/signals');
      const data = await resp.json();
      state.signals = data.signals || [];
    } catch (error) {
      state.signals = [];
      list.innerHTML = '<div class="empty-state">信号加载失败</div>';
      return;
    }
    render();
  }

  document.addEventListener('click', event => {
    const action = event.target?.dataset?.agenticAction;
    if (action === 'refresh-signals') loadSignals();
    if (action === 'run-sample-backtest') runSampleBacktest();
    const filter = event.target?.dataset?.agenticFilter;
    if (filter) {
      state.filter = filter;
      document.querySelectorAll('[data-agentic-filter]').forEach(btn => btn.classList.toggle('active', btn.dataset.agenticFilter === filter));
      render();
    }
  });

  window.AgenticSignals = { loadSignals, renderSignalCard, loadBacktestSample, runSampleBacktest, buildDefaultStrategyDSL };
  document.addEventListener('DOMContentLoaded', () => {
    loadBacktestSample();
    loadSignals();
  });
})();
