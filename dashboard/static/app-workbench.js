(function attachAppWorkbench(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        async loadStockList() {
            try {
                // 并行加载自选股和全市场股票
                const [watchlist, allStocks] = await Promise.all([
                    this.fetchJSON('/api/watchlist').catch(() => []),
                    this.fetchJSON('/api/stock/search?q=&limit=6000').catch(() => []),
                ]);
                const normalizeStockSearchResults = globalThis.Utils && typeof globalThis.Utils.normalizeStockSearchResults === 'function'
                    ? globalThis.Utils.normalizeStockSearchResults
                    : ((payload) => {
                        const list = Array.isArray(payload)
                            ? payload
                            : payload && typeof payload === 'object'
                                ? (payload.results ?? payload.data ?? payload.items ?? payload.list)
                                : [];
                        if (!Array.isArray(list)) return [];
                        return list.filter((item) => {
                            if (!item || typeof item !== 'object') return false;
                            const code = typeof item.code === 'string'
                                ? item.code.trim()
                                : String(item.code ?? '').trim();
                            return code.length > 0;
                        });
                    });
                this.watchlistCache = normalizeStockSearchResults(watchlist);
                this.stockCache = normalizeStockSearchResults(allStocks);
                this._allStocks = this.stockCache;

                // 全市场搜索数据源（本地过滤，响应快）
                const fullMarketFilter = (q) => {
                    const list = Array.isArray(this._allStocks) ? this._allStocks : [];
                    if (!list || list.length === 0) return [];
                    if (!q) return list.slice(0, 50);
                    const ql = q.toLowerCase();
                    return list.filter(s =>
                        s.code.includes(q) || (s.name && s.name.toLowerCase().includes(ql))
                    ).slice(0, 50);
                };

                this.btMultiSearch = new MultiSearchBox('bt-code', 'bt-code-dropdown', 'bt-codes-tags', { maxResults: 30 });
                this.btMultiSearch.setDataSource(fullMarketFilter);
                this._bindBacktestSnapshotInvalidation?.();

                const alphaSearch = new SearchBox('alpha-code', 'alpha-code-dropdown', {
                    maxResults: 30,
                    formatItem: (s) => `${s.code} ${s.name || ''}`,
                });
                alphaSearch.setDataSource(fullMarketFilter);
                alphaSearch.onSelect((item) => {
                    document.getElementById('alpha-code').value = item.code;
                });

                this.paperMultiSearch = new MultiSearchBox('pp-codes', 'pp-codes-dropdown', 'pp-codes-tags', { maxResults: 30 });
                this.paperMultiSearch.setDataSource(fullMarketFilter);

                Watchlist.setSelected(this.watchlistCache.map(s => s.code));
            } catch (e) {
                this.toast('股票列表加载失败', 'error');
            }
        },

        async loadBenchmarks() {
            try {
                const benchmarks = await this.fetchJSON('/api/backtest/benchmarks');
                const select = document.getElementById('bt-benchmark');
                if (!select || !benchmarks) return;
                benchmarks.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.code;
                    opt.textContent = b.name;
                    select.appendChild(opt);
                });
            } catch (e) {
                console.error('基准列表加载失败:', e);
            }
        },

        exportCSV() {
            const data = this._lastBacktestData;
            if (!data) { this.toast('请先运行回测', 'error'); return; }

            const rows = [['日期', '权益']];
            (data.equity_curve || []).forEach(p => rows.push([p.date, p.equity]));
            rows.push([]);
            rows.push(['交易明细']);
            rows.push(['日期', '代码', '方向', '价格', '数量', '入场价']);
            (data.trades || []).forEach(t => {
                rows.push([t.datetime, t.code, t.direction === 'long' ? '买入' : '卖出', t.price, t.volume, t.entry_price || '']);
            });
            rows.push([]);
            rows.push(['统计指标']);
            rows.push(['总收益率', (data.total_return * 100).toFixed(2) + '%']);
            rows.push(['年化收益', (data.annual_return * 100).toFixed(2) + '%']);
            rows.push(['最大回撤', (data.max_drawdown * 100).toFixed(2) + '%']);
            rows.push(['夏普比率', data.sharpe_ratio]);
            rows.push(['Sortino比率', data.sortino_ratio]);
            rows.push(['Calmar比率', data.calmar_ratio]);
            rows.push(['胜率', (data.win_rate * 100).toFixed(1) + '%']);
            rows.push(['盈亏比', data.profit_loss_ratio]);
            rows.push(['交易次数', data.total_trades]);

            const csv = '﻿' + rows.map(r => r.join(',')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `backtest_${data.start_date}_${data.end_date}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            this.toast('CSV导出成功', 'success');
        },

        async exportPDF(event) {
            const data = this._lastBacktestData;
            if (!data) { this.toast('请先运行回测', 'error'); return; }

            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '生成中...';

            try {
                const body = {
                    strategy: document.getElementById('bt-strategy').value,
                    codes: this.btMultiSearch
                        ? this.btMultiSearch.getSelectedCodes()
                        : [document.getElementById('bt-code').value.trim()].filter(Boolean),
                    start_date: document.getElementById('bt-start').value,
                    end_date: document.getElementById('bt-end').value,
                    initial_cash: parseFloat(document.getElementById('bt-cash').value) || 100000,
                    commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                    stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                    slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                    benchmark: document.getElementById('bt-benchmark').value || '',
                    enable_risk: document.getElementById('bt-risk').value === 'true',
                };

                const res = await fetch('/api/backtest/report/pdf', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });

                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `backtest_report_${body.start_date}_${body.end_date}.pdf`;
                a.click();
                URL.revokeObjectURL(url);
                this.toast('PDF报告已生成', 'success');
            } catch (err) {
                this.toast('PDF生成失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '导出PDF报告';
            }
        },

        quickBacktest(strategyName) {
            document.getElementById('bt-strategy').value = strategyName;
            this.switchTab('research');
            requestAnimationFrame(() => {
                document.querySelector('.research-sub-tab[data-subtab="backtest"]')?.click();
            });
        },

        bindStrategyChips() {
            document.addEventListener('click', (e) => {
                const chip = e.target.closest('.chip');
                if (!chip) return;
                e.preventDefault();
                const checkbox = chip.querySelector('input[type="checkbox"]');
                if (!checkbox) return;
                checkbox.checked = !checkbox.checked;
                chip.classList.toggle('active', checkbox.checked);
                this.compareStrategies();
            });
        },

        toggleBrokerConfig() {
            const brokerTab = document.querySelector('.trade-sub-tab[data-subtab="broker"]');
            if (brokerTab) brokerTab.click();
        },

        async loadBrokerConfig() {
            try {
                const config = await this.fetchJSON('/api/broker');
                document.getElementById('br-type').value = config.broker_type || 'simulated';
                document.getElementById('br-account').value = config.account_id || '';
                document.getElementById('br-addr').value = config.gateway_addr || '';
                document.getElementById('br-appid').value = config.app_id || '';
                document.getElementById('br-auth').value = config.auth_code || '';
            } catch (e) {
                this.toast('加载券商配置失败', 'error');
            }
        },

        async saveBrokerConfig() {
            const data = {
                broker_type: document.getElementById('br-type').value,
                account_id: document.getElementById('br-account').value.trim(),
                gateway_addr: document.getElementById('br-addr').value.trim(),
                app_id: document.getElementById('br-appid').value.trim(),
                auth_code: document.getElementById('br-auth').value.trim(),
            };
            try {
                await App.fetchJSON('/api/broker', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                    label: '保存券商配置',
                });
                this.toast('券商配置已保存', 'success');
            } catch (e) {
                this.toast('保存失败: ' + e.message, 'error');
            }
        },

        async testBrokerConn() {
            try {
                const data = await App.fetchJSON('/api/broker/test', { method: 'POST', label: '连接测试' });
                const extra = data.stub ? '（桩实现，需部署 Gateway）' : '';
                this.toast(`${data.message}${extra}`, data.success ? 'success' : 'warning');
            } catch (e) {
                this.toast('连接测试失败: ' + e.message, 'error');
            }
        },

        onBrokerTypeChange(type) {
            const addr = document.getElementById('br-addr');
            const account = document.getElementById('br-account');
            const hint = {
                simulated: { addr: '', account: '' },
                ctp: { addr: 'tcp://180.168.146.187:10130', account: '期货账号' },
                xtp: { addr: '交易服务器IP:端口', account: '资金账号' },
            }[type] || {};
            if (addr) addr.placeholder = hint.addr || '网关地址';
            if (account) account.placeholder = hint.account || '券商账户编号';
        },

        async loadTradeTab() {
            try {
                const so = { silent: true };
                const [snapshot, equityHistory, industry] = await Promise.all([
                    this.fetchJSON('/api/portfolio/snapshot', so).catch(() => null),
                    this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
                    this.fetchJSON('/api/portfolio/industry-distribution', so).catch(() => []),
                ]);
                const shared = { snapshot, equityHistory, industry };
                await Promise.all([
                    this.loadPortfolio(shared),
                    this.loadRisk(shared),
                    this.loadActiveOrders(),
                ]);
            } catch (e) {
                this.toast('交易数据加载失败: ' + e.message, 'error');
            }
        },

        async loadActiveOrders() {
            try {
                const data = await this.fetchJSON('/api/paper/orders?status=pending&page_size=50', { silent: true });
                const orders = data?.data?.items || [];
                this._activeOrders = orders;
                this.renderActiveOrders(orders);
            } catch {
                this._activeOrders = [];
                this.renderActiveOrders([]);
            }
        },

        renderActiveOrders(orders) {
            const tbody = document.querySelector('#active-orders-table tbody');
            const countEl = document.getElementById('active-orders-count');
            const panicBtn = document.getElementById('panic-btn');
            if (!tbody) return;

            if (countEl) countEl.textContent = orders.length;
            if (panicBtn) panicBtn.style.display = orders.length > 0 ? '' : 'none';

            if (orders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无挂单</td></tr>';
                return;
            }

            const typeMap = { market: '市价', limit: '限价', stop_loss: '止损', take_profit: '止盈' };
            tbody.innerHTML = orders.map(o => {
                const dirCls = o.direction === 'buy' ? 'text-up' : 'text-down';
                const dirText = o.direction === 'buy' ? '买入' : '卖出';
                return `<tr>
                <td><a href="#" class="stock-link" data-code="${this.escapeHTML(o.code)}">${this.escapeHTML(o.code)}</a></td>
                <td class="${dirCls}">${dirText}</td>
                <td>${typeMap[o.order_type] || o.order_type}</td>
                <td>${o.price ? '¥' + o.price.toFixed(2) : '市价'}</td>
                <td>${o.volume}</td>
                <td><span class="badge badge-warning">待撮合</span></td>
                <td><button class="btn btn-sm btn-danger" data-app-action="cancel-active-order" data-order-id="${this.escapeHTML(o.order_id)}">撤销</button></td>
            </tr>`;
            }).join('');
        },

        async cancelActiveOrder(orderId) {
            try {
                await this.fetchJSON(`/api/paper/orders/${orderId}`, { method: 'DELETE' });
                this.toast('订单已撤销', 'success');
                this.loadActiveOrders();
                this.emit('data:portfolio-updated', { source: 'cancel' });
            } catch (e) {
                this.toast('撤销失败: ' + e.message, 'error');
            }
        },

        async panicCancelAll() {
            const orders = this._activeOrders || [];
            if (orders.length === 0) return;
            if (!confirm(`确定撤销全部 ${orders.length} 笔挂单？`)) return;

            const panicBtn = document.getElementById('panic-btn');
            if (panicBtn) { panicBtn.disabled = true; panicBtn.textContent = '撤销中...'; }

            try {
                const results = await Promise.allSettled(
                    orders.map(o => this.fetchJSON(`/api/paper/orders/${o.order_id}`, { method: 'DELETE' }))
                );
                const succeeded = results.filter(r => r.status === 'fulfilled').length;
                const failed = results.length - succeeded;
                if (failed === 0) {
                    this.toast(`已撤销全部 ${succeeded} 笔订单`, 'success');
                } else {
                    this.toast(`撤销完成：成功 ${succeeded}，失败 ${failed}`, 'warning');
                }
                this.loadActiveOrders();
                this.emit('data:portfolio-updated', { source: 'panic' });
            } catch (e) {
                this.toast('批量撤销异常: ' + e.message, 'error');
            } finally {
                if (panicBtn) { panicBtn.disabled = false; panicBtn.textContent = '一键全撤'; }
            }
        },
    });
})(window);
