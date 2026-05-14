/**
 * 条件选股模块
 * 条件构建器 + 预设策略 + 结果表格 + CSV 导出
 */
(function () {
    'use strict';

    let _fields = [];
    let _presets = [];
    let _lastResult = null;
    let _lastPoolCodes = [];

    function createActionTraceId(prefix) {
        if (window.LocalMCP && typeof window.LocalMCP.createTraceId === 'function') {
            return window.LocalMCP.createTraceId(prefix);
        }
        const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : 'screener';
        return `${safePrefix}-${Date.now()}`;
    }

    // ── 初始化 ──

    async function init() {
        await Promise.all([loadFields(), loadPresets()]);
        bindEvents();
        bindActionDelegation();
        addConditionRow();
        initAI();
        // 读取 LLM 降级存储的条件
        try {
            const cached = localStorage.getItem('llm_filters');
            if (cached) {
                const filters = JSON.parse(cached);
                if (Array.isArray(filters) && filters.length > 0) {
                    loadFilters(filters);
                    localStorage.removeItem('llm_filters');
                }
            }
        } catch {}
    }

    async function loadFields() {
        try {
            const data = await App.fetchJSON('/api/screener/fields');
            _fields = data.fields || [];
        } catch (e) {
            console.error('加载字段失败:', e);
        }
    }

    async function loadPresets() {
        try {
            const data = await App.fetchJSON('/api/screener/presets');
            _presets = data.presets || [];
            renderPresets();
        } catch (e) {
            console.error('加载预设失败:', e);
        }
    }

    function bindEvents() {
        document.getElementById('screener-add-btn')?.addEventListener('click', addConditionRow);
        document.getElementById('screener-run-btn')?.addEventListener('click', runCustom);
        document.getElementById('screener-export-btn')?.addEventListener('click', exportCSV);
        document.getElementById('screener-add-watchlist')?.addEventListener('click', addAllToWatchlist);
    }

    function bindActionDelegation() {
        document.addEventListener('click', (e) => {
            const button = e.target.closest('[data-screener-action]');
            if (!button) {
                return;
            }

            const action = button.dataset.screenerAction;
            if (action === 'add-watchlist') {
                e.preventDefault();
                const code = typeof button.dataset.code === 'string' ? button.dataset.code.trim() : '';
                if (code) {
                    addToWatchlist(code);
                }
                return;
            }

            if (action === 'export-csv') {
                e.preventDefault();
                exportCSV();
                return;
            }

            if (action === 'add-all-watchlist') {
                e.preventDefault();
                addAllToWatchlist();
                return;
            }

            if (action === 'add-all-ai-watchlist') {
                e.preventDefault();
                addAllAIToWatchlist();
                return;
            }

            if (action === 'add-all-pool-watchlist') {
                e.preventDefault();
                if (_lastPoolCodes.length > 0) {
                    App.addAllToWatchlist(_lastPoolCodes.slice());
                }
            }
        });
    }

    // ── 预设策略 ──

    function renderPresets() {
        const container = document.getElementById('screener-presets');
        if (!container) return;
        container.innerHTML = _presets.map(p =>
            `<button class="btn btn-sm screener-preset-btn" data-name="${App.escapeHTML(p.name)}" title="${App.escapeHTML(p.desc)}">${App.escapeHTML(p.name)}</button>`
        ).join('');

        container.addEventListener('click', (e) => {
            const btn = e.target.closest('.screener-preset-btn');
            if (!btn) return;
            runPreset(btn.dataset.name);
        });
    }

    async function runPreset(name) {
        const resultDiv = document.getElementById('screener-result');
        if (resultDiv) resultDiv.innerHTML = Utils.skeletonTable(8, 6);

        try {
            const data = await App.fetchJSON('/api/screener/run-preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preset_name: name, page_size: 10000 }),
            });
            if (!data.success) {
                App.toast(data.error || '筛选失败', 'error');
                return;
            }
            _lastResult = data;
            renderResult(data, name);
            App.toast(`「${name}」找到 ${data.total} 只股票`, 'success');
        } catch (e) {
            App.toast('预设选股失败: ' + e.message, 'error');
        }
    }

    // ── 从外部加载条件（LLM 生成 / 条件单导入） ──

    function loadFilters(filters) {
        if (!Array.isArray(filters) || filters.length === 0) return;

        // 切换到条件选股子 tab
        const manualTab = document.querySelector('.screener-tab[data-tab="manual"]');
        if (manualTab) manualTab.click();

        // 清空现有条件行
        const container = document.getElementById('screener-conditions');
        if (container) container.innerHTML = '';

        // 填入新条件
        for (const f of filters) {
            addConditionRow();
            const rows = document.querySelectorAll('#screener-conditions .screener-cond-row');
            const row = rows[rows.length - 1];
            if (!row) continue;

            const fieldSel = row.querySelector('.screener-field');
            const opSel = row.querySelector('.screener-op');
            const valInput = row.querySelector('.screener-value');
            const valInput2 = row.querySelector('.screener-value2');

            if (fieldSel && f.field) {
                fieldSel.value = f.field;
                // 如果字段不存在于选项中，添加一个临时选项
                if (!fieldSel.value) {
                    const opt = document.createElement('option');
                    opt.value = f.field;
                    opt.textContent = f.field;
                    fieldSel.appendChild(opt);
                    fieldSel.value = f.field;
                }
            }

            if (opSel && f.op) {
                opSel.value = f.op;
                // 触发 between 时显示第二输入框
                if (f.op === 'between' && valInput2) {
                    valInput2.style.display = '';
                    valInput.placeholder = '最小值';
                }
            }

            if (valInput && f.value != null) {
                if (Array.isArray(f.value)) {
                    valInput.value = f.value[0] ?? '';
                    if (valInput2 && f.value[1] != null) valInput2.value = f.value[1];
                } else {
                    valInput.value = f.value;
                }
            }
        }

        App.toast(`已载入 ${filters.length} 个筛选条件`, 'success');
    }

    // ── 自定义条件 ──

    function _getFieldUnit(field) {
        const f = _fields.find(x => x.field === field);
        if (!f) return '数值';
        const label = f.label || '';
        const m = label.match(/\(([^)]+)\)/);
        return m ? `数值(${m[1]})` : '数值';
    }

    function addConditionRow() {
        const container = document.getElementById('screener-conditions');
        if (!container) return;

        const row = document.createElement('div');
        row.className = 'screener-cond-row';

        const fieldSelect = document.createElement('select');
        fieldSelect.className = 'screener-field';
        fieldSelect.innerHTML = '<option value="">选择字段</option>' +
            _fields.filter(f => f.type === 'number').map(f =>
                `<option value="${f.field}">${f.label}</option>`
            ).join('');

        const opSelect = document.createElement('select');
        opSelect.className = 'screener-op';
        opSelect.innerHTML = `
            <option value="gt">大于</option>
            <option value="lt">小于</option>
            <option value="gte">大于等于</option>
            <option value="lte">小于等于</option>
            <option value="between">区间</option>
        `;

        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'screener-value';
        valueInput.placeholder = '数值';

        // 字段变化时更新 placeholder 单位
        fieldSelect.addEventListener('change', () => {
            const unit = _getFieldUnit(fieldSelect.value);
            valueInput.placeholder = unit;
            valueInput2.placeholder = opSelect.value === 'between' ? `最大值` : unit;
        });

        const valueInput2 = document.createElement('input');
        valueInput2.type = 'text';
        valueInput2.className = 'screener-value2';
        valueInput2.placeholder = '最大值';
        valueInput2.style.display = 'none';

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-sm screener-remove';
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', () => row.remove());

        opSelect.addEventListener('change', () => {
            valueInput2.style.display = opSelect.value === 'between' ? '' : 'none';
            valueInput.placeholder = opSelect.value === 'between' ? '最小值' : '数值';
        });

        row.append(fieldSelect, opSelect, valueInput, valueInput2, removeBtn);
        container.appendChild(row);
    }

    function collectFilters() {
        const rows = document.querySelectorAll('#screener-conditions .screener-cond-row');
        const filters = [];
        for (const row of rows) {
            const field = row.querySelector('.screener-field')?.value;
            const op = row.querySelector('.screener-op')?.value;
            const valStr = row.querySelector('.screener-value')?.value;
            if (!field || !op || !valStr) continue;

            let value;
            if (op === 'between') {
                const valStr2 = row.querySelector('.screener-value2')?.value;
                const lo = parseFloat(valStr);
                const hi = parseFloat(valStr2);
                if (isNaN(lo) || isNaN(hi)) continue;
                value = [lo, hi];
            } else {
                value = parseFloat(valStr);
                if (isNaN(value)) continue;
            }
            filters.push({ field, op, value });
        }
        return filters;
    }

    async function runCustom() {
        const filters = collectFilters();
        if (filters.length === 0) {
            App.toast('请至少添加一个筛选条件', 'error');
            return;
        }

        const resultDiv = document.getElementById('screener-result');
        if (resultDiv) resultDiv.innerHTML = Utils.skeletonTable(8, 6);

        try {
            const data = await App.fetchJSON('/api/screener/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filters, page_size: 10000 }),
            });
            if (!data.success) {
                App.toast(data.error || '筛选失败', 'error');
                return;
            }
            _lastResult = data;
            renderResult(data, '自定义条件');
            App.toast(`找到 ${data.total} 只股票`, 'success');
        } catch (e) {
            App.toast('选股失败: ' + e.message, 'error');
        }
    }

    // ── 结果渲染 ──

    function renderResult(data, label) {
        const container = document.getElementById('screener-result');
        if (!container) return;

        const stocks = data.stocks || [];
        if (stocks.length === 0) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">未找到符合条件的股票</div>';
            return;
        }

        const rows = stocks.map(s => {
            const changeClass = (s.change_pct || 0) >= 0 ? 'text-up' : 'text-down';
            const cap = s.market_cap != null ? s.market_cap.toFixed(1) + '亿' : '--';
            const pe = s.pe_ratio != null ? s.pe_ratio.toFixed(1) : '--';
            const pb = s.pb_ratio != null ? s.pb_ratio.toFixed(2) : '--';
            const tr = s.turnover_rate != null ? s.turnover_rate.toFixed(2) + '%' : '--';
            return `<tr>
                <td>${App.escapeHTML(s.code || '')}</td>
                <td>${App.escapeHTML(s.name || '')}</td>
                <td>${App.escapeHTML(s.industry || '--')}</td>
                <td>${s.price != null ? '¥' + s.price.toFixed(2) : '--'}</td>
                <td class="${changeClass}">${s.change_pct != null ? (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%' : '--'}</td>
                <td>${pe}</td>
                <td>${pb}</td>
                <td>${cap}</td>
                <td>${tr}</td>
                <td><button class="btn btn-sm" data-screener-action="add-watchlist" data-code="${App.escapeHTML(s.code || '')}">加自选</button></td>
            </tr>`;
        });
        container.innerHTML = `
            <div class="screener-result-header">
                <span class="screener-result-label">${App.escapeHTML(label)} — 共 ${data.total} 只</span>
                <div class="screener-result-actions">
                    <button class="btn btn-sm" id="screener-export-btn" data-screener-action="export-csv">导出 CSV</button>
                    <button class="btn btn-sm" id="screener-add-watchlist" data-screener-action="add-all-watchlist">全部加自选</button>
                </div>
            </div>
            <div class="table-wrap">
                <table class="sortable" id="screener-table">
                    <thead><tr>
                        <th data-sort="code">代码</th><th data-sort="name">名称</th><th data-sort="industry">行业</th><th data-sort="price">最新价</th><th data-sort="change">涨跌幅</th>
                        <th data-sort="pe">PE</th><th data-sort="pb">PB</th><th data-sort="cap">市值(亿)</th><th data-sort="turnover">换手率</th><th>操作</th>
                    </tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>
        `;
        Utils.enhanceTable('#screener-table', { pageSize: 20, searchable: true });
    }

    // ── CSV 导出 ──

    function exportCSV() {
        if (!_lastResult?.stocks?.length) {
            App.toast('没有可导出的数据', 'error');
            return;
        }
        const headers = ['代码', '名称', '行业', '最新价', '涨跌幅%', 'PE', 'PB', '市值(亿)', '换手率%'];
        const csvRows = [headers.join(',')];
        for (const s of _lastResult.stocks) {
            csvRows.push([
                s.code, s.name, s.industry,
                s.price ?? '', s.change_pct ?? '', s.pe_ratio ?? '',
                s.pb_ratio ?? '', s.market_cap ?? '', s.turnover_rate ?? '',
            ].join(','));
        }
        const blob = new Blob(['﻿' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `选股结果_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ── 加入自选股 ──

    async function addToWatchlist(code) {
        if (!code) {
            return {
                ok: false,
                status: 'failed',
                code: 'STOCK_CODE_REQUIRED',
            };
        }

        return App.addToWatchlist(code, {
            source: 'screener:add-watchlist',
            traceId: createActionTraceId('screener'),
        });
    }

    async function addAllToWatchlist() {
        if (!_lastResult?.stocks?.length) return;
        const codes = _lastResult.stocks.map(s => s.code).filter(Boolean);
        await App.addAllToWatchlist(codes);
    }

    function setLastPoolCodes(codes) {
        _lastPoolCodes = Array.isArray(codes) ? codes.filter(Boolean) : [];
    }

    // ── AI 选股 ──

    function initAI() {
        bindTabs();
        checkModelStatus();
        const trainBtn = document.getElementById('ai-train-btn');
        const predictBtn = document.getElementById('ai-predict-btn');
        trainBtn?.addEventListener('click', trainModel);
        predictBtn?.addEventListener('click', runAIPredict);
    }

    function bindTabs() {
        document.querySelectorAll('.screener-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.screener-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.screener-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const panel = document.getElementById(`screener-panel-${tab.dataset.tab}`);
                if (panel) panel.classList.add('active');
            });
        });
    }

    async function checkModelStatus() {
        const dot = document.querySelector('.ai-status-dot');
        const text = document.querySelector('.ai-status-text');
        const predictBtn = document.getElementById('ai-predict-btn');
        try {
            const data = await App.fetchJSON('/api/alpha/model-status');
            if (data.trained) {
                if (dot) dot.className = 'ai-status-dot trained';
                if (text) text.textContent = `模型已就绪（${data.feature_count} 个特征）`;
                if (predictBtn) predictBtn.disabled = false;
            } else {
                if (dot) dot.className = 'ai-status-dot untrained';
                if (text) text.textContent = '模型未训练，请先执行训练';
                if (predictBtn) predictBtn.disabled = true;
            }
        } catch {
            if (dot) dot.className = 'ai-status-dot untrained';
            if (text) text.textContent = '无法获取模型状态';
        }
    }

    async function trainModel() {
        const trainBtn = document.getElementById('ai-train-btn');
        const progressDiv = document.getElementById('ai-progress');
        const progressText = document.querySelector('.ai-progress-text');
        const modelType = document.getElementById('ai-model-type')?.value || 'lightgbm';

        if (trainBtn) trainBtn.disabled = true;
        if (progressDiv) progressDiv.style.display = '';
        if (progressText) progressText.textContent = '训练中，请稍候...';

        try {
            const data = await App.fetchJSON('/api/alpha/train-global', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_type: modelType }),
            });
            if (data.success) {
                App.toast(`训练完成：${data.n_samples} 样本，${data.n_features} 特征`, 'success');
                checkModelStatus();
            } else {
                App.toast(data.error || '训练失败', 'error');
            }
        } catch (e) {
            App.toast('训练请求失败: ' + e.message, 'error');
        } finally {
            if (trainBtn) trainBtn.disabled = false;
            if (progressDiv) progressDiv.style.display = 'none';
        }
    }

    async function runAIPredict() {
        const resultDiv = document.getElementById('ai-result');
        if (resultDiv) resultDiv.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

        try {
            const data = await App.fetchJSON('/api/alpha/screen-ai?top_n=20');
            if (!data.success) {
                App.toast(data.error || 'AI 选股失败', 'error');
                if (resultDiv) resultDiv.innerHTML = `<div class="text-muted text-center" style="padding:20px">${App.escapeHTML(data.error || 'AI 选股失败')}</div>`;
                return;
            }
            renderAIResult(data);
            App.toast(`AI 找到 ${data.total} 只推荐股票`, 'success');
        } catch (e) {
            App.toast('AI 选股失败: ' + e.message, 'error');
        }
    }

    function renderAIResult(data) {
        const container = document.getElementById('ai-result');
        if (!container) return;

        const stocks = data.stocks || [];
        if (stocks.length === 0) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">未找到推荐股票</div>';
            return;
        }

        const rows = stocks.map(s => {
            const probPct = (s.probability * 100).toFixed(1);
            const riskPct = (s.risk_score * 100).toFixed(0);
            const factors = s.key_factors || {};
            const topFactor = Object.entries(factors).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
            const factorStr = topFactor ? `${topFactor[0]}: ${topFactor[1].toFixed(2)}` : '--';
            return `<tr>
                <td>${s.rank}</td>
                <td>${App.escapeHTML(s.code || '')}</td>
                <td>${App.escapeHTML(s.name || '')}</td>
                <td>${App.escapeHTML(s.industry || '--')}</td>
                <td class="text-up">${probPct}%</td>
                <td>${riskPct}%</td>
                <td class="text-muted">${App.escapeHTML(factorStr)}</td>
                <td><button class="btn btn-sm" data-screener-action="add-watchlist" data-code="${App.escapeHTML(s.code || '')}">加自选</button></td>
            </tr>`;
        });

        container.innerHTML = `
            <div class="screener-result-header">
                <span class="screener-result-label">AI 推荐 TOP ${data.total}</span>
                <div class="screener-result-actions">
                    <button class="btn btn-sm" data-screener-action="add-all-ai-watchlist">全部加自选</button>
                </div>
            </div>
            <div class="table-wrap">
                <table class="sortable" id="ai-table">
                    <thead><tr>
                        <th>排名</th><th>代码</th><th>名称</th><th>行业</th>
                        <th>预测概率</th><th>置信度</th><th>关键因子</th><th>操作</th>
                    </tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>
        `;
    }

    async function addAllAIToWatchlist() {
        const rows = document.querySelectorAll('#ai-table tbody tr');
        const codes = [];
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 2) codes.push(cells[1].textContent.trim());
        });
        if (!codes.length) return;
        await App.addAllToWatchlist(codes);
    }

    // ── 从问财股票池渲染 ──

    async function renderFromPool(codes, query) {
        if (!codes || codes.length === 0) return;
        setLastPoolCodes(codes.slice(0, 100));
        // 切换到手动选股子Tab
        const manualTab = document.querySelector('.screener-tab[data-tab="manual"]');
        if (manualTab) manualTab.click();

        const resultDiv = document.getElementById('screener-result');
        if (resultDiv) resultDiv.innerHTML = Utils.skeletonTable(8, 6);

        try {
            // 尝试用选股器 API 批量查询
            const data = await App.fetchJSON('/api/screener/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ codes: codes.slice(0, 100), page_size: 10000 }),
            });
            if (data.success) {
                _lastResult = data;
                renderResult(data, `问财: ${query}`);
                App.toast(`已加载 ${data.total} 只股票`, 'success');
            } else {
                _renderCodeList(codes, query);
            }
        } catch {
            _renderCodeList(codes, query);
        }
    }

    function _renderCodeList(codes, query) {
        const container = document.getElementById('screener-result');
        if (!container) return;
        setLastPoolCodes(codes.slice(0, 100));
        const rows = codes.slice(0, 100).map(code =>
            `<tr><td>${App.escapeHTML(code)}</td><td>--</td><td>--</td><td>--</td><td>--</td><td>--</td><td>--</td><td>--</td><td>--</td>
            <td><button class="btn btn-sm" data-screener-action="add-watchlist" data-code="${App.escapeHTML(code)}">加自选</button></td></tr>`
        );
        container.innerHTML = `
            <div class="screener-result-header">
                <span class="screener-result-label">问财: ${App.escapeHTML(query)} — ${codes.length} 只</span>
                <div class="screener-result-actions">
                    <button class="btn btn-sm" data-screener-action="add-all-pool-watchlist">全部加自选</button>
                </div>
            </div>
            <div class="table-wrap"><table>
                <thead><tr><th>代码</th><th>名称</th><th>行业</th><th>最新价</th><th>涨跌幅</th><th>PE</th><th>PB</th><th>市值(亿)</th><th>换手率</th><th>操作</th></tr></thead>
                <tbody>${rows.join('')}</tbody>
            </table></div>`;
        App.toast(`已加载 ${codes.length} 只股票代码`, 'info');
    }

    // ── 公开接口 ──

    App.Screener = { init, runCustom, runPreset, exportCSV, addToWatchlist, addAllToWatchlist, trainModel, runAIPredict, addAllAIToWatchlist, loadFilters, renderFromPool };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
