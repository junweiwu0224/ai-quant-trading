/* ── 条件选股：AI 选股与问财股票池导入 ── */
(function () {
    'use strict';

    const Screener = App.Screener || (App.Screener = {});

    Object.assign(Screener, {
        initAI() {
            if (this.state?.aiInitialized) return;
            if (this.state) this.state.aiInitialized = true;
            this.bindTabs();
            this.checkModelStatus();
            const trainBtn = document.getElementById('ai-train-btn');
            const predictBtn = document.getElementById('ai-predict-btn');
            trainBtn?.addEventListener('click', () => this.trainModel());
            predictBtn?.addEventListener('click', () => this.runAIPredict());
        },

        bindTabs() {
            document.querySelectorAll('.screener-tab').forEach(tab => {
                if (tab.dataset.bound === 'true') return;
                tab.dataset.bound = 'true';
                tab.addEventListener('click', () => {
                    document.querySelectorAll('.screener-tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.screener-panel').forEach(p => p.classList.remove('active'));
                    tab.classList.add('active');
                    const panel = document.getElementById(`screener-panel-${tab.dataset.tab}`);
                    if (panel) panel.classList.add('active');
                });
            });
        },

        async checkModelStatus() {
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
        },

        async trainModel() {
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
                    this.checkModelStatus();
                } else {
                    App.toast(data.error || '训练失败', 'error');
                }
            } catch (e) {
                App.toast('训练请求失败: ' + e.message, 'error');
            } finally {
                if (trainBtn) trainBtn.disabled = false;
                if (progressDiv) progressDiv.style.display = 'none';
            }
        },

        async runAIPredict() {
            const resultDiv = document.getElementById('ai-result');
            if (resultDiv) resultDiv.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

            try {
                const data = await App.fetchJSON('/api/alpha/screen-ai?top_n=20');
                if (!data.success) {
                    App.toast(data.error || 'AI 选股失败', 'error');
                    if (resultDiv) resultDiv.innerHTML = `<div class="text-muted text-center" style="padding:20px">${App.escapeHTML(data.error || 'AI 选股失败')}</div>`;
                    return;
                }
                this.renderAIResult(data);
                App.toast(`AI 找到 ${data.total} 只推荐股票`, 'success');
            } catch (e) {
                App.toast('AI 选股失败: ' + e.message, 'error');
            }
        },

        renderAIResult(data) {
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
        },

        async addAllAIToWatchlist() {
            const rows = document.querySelectorAll('#ai-table tbody tr');
            const codes = [];
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 2) codes.push(cells[1].textContent.trim());
            });
            if (!codes.length) return;
            await App.addAllToWatchlist(codes);
        },

        async renderFromPool(codes, query) {
            if (!codes || codes.length === 0) return;
            this.setLastPoolCodes(codes.slice(0, 100));
            const manualTab = document.querySelector('.screener-tab[data-tab="manual"]');
            if (manualTab) manualTab.click();

            const resultDiv = document.getElementById('screener-result');
            if (resultDiv) resultDiv.innerHTML = Utils.skeletonTable(8, 6);

            try {
                const data = await App.fetchJSON('/api/screener/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ codes: codes.slice(0, 100), page_size: 10000 }),
                });
                if (data.success) {
                    this.state.lastResult = data;
                    this.renderResult(data, `问财: ${query}`);
                    App.toast(`已加载 ${data.total} 只股票`, 'success');
                } else {
                    this._renderCodeList(codes, query);
                }
            } catch {
                this._renderCodeList(codes, query);
            }
        },

        _renderCodeList(codes, query) {
            const container = document.getElementById('screener-result');
            if (!container) return;
            this.setLastPoolCodes(codes.slice(0, 100));
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
        },
    });

    if (typeof Screener.initAI === 'function') {
        Screener.initAI();
    }
})();
