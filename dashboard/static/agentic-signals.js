(function () {
  const AGENTIC_HISTORY_LIMIT = 3;
  const state = { signals: [], filter: 'all', sample: null, backtest: null, candidateBatch: null, paperCandidates: [], paperExecutions: [], orderDrafts: [] };

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

  function authMessage(error) {
    return error?.status === 401 ? '请先登录后查看 Agent 策略实验台' : '';
  }

  async function agenticFetchJson(url, options) {
    const resp = await fetch(url, options);
    let data = {};
    try {
      data = await resp.json();
    } catch (error) {
      data = {};
    }
    if (!resp.ok || !data.success) {
      const error = new Error(data.detail || `request failed: ${resp.status}`);
      error.status = resp.status;
      throw error;
    }
    return data;
  }

  function paperStatusLabel(status) {
    return ({
      paper_candidate: '等待你确认',
      paper_active: '已进入模拟盘候选',
      paper_intent_pending: '等待风控确认',
      paper_intent_confirmed: '可写入模拟盘订单',
      paper_orders_submitted: '已写入订单',
      draft_pending: '订单草案',
      submitted: '已提交',
      rejected: '已拒绝',
    })[status] || status || '-';
  }

  function paperStatusTone(status) {
    if (status === 'paper_intent_confirmed') return 'is-ready';
    if (status === 'paper_orders_submitted' || status === 'submitted') return 'is-done';
    if (status === 'rejected') return 'is-danger';
    return 'is-pending';
  }

  function formatStockLabel(code, source) {
    const raw = String(code || '').trim();
    const names = { ...(state.sample?.stock_names || {}), ...(source?.stock_names || source?.names || {}) };
    const name = names[raw] || names[raw.replace(/^(sh|sz)/i, '')] || '';
    return name && name !== raw ? `${name}（${raw}）` : raw;
  }

  function formatStockList(codes, source) {
    const list = Array.isArray(codes) ? codes : [];
    return list.length ? list.map(code => formatStockLabel(code, source)).join(' / ') : '-';
  }

  function formatRange(source) {
    const start = source?.start_date || '-';
    const end = source?.end_date || '-';
    return `${start} 至 ${end}`;
  }

  function promotionReason(reason) {
    return ({
      'insufficient trades': '交易次数不足，暂不建议进入模拟盘',
      'sharpe below threshold': '收益稳定性不够，暂不建议进入模拟盘',
      'drawdown above threshold': '回撤偏大，暂不建议进入模拟盘',
      'passed promotion gate': '通过晋级门槛，可以加入模拟盘候选',
    })[reason] || reason || '-';
  }

  function buildCandidateDiagnosis(results) {
    const items = Array.isArray(results) ? results : [];
    const promoted = items.filter(item => item.promotion?.promoted).length;
    const zeroTrade = items.filter(item => Number(item.metrics?.trades || 0) === 0).length;
    const insufficientTrades = items.filter(item => item.promotion?.reason === 'insufficient trades').length;
    const sharpeFailed = items.filter(item => item.promotion?.reason === 'sharpe below threshold').length;
    const drawdownFailed = items.filter(item => item.promotion?.reason === 'max drawdown exceeded').length;
    const notes = [];
    if (promoted) notes.push(`${promoted} 个策略可以进入模拟盘候选`);
    if (zeroTrade) notes.push(`${zeroTrade} 个策略产生交易为 0，可能是预测覆盖不足，也可能是该策略条件在样本内没有触发`);
    if (insufficientTrades && insufficientTrades > zeroTrade) notes.push(`${insufficientTrades - zeroTrade} 个策略交易次数不足，样本太少时不建议实跑`);
    if (sharpeFailed) notes.push(`${sharpeFailed} 个策略 Sharpe 没达标，说明收益波动后不够稳`);
    if (drawdownFailed) notes.push(`${drawdownFailed} 个策略回撤超过门槛`);
    if (!notes.length) notes.push('本轮候选没有明显错误，但尚未达到模拟盘晋级门槛');
    const action = promoted
      ? '下一步：选择晋级策略加入模拟盘候选。'
      : zeroTrade
        ? '下一步：先确认 Qlib 历史预测已覆盖回测期；若已覆盖，就调整没有触发交易的策略参数。'
        : '下一步：降低策略风险或调整候选参数后重新回测。';
    return { promoted, zeroTrade, insufficientTrades, sharpeFailed, drawdownFailed, notes, action };
  }

  function currentActionItem() {
    const pendingCandidate = state.paperCandidates.find(item => item.requires_confirmation);
    if (pendingCandidate) return { type: 'candidate', item: pendingCandidate };
    const pendingExecution = state.paperExecutions.find(item => item.status === 'paper_intent_pending');
    if (pendingExecution) return { type: 'execution', item: pendingExecution };
    const readyExecution = state.paperExecutions.find(item => item.status === 'paper_intent_confirmed');
    if (readyExecution) return { type: 'execution', item: readyExecution };
    const activeCandidate = state.paperCandidates.find(item => item.status === 'paper_active');
    if (activeCandidate) return { type: 'candidate', item: activeCandidate };
    const submittedExecution = state.paperExecutions.find(item => item.status === 'paper_orders_submitted');
    if (submittedExecution) return { type: 'execution', item: submittedExecution };
    return null;
  }

  function historyItems(current) {
    const currentId = current?.item?.id;
    return {
      candidates: state.paperCandidates.filter(item => item.id !== currentId).slice(0, AGENTIC_HISTORY_LIMIT),
      executions: state.paperExecutions.filter(item => item.id !== currentId).slice(0, AGENTIC_HISTORY_LIMIT),
      drafts: state.orderDrafts.slice(0, AGENTIC_HISTORY_LIMIT),
    };
  }

  function renderCurrentAgenticAction() {
    const el = document.querySelector('[data-agentic-current-action]');
    if (!el) return;
    const current = currentActionItem();
    if (!current) {
      el.innerHTML = '<div class="empty-state">当前没有待处理策略。先点击上方“重新回测候选”。</div>';
      return;
    }
    const item = current.item;
    if (current.type === 'candidate') {
      const isPending = item.requires_confirmation;
      el.innerHTML = `
        <article class="agentic-current-card ${isPending ? 'is-actionable' : ''}">
          <span class="agentic-status-pill ${paperStatusTone(item.status)}">${esc(paperStatusLabel(item.status))}</span>
          <h3>${esc(item.name || item.candidate_id)}</h3>
          <p>${isPending ? '新候选已生成，先确认是否进入模拟盘。确认后仍不会直接下单。' : '策略已进入模拟盘候选，下一步先生成交易意图。'}</p>
          <div class="agentic-current-meta">
            <span>股票池 <b>${esc(formatStockList(item.sample?.codes, item.sample))}</b></span>
            <span>回测区间 <b>${esc(formatRange(item.sample))}</b></span>
            <span>Sharpe <b>${esc(item.metrics?.sharpe ?? '-')}</b></span>
          </div>
          ${isPending ? `<button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-strategy" data-paper-candidate-id="${esc(item.id)}">确认进入模拟盘</button>` : `<button class="btn btn-primary btn-sm" data-agentic-action="run-paper-strategy" data-paper-candidate-id="${esc(item.id)}">生成交易意图</button>`}
        </article>
      `;
      return;
    }
    const canSubmit = item.status === 'paper_intent_confirmed';
    const pendingRisk = item.status === 'paper_intent_pending';
    el.innerHTML = `
      <article class="agentic-current-card ${paperStatusTone(item.status)}">
        <span class="agentic-status-pill ${paperStatusTone(item.status)}">${esc(paperStatusLabel(item.status))}</span>
        <h3>${esc(item.name || item.candidate_id)}</h3>
        <p>${esc(item.status === 'paper_orders_submitted' ? '这条策略已经写入模拟盘订单，可以去模拟盘查看。' : canSubmit ? '风控已经通过，现在可以写入模拟盘订单。' : pendingRisk ? '交易意图已生成，先做组合风控确认。' : (item.reason || ''))}</p>
        <div class="agentic-current-meta">
          <span>股票 <b>${esc(formatStockList(item.codes, item.sample))}</b></span>
          <span>状态 <b>${esc(paperStatusLabel(item.status))}</b></span>
        </div>
        ${pendingRisk ? `<button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-execution" data-paper-execution-id="${esc(item.id)}">确认风控</button>` : ''}
        ${canSubmit ? `<button class="btn btn-primary btn-sm" data-agentic-action="submit-paper-orders" data-paper-execution-id="${esc(item.id)}">写入模拟盘订单</button>` : ''}
      </article>
    `;
  }

  function renderAgenticHistory() {
    const el = document.querySelector('[data-agentic-history]');
    if (!el) return;
    const current = currentActionItem();
    const history = historyItems(current);
    el.innerHTML = `
      <div class="agentic-history-group"><h4>候选策略</h4><div data-agentic-paper-candidates></div></div>
      <div class="agentic-history-group"><h4>交易意图</h4><div data-agentic-paper-executions></div></div>
      <div class="agentic-history-group"><h4>订单草案</h4><div data-agentic-order-drafts></div></div>
    `;
    renderPaperStrategyCandidates(history.candidates);
    renderPaperStrategyExecutions(history.executions);
    renderAgenticOrderDrafts(history.drafts);
  }

  function renderAgenticWorkbench() {
    renderCurrentAgenticAction();
    renderNextAgenticAction();
    renderAgenticHistory();
  }

  function renderNextAgenticAction() {
    const el = document.querySelector('[data-agentic-next-action]');
    if (!el) return;
    const current = currentActionItem();
    const item = current?.item;
    if (current?.type === 'candidate' && item.requires_confirmation) {
      el.innerHTML = `<strong>下一步</strong><span>新候选已生成，先确认是否进入模拟盘。</span><button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-strategy" data-paper-candidate-id="${esc(item.id)}">确认策略</button>`;
    } else if (current?.type === 'candidate') {
      el.innerHTML = `<strong>下一步</strong><span>候选策略已确认，可以生成交易意图，不会直接下单。</span><button class="btn btn-primary btn-sm" data-agentic-action="run-paper-strategy" data-paper-candidate-id="${esc(item.id)}">生成交易意图</button>`;
    } else if (item?.status === 'paper_intent_pending') {
      el.innerHTML = `<strong>下一步</strong><span>交易意图已生成，先做组合风控确认。</span><button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-execution" data-paper-execution-id="${esc(item.id)}">确认风控</button>`;
    } else if (item?.status === 'paper_intent_confirmed') {
      el.innerHTML = `<strong>下一步</strong><span>策略已通过风控，可以写入模拟盘订单。</span><button class="btn btn-primary btn-sm" data-agentic-action="submit-paper-orders" data-paper-execution-id="${esc(item.id)}">写入模拟盘订单</button>`;
    } else if (item?.status === 'paper_orders_submitted') {
      el.innerHTML = `<strong>当前状态</strong><span>最近一条策略已经写入模拟盘订单，可到“模拟盘”查看订单。</span>`;
    } else {
      el.innerHTML = `<strong>下一步</strong><span>先点击“重新回测候选”，系统会告诉你哪些策略能进入模拟盘。</span><button class="btn btn-primary btn-sm" data-agentic-action="run-candidate-backtests">重新回测候选</button>`;
    }
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
    const codes = formatStockList(state.sample.codes, state.sample);
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

  function renderCandidateBacktestResults(message) {
    const list = document.querySelector('[data-agentic-candidate-results]');
    const summary = document.querySelector('[data-agentic-backtest-result]');
    if (!list) return;
    if (message) {
      list.innerHTML = '';
      if (summary) summary.textContent = message;
      return;
    }
    const results = state.candidateBatch?.results || [];
    if (!results.length) {
      list.innerHTML = '<div class="empty-state">暂无候选回测结果</div>';
      if (summary) summary.textContent = '等待候选回测';
      return;
    }
    const diagnosis = buildCandidateDiagnosis(results);
    if (summary) {
      summary.innerHTML = `
        <strong>${diagnosis.promoted ? `候选 ${results.length} 个，其中 ${diagnosis.promoted} 个可以进入模拟盘候选` : `候选 ${results.length} 个，暂时不要进模拟盘`}</strong>
        <div class="agentic-diagnosis-list">
          ${diagnosis.notes.map(note => `<span>${esc(note)}</span>`).join('')}
        </div>
        <em>${esc(diagnosis.action)}</em>
      `;
    }
    list.innerHTML = results.map((item, index) => {
      const candidate = item.candidate || {};
      const metrics = item.metrics || {};
      const promotion = item.promotion || {};
      return `
        <article class="agentic-candidate-row ${promotion.promoted ? 'is-promoted' : ''}">
          <div class="agentic-candidate-rank">#${index + 1}</div>
          <div>
            <strong>${esc(candidate.name || candidate.id || '-')}</strong>
            <p>${esc(candidate.thesis || '')}</p>
            <span>${promotion.promoted ? '可进入模拟盘候选' : '暂不进入模拟盘'} · ${esc(promotionReason(promotion.reason))}</span>
            ${promotion.promoted ? `<button class="btn btn-primary btn-sm" data-agentic-action="queue-paper-strategy" data-candidate-index="${index}">加入模拟盘候选</button>` : ''}
          </div>
          <div class="agentic-candidate-metrics">
            <span>交易 <b>${esc(metrics.trades ?? '-')}</b></span>
            <span>回撤 <b>${esc(metrics.max_drawdown ?? '-')}</b></span>
            <span>Sharpe <b>${esc(metrics.sharpe ?? '-')}</b></span>
          </div>
        </article>
      `;
    }).join('');
  }


  async function loadBacktestSample() {
    const holder = document.querySelector('[data-agentic-sample-status]');
    if (!holder) return;
    try {
      const data = await agenticFetchJson('/api/agentic/backtest-sample?min_days=60&max_codes=5');
      state.sample = data.sample;
      renderSampleStatus();
      renderAgenticWorkbench();
    } catch (error) {
      state.sample = null;
      renderSampleStatus();
      renderBacktestResult(authMessage(error) || '本地样本不可用，请先同步 Qlib/日线覆盖数据');
      renderAgenticWorkbench();
    }
  }

  async function runSampleBacktest() {
    if (!state.sample) await loadBacktestSample();
    if (!state.sample) return;
    renderBacktestResult('回测运行中...');
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/run-backtest', {
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
      state.backtest = data;
      renderBacktestResult();
    } catch (error) {
      state.backtest = null;
      renderBacktestResult(authMessage(error) || ('样本回测失败：' + (error.message || error)));
    }
  }

  async function runCandidateBacktests() {
    renderCandidateBacktestResults('候选策略回测运行中...');
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/run-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          context: { universe: 'qlib_top', risk_mode: 'balanced', max_holdings: 5 },
          limit: 4,
          min_days: 60,
          max_codes: 5,
          initial_cash: 1000000,
        }),
      });
      state.candidateBatch = data;
      state.sample = data.sample || state.sample;
      renderSampleStatus();
      renderCandidateBacktestResults();
      renderAgenticWorkbench();
    } catch (error) {
      state.candidateBatch = null;
      renderCandidateBacktestResults(authMessage(error) || ('候选回测失败：' + (error.message || error)));
      renderAgenticWorkbench();
    }
  }

  async function queuePaperStrategyCandidate(index) {
    const result = state.candidateBatch?.results?.[Number(index)];
    if (!result || !result.promotion?.promoted) return;
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/paper-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sample: state.candidateBatch.sample, result }),
      });
      state.paperCandidates = [data.candidate, ...state.paperCandidates.filter(item => item.id !== data.candidate.id)];
      renderAgenticWorkbench();
      renderCandidateBacktestResults(`已加入模拟盘候选：${data.candidate?.name || result.candidate?.name || ''}`);
    } catch (error) {
      renderCandidateBacktestResults(authMessage(error) || ('加入模拟盘候选失败：' + (error.message || error)));
    }
  }


  function renderPaperStrategyCandidates(items) {
    const list = document.querySelector('[data-agentic-paper-candidates]');
    if (!list) return;
    const rows = Array.isArray(items) ? items : state.paperCandidates;
    if (!rows.length) {
      list.innerHTML = '<div class="empty-state">暂无需要确认的策略。先在上方跑候选回测。</div>';
      return;
    }
    list.innerHTML = rows.slice(0, AGENTIC_HISTORY_LIMIT).map(item => `
      <article class="agentic-paper-candidate-row ${item.requires_confirmation ? 'is-actionable' : ''}" data-paper-candidate-id="${esc(item.id)}">
        <div>
          <span class="agentic-status-pill ${paperStatusTone(item.status)}">${esc(paperStatusLabel(item.status))}</span>
          <strong>${esc(item.name || item.candidate_id)}</strong>
          <p>${esc(formatStockList(item.sample?.codes, item.sample))} · ${esc(formatRange(item.sample))}</p>
          <span>回测 Sharpe ${esc(item.metrics?.sharpe ?? '-')}</span>
        </div>
        <div class="agentic-paper-candidate-actions">
          ${item.requires_confirmation ? `<button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-strategy" data-paper-candidate-id="${esc(item.id)}">确认进入模拟盘</button>` : `<button class="btn btn-secondary btn-sm" data-agentic-action="run-paper-strategy" data-paper-candidate-id="${esc(item.id)}">生成交易意图</button>`}
        </div>
      </article>
    `).join('');
  }

  async function loadPaperStrategyCandidates() {
    const list = document.querySelector('[data-agentic-paper-candidates]');
    if (!list) return;
    list.innerHTML = '<div class="empty-state">加载候选中...</div>';
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/paper-candidates?limit=20');
      state.paperCandidates = data.candidates || [];
      renderAgenticWorkbench();
    } catch (error) {
      state.paperCandidates = [];
      list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || '候选加载失败') + '</div>';
      renderAgenticWorkbench();
    }
  }

  async function confirmPaperStrategyCandidate(candidateId) {
    if (!candidateId) return;
    try {
      const data = await agenticFetchJson(`/api/agentic/strategy/paper-candidates/${encodeURIComponent(candidateId)}/confirm`, { method: 'POST' });
      state.paperCandidates = state.paperCandidates.map(item => item.id === candidateId ? data.candidate : item);
      renderAgenticWorkbench();
    } catch (error) {
      const list = document.querySelector('[data-agentic-paper-candidates]');
      if (list) list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || ('确认失败：' + (error.message || error))) + '</div>';
    }
  }

  function renderPaperStrategyExecutions(items) {
    const list = document.querySelector('[data-agentic-paper-executions]');
    if (!list) return;
    const rows = Array.isArray(items) ? items : state.paperExecutions;
    if (!rows.length) {
      list.innerHTML = '<div class="empty-state">还没有交易意图。先确认候选策略，再生成意图。</div>';
      return;
    }
    list.innerHTML = rows.slice(0, AGENTIC_HISTORY_LIMIT).map(item => `
      <article class="agentic-paper-execution-row ${paperStatusTone(item.status)}">
        <span class="agentic-status-pill ${paperStatusTone(item.status)}">${esc(paperStatusLabel(item.status))}</span>
        <strong>${esc(item.name || item.candidate_id)}</strong>
        <span>${esc(formatStockList(item.codes, item.sample))}</span>
        <p>${esc(item.status === 'paper_orders_submitted' ? '已生成模拟盘订单，可到模拟盘页查看。' : item.status === 'paper_intent_confirmed' ? '已通过风控，可以写入模拟盘订单。' : item.status === 'paper_intent_pending' ? '等待组合风控确认，不会直接下单。' : (item.reason || ''))}</p>
        ${item.requires_confirmation ? `<button class="btn btn-primary btn-sm" data-agentic-action="confirm-paper-execution" data-paper-execution-id="${esc(item.id)}">确认意图</button>` : ''}
        ${item.status === 'paper_intent_confirmed' ? `<button class="btn btn-secondary btn-sm" data-agentic-action="create-order-drafts" data-paper-execution-id="${esc(item.id)}">生成订单草案</button>` : ''}
        ${item.status === 'paper_intent_confirmed' ? `<button class="btn btn-primary btn-sm" data-agentic-action="submit-paper-orders" data-paper-execution-id="${esc(item.id)}">写入模拟盘订单</button>` : ''}
        ${item.status === 'paper_orders_submitted' ? `<span class="badge success">已完成</span>` : ''}
      </article>
    `).join('');
  }

  async function loadPaperStrategyExecutions() {
    const list = document.querySelector('[data-agentic-paper-executions]');
    if (!list) return;
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/paper-executions?limit=20');
      state.paperExecutions = data.executions || [];
      renderAgenticWorkbench();
    } catch (error) {
      state.paperExecutions = [];
      list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || '执行记录加载失败') + '</div>';
      renderAgenticWorkbench();
    }
  }

  async function runPaperStrategyCandidate(candidateId) {
    if (!candidateId) return;
    try {
      const data = await agenticFetchJson(`/api/agentic/strategy/paper-candidates/${encodeURIComponent(candidateId)}/run`, { method: 'POST' });
      state.paperExecutions = [data.execution, ...state.paperExecutions.filter(item => item.id !== data.execution.id)];
      renderAgenticWorkbench();
    } catch (error) {
      const list = document.querySelector('[data-agentic-paper-executions]');
      if (list) list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || ('生成意图失败：' + (error.message || error))) + '</div>';
    }
  }

  async function confirmPaperStrategyExecution(executionId) {
    if (!executionId) return;
    try {
      const data = await agenticFetchJson(`/api/agentic/strategy/paper-executions/${encodeURIComponent(executionId)}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          portfolio: { total_equity: 1000000, positions: {} },
          risk_context: {
            cash_pct: 0.1,
            max_strategy_cash_pct: 0.2,
            max_position_pct: 0.1,
            max_holdings: 10,
            blacklist: [],
            max_industry_pct: 0.35,
          },
        }),
      });
      state.paperExecutions = state.paperExecutions.map(item => item.id === executionId ? data.execution : item);
      renderAgenticWorkbench();
    } catch (error) {
      const list = document.querySelector('[data-agentic-paper-executions]');
      if (list) list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || ('确认意图失败：' + (error.message || error))) + '</div>';
    }
  }

  function renderAgenticOrderDrafts(items) {
    const list = document.querySelector('[data-agentic-order-drafts]');
    if (!list) return;
    const rows = Array.isArray(items) ? items : state.orderDrafts;
    if (!rows.length) {
      list.innerHTML = '<div class="empty-state">暂无订单草案。草案只是预览，真正写入请点“写入模拟盘订单”。</div>';
      return;
    }
    list.innerHTML = rows.slice(0, AGENTIC_HISTORY_LIMIT).map(item => `
      <article class="agentic-order-draft-row">
        <span class="agentic-status-pill ${paperStatusTone(item.status)}">${esc(paperStatusLabel(item.status))}</span>
        <strong>${esc(item.code)} · 买入 · 市价</strong>
        <span>${esc(item.volume)} 股 · ${esc(item.strategy_name)}</span>
      </article>
    `).join('');
  }

  async function loadAgenticOrderDrafts() {
    const list = document.querySelector('[data-agentic-order-drafts]');
    if (!list) return;
    try {
      const data = await agenticFetchJson('/api/agentic/strategy/order-drafts?limit=20');
      state.orderDrafts = data.drafts || [];
      renderAgenticWorkbench();
    } catch (error) {
      state.orderDrafts = [];
      list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || '订单草案加载失败') + '</div>';
      renderAgenticWorkbench();
    }
  }

  async function createAgenticOrderDrafts(executionId) {
    if (!executionId) return;
    try {
      const data = await agenticFetchJson(`/api/agentic/strategy/paper-executions/${encodeURIComponent(executionId)}/order-drafts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume_per_code: 100 }),
      });
      state.orderDrafts = [...(data.drafts || []), ...state.orderDrafts];
      renderAgenticWorkbench();
    } catch (error) {
      const list = document.querySelector('[data-agentic-order-drafts]');
      if (list) list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || ('生成订单草案失败：' + (error.message || error))) + '</div>';
    }
  }

  async function submitAgenticPaperOrders(executionId) {
    if (!executionId) return;
    const list = document.querySelector('[data-agentic-paper-executions]');
    try {
      const data = await agenticFetchJson(`/api/agentic/strategy/paper-executions/${encodeURIComponent(executionId)}/paper-orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume_per_code: 100 }),
      });
      if (list) {
        list.insertAdjacentHTML('afterbegin', `<div class="empty-state">已写入模拟盘订单 ${esc((data.orders || []).length)} 笔</div>`);
      }
      state.paperExecutions = state.paperExecutions.map(item => item.id === executionId ? { ...item, status: 'paper_orders_submitted', reason: `submitted ${(data.orders || []).length} paper orders from confirmed agentic intent` } : item);
      renderAgenticWorkbench();
    } catch (error) {
      if (list) list.innerHTML = '<div class="empty-state">' + esc(authMessage(error) || ('写入模拟盘订单失败：' + (error.message || error))) + '</div>';
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
      : '<div class="agentic-signal-empty"><strong>暂无 Agent 信号</strong><span>这里会汇总 Qlib、热点、问财、OpenClaw 和策略 Agent 的结构化信号；当前没有新信号，不影响上方策略实验台继续推进。</span></div>';
  }

  async function loadSignals() {
    const list = document.querySelector('[data-agentic-signal-list]');
    if (!list) return;
    list.innerHTML = '<div class="empty-state">加载中...</div>';
    try {
      const data = await agenticFetchJson('/api/agentic/signals');
      state.signals = data.signals || [];
    } catch (error) {
      state.signals = [];
      list.innerHTML = '<div class="agentic-signal-empty"><strong>' + esc(authMessage(error) || '信号加载失败') + '</strong><span>信号池是独立看板，不影响上方策略候选和模拟盘推进。</span></div>';
      return;
    }
    render();
  }

  document.addEventListener('click', event => {
    const action = event.target?.dataset?.agenticAction;
    if (action === 'refresh-signals') loadSignals();
    if (action === 'run-sample-backtest') runSampleBacktest();
    if (action === 'run-candidate-backtests') runCandidateBacktests();
    if (action === 'queue-paper-strategy') queuePaperStrategyCandidate(event.target?.dataset?.candidateIndex);
    if (action === 'refresh-paper-candidates') loadPaperStrategyCandidates();
    if (action === 'confirm-paper-strategy') confirmPaperStrategyCandidate(event.target?.dataset?.paperCandidateId);
    if (action === 'run-paper-strategy') runPaperStrategyCandidate(event.target?.dataset?.paperCandidateId);
    if (action === 'confirm-paper-execution') confirmPaperStrategyExecution(event.target?.dataset?.paperExecutionId);
    if (action === 'create-order-drafts') createAgenticOrderDrafts(event.target?.dataset?.paperExecutionId);
    if (action === 'submit-paper-orders') submitAgenticPaperOrders(event.target?.dataset?.paperExecutionId);
    const filter = event.target?.dataset?.agenticFilter;
    if (filter) {
      state.filter = filter;
      document.querySelectorAll('[data-agentic-filter]').forEach(btn => btn.classList.toggle('active', btn.dataset.agenticFilter === filter));
      render();
    }
  });

  window.AgenticSignals = { loadSignals, renderSignalCard, loadBacktestSample, runSampleBacktest, runCandidateBacktests, queuePaperStrategyCandidate, renderCandidateBacktestResults, loadPaperStrategyCandidates, confirmPaperStrategyCandidate, loadPaperStrategyExecutions, runPaperStrategyCandidate, confirmPaperStrategyExecution, loadAgenticOrderDrafts, createAgenticOrderDrafts, submitAgenticPaperOrders, buildDefaultStrategyDSL };
  document.addEventListener('DOMContentLoaded', () => {
    loadBacktestSample();
    loadSignals();
    loadPaperStrategyCandidates();
    loadPaperStrategyExecutions();
    loadAgenticOrderDrafts();
  });
})();
