/* ── 持仓模块：持仓明细表 ── */

Object.assign(App, {
    _pfRenderTable() {
        const positions = this._pf.positions;
        const posBody = document.querySelector('#pf-positions tbody');
        const totalFoot = document.getElementById('pf-positions-total');

        // 填充策略筛选下拉
        this._pfPopulateStrategyFilter(positions);

        // 搜索过滤
        const query = (this._pf.searchQuery || '').toLowerCase();
        let filtered = positions;
        if (query) {
            filtered = positions.filter(p =>
                p.code.toLowerCase().includes(query) ||
                (p.name || '').toLowerCase().includes(query) ||
                (p.strategy_name || '').toLowerCase().includes(query)
            );
        }
        const stratFilter = this._pf.strategyFilter;
        if (stratFilter) {
            filtered = filtered.filter(p => (p.strategy_name || '未分配') === stratFilter);
        }

        // 排序
        const sortKey = this._pf.sortKey || 'mv';
        const sortDir = this._pf.sortDir || 'desc';
        const sortMap = {
            'code': 'code', 'name': 'name', 'volume': 'volume',
            'avg': 'avg_price', 'price': 'current_price', 'mv': 'market_value',
            'pnl': 'pnl', 'pnl-pct': 'pnl_pct', 'weight': 'position_pct',
            'days': 'holding_days',
        };
        const field = sortMap[sortKey] || 'market_value';
        filtered.sort((a, b) => {
            let va = a[field], vb = b[field];
            if (typeof va === 'string') {
                return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            return sortDir === 'asc' ? va - vb : vb - va;
        });

        if (filtered.length === 0) {
            posBody.innerHTML = '<tr><td colspan="14" class="text-muted">暂无持仓数据</td></tr>';
            totalFoot.innerHTML = '';
            return;
        }

        const colorClass = (v) => v > 0 ? 'pf-val-up' : v < 0 ? 'pf-val-down' : 'pf-val-flat';
        const fmtPct = (v) => (v * 100).toFixed(2) + '%';

        posBody.innerHTML = filtered.map(p => {
            const pnlSign = p.pnl >= 0 ? '+' : '';
            const dpSign = p.daily_pnl >= 0 ? '+' : '';
            const slClass = p.stop_loss_triggered ? 'pf-sl-breach' : '';
            const tpClass = p.take_profit_triggered ? 'pf-sl-breach' : '';
            return `<tr>
                <td class="pf-code"><a href="#" onclick="App.openStockDetail('${this.escapeHTML(p.code)}');return false">${this.escapeHTML(p.code)}</a></td>
                <td class="pf-name">${this.escapeHTML(p.name || '--')}</td>
                <td class="pf-right pf-mono">${p.volume}</td>
                <td class="pf-right pf-mono">${p.avg_price.toFixed(2)}</td>
                <td class="pf-right pf-mono">${p.current_price.toFixed(2)}</td>
                <td class="pf-right pf-mono">${this.fmt(p.market_value)}</td>
                <td class="pf-right pf-mono ${colorClass(p.pnl)}">${pnlSign}${this.fmt(p.pnl)}</td>
                <td class="pf-right pf-mono ${colorClass(p.pnl_pct)}">${pnlSign}${fmtPct(p.pnl_pct)}</td>
                <td class="pf-right pf-mono">${fmtPct(p.position_pct)}</td>
                <td class="pf-right pf-mono pf-col-hide-mobile">${p.holding_days}天</td>
                <td class="pf-right pf-mono pf-col-hide-mobile ${slClass}"><span class="pf-sl-indicator" onclick="App.pfEditSltp('${this.escapeHTML(p.code)}','${this.escapeHTML(p.name||'')}')" title="点击编辑">${p.stop_loss_price.toFixed(2)}</span></td>
                <td class="pf-right pf-mono pf-col-hide-mobile ${tpClass}"><span class="pf-sl-indicator" onclick="App.pfEditSltp('${this.escapeHTML(p.code)}','${this.escapeHTML(p.name||'')}')" title="点击编辑">${p.take_profit_price.toFixed(2)}</span></td>
                <td class="pf-col-hide-mobile"><span class="pf-strategy-tag">${this.escapeHTML(p.strategy_name || '--')}</span></td>
                <td><div class="pf-row-actions">
                    <button class="btn" onclick="App.pfPartialClose('${this.escapeHTML(p.code)}',${p.volume})">卖出</button>
                    <button class="btn btn-danger" onclick="App.pfFullClose('${this.escapeHTML(p.code)}')">清仓</button>
                </div></td>
            </tr>`;
        }).join('');

        // 汇总行
        const totVol = filtered.reduce((s, p) => s + p.volume, 0);
        const totMV = filtered.reduce((s, p) => s + p.market_value, 0);
        const totPnl = filtered.reduce((s, p) => s + p.pnl, 0);
        const totCost = filtered.reduce((s, p) => s + p.cost_amount, 0);
        const totPnlPct = totCost > 0 ? totPnl / totCost : 0;
        const totWeight = filtered.reduce((s, p) => s + p.position_pct, 0);

        totalFoot.innerHTML = `<tr>
            <td colspan="2" class="pf-right"><strong>合计 (${filtered.length})</strong></td>
            <td class="pf-right pf-mono">${totVol}</td>
            <td colspan="2"></td>
            <td class="pf-right pf-mono">${this.fmt(totMV)}</td>
            <td class="pf-right pf-mono ${colorClass(totPnl)}">${totPnl >= 0 ? '+' : ''}${this.fmt(totPnl)}</td>
            <td class="pf-right pf-mono ${colorClass(totPnlPct)}">${(totPnlPct * 100).toFixed(2)}%</td>
            <td class="pf-right pf-mono">${(totWeight * 100).toFixed(2)}%</td>
            <td colspan="5"></td>
        </tr>`;
    },

    _pfPopulateStrategyFilter(positions) {
        const select = document.getElementById('pf-filter-strategy');
        if (!select) return;
        const strategies = [...new Set(positions.map(p => p.strategy_name || '未分配'))];
        const current = select.value;
        select.innerHTML = '<option value="">全部策略</option>' +
            strategies.map(s => `<option value="${this.escapeHTML(s)}">${this.escapeHTML(s)}</option>`).join('');
        select.value = current;
    },

    _pfTableEventsBound: false,

    _pfBindTableEvents() {
        if (this._pfTableEventsBound) return;

        const searchInput = document.getElementById('pf-search');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                this._pf.searchQuery = searchInput.value;
                this._pfRenderTable();
            });
        }
        const stratSelect = document.getElementById('pf-filter-strategy');
        if (stratSelect) {
            stratSelect.addEventListener('change', () => {
                this._pf.strategyFilter = stratSelect.value;
                this._pfRenderTable();
            });
        }

        // 表头排序
        document.querySelectorAll('#pf-positions thead th[data-sort]').forEach(th => {
            th.addEventListener('click', () => {
                const key = th.dataset.sort;
                if (this._pf.sortKey === key) {
                    this._pf.sortDir = this._pf.sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this._pf.sortKey = key;
                    this._pf.sortDir = 'desc';
                }
                this._pfRenderTable();
            });
        });

        this._pfTableEventsBound = true;
    },
});
