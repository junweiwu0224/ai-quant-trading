/**
 * 条件选股模块
 * 条件构建器 + 预设策略 + 结果表格 + CSV 导出
 */
(function () {
    'use strict';

    let _fields = [];
    let _presets = [];
    let _lastResult = null;

    // ── 初始化 ──

    async function init() {
        await Promise.all([loadFields(), loadPresets()]);
        bindEvents();
        addConditionRow();
        initAI();
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
        if (resultDiv) resultDiv.innerHTML = '<div class="loading"><span class="spinner"></span>筛选中...</div>';

        try {
            const data = await App.fetchJSON('/api/screener/run-preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preset_name: name, page_size: 50 }),
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

    // ── 自定义条件 ──

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
        if (resultDiv) resultDiv.innerHTML = '<div class="loading"><span class="spinner"></span>筛选中...</div>';

        try {
            const data = await App.fetchJSON('/api/screener/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filters, page_size: 50 }),
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
            const cap = s.market_cap != null ? s.market_cap.toFixed(1) : '--';
            const pe = s.pe_ratio != null ? s.pe_ratio.toFixed(1) : '--';
            const pb = s.pb_ratio != null ? s.pb_ratio.toFixed(2) : '--';
            const tr = s.turnover_rate != null ? s.turnover_rate.toFixed(2) : '--';
            return `<tr>
                <td>${App.escapeHTML(s.code || '')}</td>
                <td>${App.escapeHTML(s.name || '')}</td>
                <td>${App.escapeHTML(s.industry || '--')}</td>
                <td>${s.price != null ? s.price.toFixed(2) : '--'}</td>
                <td class="${changeClass}">${s.change_pct != null ? (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%' : '--'}</td>
                <td>${pe}</td>
                <td>${pb}</td>
                <td>${cap}</td>
                <td>${tr}%</td>
                <td><button class="btn btn-sm" onclick="App.Screener.addToWatchlist('${App.escapeHTML(s.code || '')}')">加自选</button></td>
            </tr>`;
        }).join('');
        container.innerHTML = `
            <div class="screener-result-header">
                <span class="screener-result-label">${App.escapeHTML(label)} — 共 ${data.total} 只</span>
                <div class="screener-result-actions">
                    <button class="btn btn-sm" id="screener-export-btn" onclick="App.Screener.exportCSV()">导出 CSV</button>
                    <button class="btn btn-sm" id="screener-add-watchlist" onclick="App.Screener.addAllToWatchlist()">全部加自选</button>
                </div>
            </div>
            <div class="table-wrap">
                <table class="sortable" id="screener-table">
                    <thead><tr>
                        <th>代码</th><th>名称</th><th>行业</th><th>最新价</th><th>涨跌幅</th>
                        <th>PE</th><th>PB</th><th>市值(亿)</th><th>换手率</th><th>操作</th>
                    </tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>
        `;
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
        if (!code) return;
        try {
            const resp = await fetch(`/api/watchlist/${code}`, { method: 'POST' });
            const data = await resp.json();
            if (data.success) {
                App.toast(`${code} 已加入自选股`, 'success');
            } else {
                App.toast(data.error || '添加失败', 'error');
            }
        } catch (e) {
            App.toast('加入自选股失败', 'error');
        }
    }

    async function addAllToWatchlist() {
        if (!_lastResult?.stocks?.length) return;
        const codes = _lastResult.stocks.map(s => s.code).filter(Boolean);
        let ok = 0, fail = 0;
        for (const code of codes) {
            try {
                const resp = await fetch(`/api/watchlist/${code}`, { method: 'POST' });
                const data = await resp.json();
                if (data.success) ok++;
                else fail++;
            } catch {
                fail++;
            }
        }
        App.toast(`自选股: 成功 ${ok}，失败 ${fail}`, ok > 0 ? 'success' : 'error');
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
        if (resultDiv) resultDiv.innerHTML = '<div class="loading"><span class="spinner"></span>AI 分析中...</div>';

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
                <td><button class="btn btn-sm" onclick="App.Screener.addToWatchlist('${App.escapeHTML(s.code || '')}')">加自选</button></td>
            </tr>`;
        });

        container.innerHTML = `
            <div class="screener-result-header">
                <span class="screener-result-label">AI 推荐 TOP ${data.total}</span>
                <div class="screener-result-actions">
                    <button class="btn btn-sm" onclick="App.Screener.addAllAIToWatchlist()">全部加自选</button>
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
        let ok = 0, fail = 0;
        for (const code of codes) {
            try {
                const resp = await fetch(`/api/watchlist/${code}`, { method: 'POST' });
                const data = await resp.json();
                if (data.success) ok++; else fail++;
            } catch { fail++; }
        }
        App.toast(`自选股: 成功 ${ok}，失败 ${fail}`, ok > 0 ? 'success' : 'error');
    }

    // ── 公开接口 ──

    App.Screener = { init, runCustom, runPreset, exportCSV, addToWatchlist, addAllToWatchlist, trainModel, runAIPredict, addAllAIToWatchlist };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
