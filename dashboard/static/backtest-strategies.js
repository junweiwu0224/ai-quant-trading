/* ── 回测模块：策略选择 / 参数 / 对比 ── */

Object.assign(App, {
    async compareStrategies() {
        const strategies = [...document.querySelectorAll('#bt-compare-section input:checked')].map(el => el.value);
        if (strategies.length === 0) return;
        const codes = this.btMultiSearch
            ? this.btMultiSearch.getSelectedCodes()
            : [document.getElementById('bt-code').value.trim()].filter(Boolean);
        if (codes.length === 0) return;

        const body = {
            strategies, codes: codes,
            start_date: document.getElementById('bt-start').value,
            end_date: document.getElementById('bt-end').value,
            initial_cash: parseFloat(document.getElementById('bt-cash').value),
        };

        try {
            const results = await App.fetchJSON('/api/backtest/compare', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
                label: '策略对比',
            });
            if (!results || results.length === 0) return;

            const labelMap = { dual_ma: '双均线', bollinger: '布林带', momentum: '动量' };
            const palette = ChartFactory.palette();
            ChartFactory.line('bt-compare-chart', {
                labels: results[0].equity_curve.map(p => p.date),
                datasets: results.map((r, i) => ({
                    label: labelMap[r.strategy] || r.strategy,
                    data: r.equity_curve.map(p => p.equity),
                    color: palette[i % palette.length],
                })),
            }, 'compare', {
                plugins: { legend: { labels: { color: ChartFactory.getColors().text } } },
            });
        } catch (e) {
            console.error('策略对比失败:', e);
        }
    },

    async _loadStrategies() {
        const select = document.getElementById('bt-strategy');
        if (!select) return;

        try {
            const strategies = await this.fetchJSON('/api/backtest/strategies');
            const visibleStrategies = (strategies || []).filter(s => !s.legacy_alias_for);
            this._strategiesData = strategies;
            select.innerHTML = visibleStrategies.map(s =>
                `<option value="${this.escapeHTML(s.name)}">${this.escapeHTML(s.label)}</option>`
            ).join('');
            this._onStrategyChange();
            this._bindBacktestSnapshotInvalidation();
        } catch (e) {
            console.error('加载策略列表失败:', e);
            select.innerHTML = '<option value="dual_ma">双均线策略</option>';
        }
    },

    _onStrategyChange() {
        const name = document.getElementById('bt-strategy')?.value;
        const container = document.getElementById('bt-params-fields');
        const wrapper = document.getElementById('bt-strategy-params');
        if (!container || !wrapper) return;

        const strategy = (this._strategiesData || []).find(s => s.name === name);
        const params = strategy?.params || {};
        const entries = Object.entries(params);

        if (entries.length === 0) {
            wrapper.style.display = 'none';
            container.innerHTML = '';
            return;
        }

        wrapper.style.display = '';
        const labelMap = {
            short_window: '短均线周期', long_window: '长均线周期',
            window: '窗口周期', num_std: '标准差倍数',
            lookback: '回看周期', entry_threshold: '动量阈值',
            period: 'RSI周期', oversold: '超卖线', overbought: '超买线',
            fast: '快线周期', slow: '慢线周期', signal: '信号线周期',
            k_period: 'K周期', d_period: 'D周期',
            buy_threshold: '买入阈值', sell_threshold: '卖出阈值',
            position_pct: '仓位比例', score_normalize: '分数归一化',
            mode: '信号模式', top_n: '排名买入数',
        };
        const selectMap = {
            mode: [['absolute', '绝对阈值'], ['ranking', '截面排名']],
        };
        container.innerHTML = entries.map(([k, v]) => {
            const label = labelMap[k] || k;
            const isBool = typeof v === 'boolean';
            const isFloat = typeof v === 'number' && !Number.isInteger(v);
            let inputType;
            if (selectMap[k]) {
                inputType = `<select data-param="${k}">${selectMap[k].map(([val, lbl]) => `<option value="${val}"${v === val ? ' selected' : ''}>${lbl}</option>`).join('')}</select>`;
            } else if (isBool) {
                inputType = `<select data-param="${k}"><option value="false"${!v ? ' selected' : ''}>否</option><option value="true"${v ? ' selected' : ''}>是</option></select>`;
            } else {
                inputType = `<input type="number" data-param="${k}" value="${v}" step="${isFloat ? 0.01 : 1}">`;
            }
            return `<div class="bt-param-row"><label>${label}</label>${inputType}</div>`;
        }).join('');
    },

    _collectStrategyParams() {
        const container = document.getElementById('bt-params-fields');
        if (!container) return {};
        const params = {};
        container.querySelectorAll('[data-param]').forEach(el => {
            const key = el.dataset.param;
            if (el.tagName === 'SELECT') {
                if (el.value === 'true' || el.value === 'false') {
                    params[key] = el.value === 'true';
                } else {
                    params[key] = el.value;
                }
            } else {
                const val = parseFloat(el.value);
                if (!isNaN(val)) params[key] = val;
            }
        });
        return params;
    },
});
