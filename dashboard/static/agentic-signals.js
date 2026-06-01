(function () {
  const state = { signals: [], filter: 'all' };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'
    }[ch]));
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
    const filter = event.target?.dataset?.agenticFilter;
    if (filter) {
      state.filter = filter;
      document.querySelectorAll('[data-agentic-filter]').forEach(btn => btn.classList.toggle('active', btn.dataset.agenticFilter === filter));
      render();
    }
  });

  window.AgenticSignals = { loadSignals, renderSignalCard };
  document.addEventListener('DOMContentLoaded', loadSignals);
})();
