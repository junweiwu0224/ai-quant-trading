/**
 * 条件选股模块
 * 条件构建器 + 预设策略 + 结果表格 + CSV 导出
 */
(function () {
    'use strict';

    const Screener = App.Screener || (App.Screener = {});
    const state = Screener.state || (Screener.state = {
        fields: [],
        presets: [],
        lastResult: null,
        lastPoolCodes: [],
        initialized: false,
    });

    function createActionTraceId(prefix) {
        if (window.LocalMCP && typeof window.LocalMCP.createTraceId === 'function') {
            return window.LocalMCP.createTraceId(prefix);
        }
        const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : 'screener';
        return `${safePrefix}-${Date.now()}`;
    }

    // ── 初始化 ──

    async function init() {
        if (state.initialized) return;
        state.initialized = true;
        await Promise.all([loadFields(), loadPresets()]);
        bindEvents();
        bindActionDelegation();
        addConditionRow();
        Screener.initAI?.();
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
            state.fields = data.fields || [];
        } catch (e) {
            console.error('加载字段失败:', e);
        }
    }

    async function loadPresets() {
        try {
            const data = await App.fetchJSON('/api/screener/presets');
            state.presets = data.presets || [];
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
                Screener.addAllAIToWatchlist?.();
                return;
            }

            if (action === 'add-all-pool-watchlist') {
                e.preventDefault();
                if (state.lastPoolCodes.length > 0) {
                    App.addAllToWatchlist(state.lastPoolCodes.slice());
                }
            }
        });
    }

    // ── 预设策略 ──

    function renderPresets() {
        const container = document.getElementById('screener-presets');
        if (!container) return;
        container.innerHTML = state.presets.map(p =>
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
            state.lastResult = data;
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
        const f = state.fields.find(x => x.field === field);
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
            state.fields.filter(f => f.type === 'number').map(f =>
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
            state.lastResult = data;
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
        if (!state.lastResult?.stocks?.length) {
            App.toast('没有可导出的数据', 'error');
            return;
        }
        const headers = ['代码', '名称', '行业', '最新价', '涨跌幅%', 'PE', 'PB', '市值(亿)', '换手率%'];
        const csvRows = [headers.join(',')];
        for (const s of state.lastResult.stocks) {
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
        if (!state.lastResult?.stocks?.length) return;
        const codes = state.lastResult.stocks.map(s => s.code).filter(Boolean);
        await App.addAllToWatchlist(codes);
    }

    function setLastPoolCodes(codes) {
        state.lastPoolCodes = Array.isArray(codes) ? codes.filter(Boolean) : [];
    }

    // ── 公开接口 ──

    Object.assign(Screener, {
        init,
        runCustom,
        runPreset,
        exportCSV,
        addToWatchlist,
        addAllToWatchlist,
        loadFilters,
        renderResult,
        setLastPoolCodes,
    });

if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
            init();
        });
    } else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
        init();
    }
})();
