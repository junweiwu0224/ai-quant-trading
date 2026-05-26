/* ── 回测模块 ── */

Object.assign(App, {
    _setBacktestDiagnoseEnabled(isEnabled) {
        const diagnoseBtn = document.getElementById('ensemble-diagnose-btn')
            || document.querySelector('#bt-results button[title="AI 回测诊断"]');
        if (!diagnoseBtn) return;
        diagnoseBtn.disabled = !isEnabled;
    },

    _clearBacktestSnapshot() {
        this._lastBacktestData = null;
        this._lastBacktestBody = null;
        this._setBacktestDiagnoseEnabled(false);
    },

    _bindBacktestSnapshotInvalidation() {
        const invalidateSnapshot = () => {
            this._clearBacktestSnapshot();
        };
        const snapshotFieldIds = [
            'bt-strategy',
            'bt-start',
            'bt-end',
            'bt-cash',
            'bt-commission',
            'bt-stamp-tax',
            'bt-slippage',
            'bt-benchmark',
            'bt-risk',
            'bt-period',
        ];
        snapshotFieldIds.forEach((fieldId) => {
            const field = document.getElementById(fieldId);
            if (!field) {
                return;
            }
            field.onchange = (e) => {
                invalidateSnapshot();
                if (e.target?.id === 'bt-strategy') {
                    this._onStrategyChange();
                }
            };
        });
        const paramsContainer = document.getElementById('bt-params-fields');
        if (paramsContainer) {
            paramsContainer.onchange = () => {
                invalidateSnapshot();
            };
            paramsContainer.oninput = () => {
                invalidateSnapshot();
            };
        }
        if (this.btMultiSearch) {
            this.btMultiSearch.onToggle = () => {
                invalidateSnapshot();
            };
        }
        const btCodeInput = document.getElementById('bt-code');
        if (btCodeInput && !this.btMultiSearch) {
            btCodeInput.onchange = () => {
                invalidateSnapshot();
            };
        }
        this._setBacktestDiagnoseEnabled(Boolean(this._lastBacktestData));
    },

    bindBacktest() {
        const form = document.getElementById('backtest-form');
        if (!form) return;

        const strategySelect = document.getElementById('bt-strategy');
        if (strategySelect) {
            strategySelect.removeAttribute('onchange');
        }

        const exportCsvBtn = document.getElementById('bt-export-csv-btn');
        if (exportCsvBtn) {
            exportCsvBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportCSV();
            });
        }

        const exportPdfBtn = document.getElementById('bt-export-pdf-btn');
        if (exportPdfBtn) {
            exportPdfBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportPDF(e);
            });
        }

        const diagnoseBtn = document.getElementById('ensemble-diagnose-btn')
            || document.querySelector('#bt-results button[title="AI 回测诊断"]');
        if (diagnoseBtn) {
            diagnoseBtn.removeAttribute('onclick');
            diagnoseBtn.id = diagnoseBtn.id || 'ensemble-diagnose-btn';
            diagnoseBtn.onclick = (e) => {
                e.preventDefault();
                if (!this._lastBacktestData) {
                    this.toast('请先运行回测', 'error');
                    return;
                }
                Ensemble?.diagnoseBacktest?.(this._lastBacktestData);
            };
        }

        const monteCarloBtn = document.getElementById('mc-run-btn');
        if (monteCarloBtn) {
            monteCarloBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.runMonteCarlo();
            });
        }

        this._bindBacktestSnapshotInvalidation();

        // 动态加载策略列表
        this._loadStrategies();

        if (form.dataset.backtestSubmitBound === 'true') {
            return;
        }
        form.dataset.backtestSubmitBound = 'true';
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const codes = this.btMultiSearch
                ? this.btMultiSearch.getSelectedCodes()
                : [document.getElementById('bt-code').value.trim()].filter(Boolean);
            const startDate = document.getElementById('bt-start').value;
            const endDate = document.getElementById('bt-end').value;
            const cash = parseFloat(document.getElementById('bt-cash').value);

            if (codes.length === 0) { this.toast('请至少选择一只股票', 'error'); return; }
            if (startDate > endDate) { this.toast('开始日期不能晚于结束日期', 'error'); return; }
            if (cash <= 0) { this.toast('初始资金必须大于 0', 'error'); return; }

            const btn = document.getElementById('bt-run-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="skeleton-pulse" style="display:inline-block;width:1em;height:1em;border-radius:50%;vertical-align:middle;margin-right:4px"></span>运行中...';
            // 显示取消按钮
            let cancelBtn = document.getElementById('bt-cancel-btn');
            if (!cancelBtn) {
                cancelBtn = document.createElement('button');
                cancelBtn.id = 'bt-cancel-btn';
                cancelBtn.className = 'btn btn-sm btn-danger';
                cancelBtn.textContent = '取消回测';
                cancelBtn.style.marginLeft = '8px';
                btn.parentElement.appendChild(cancelBtn);
            }
            cancelBtn.style.display = '';
            cancelBtn.disabled = false;
            document.getElementById('bt-results').style.display = 'none';
            this._showProgress(0, '');

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: codes,
                start_date: startDate, end_date: endDate,
                initial_cash: cash,
                commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                benchmark: document.getElementById('bt-benchmark').value || '',
                enable_risk: document.getElementById('bt-risk').value === 'true',
                period: document.getElementById('bt-period').value || 'daily',
                params: this._collectStrategyParams(),
            };

            try {
                const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                const rawUrl = `${proto}//${location.host}/api/backtest/ws/run`;
                const url = (typeof App !== 'undefined' && App.withAPIKey) ? App.withAPIKey(rawUrl) : rawUrl;
                const ws = new WebSocket(url);
                this._btWs = ws;

                const result = await new Promise((resolve, reject) => {
                    ws.onopen = () => ws.send(JSON.stringify(body));
                    // 取消按钮事件
                    cancelBtn.onclick = () => {
                        try { ws.send(JSON.stringify({ type: 'cancel' })); } catch (e) { /* ignore */ }
                        cancelBtn.disabled = true;
                        cancelBtn.textContent = '取消中...';
                    };
                    ws.onmessage = (evt) => {
                        const msg = JSON.parse(evt.data);
                        if (msg.type === 'progress') {
                            this._showProgress(msg.progress, msg.current_date, msg.elapsed, msg.remaining);
                        } else if (msg.type === 'warning') {
                            this.toast(msg.message, 'warning');
                        } else if (msg.type === 'complete') {
                            resolve(msg.data);
                        } else if (msg.type === 'cancelled') {
                            reject(new Error('cancelled'));
                        } else if (msg.type === 'error') {
                            reject(new Error(msg.message));
                        }
                    };
                    ws.onerror = () => reject(new Error('WebSocket连接失败'));
                    ws.onclose = (evt) => {
                        if (!evt.wasClean) reject(new Error('连接中断'));
                    };
                    setTimeout(() => {
                        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                            ws.close();
                            reject(new Error('回测超时'));
                        }
                    }, 300000);
                });

                this._clearBacktestSnapshot();
                this.showBacktestResults(result, body);
                this.toast('回测完成', 'success');
                this.compareStrategies();
            } catch (err) {
                if (err.message === 'cancelled') {
                    this.toast('回测已取消', 'info');
                } else {
                    this.toast('回测失败: ' + err.message, 'error');
                }
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
                const cancelBtn = document.getElementById('bt-cancel-btn');
                if (cancelBtn) cancelBtn.style.display = 'none';
                this._hideProgress();
                if (this._btWs) {
                    try { this._btWs.close(); } catch (e) { /* ignore */ }
                    this._btWs = null;
                }
            }
        });
    },

    _showProgress(progress, currentDate, elapsed, remaining) {
        let bar = document.getElementById('bt-progress-wrap');
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'bt-progress-wrap';
            bar.className = 'bt-progress';
            bar.innerHTML = '<div class="bt-progress-bar"><div class="bt-progress-fill" id="bt-progress-fill"></div></div><div class="bt-progress-text" id="bt-progress-text"></div>';
            const form = document.getElementById('backtest-form');
            if (form) form.parentNode.insertBefore(bar, form.nextSibling);
        }
        bar.style.display = '';
        const fill = document.getElementById('bt-progress-fill');
        const text = document.getElementById('bt-progress-text');
        if (fill) fill.style.width = (progress * 100).toFixed(1) + '%';
        if (text) {
            let info = (progress * 100).toFixed(1) + '%';
            if (currentDate) info += ' · ' + currentDate;
            if (elapsed != null) info += ' · 已用' + elapsed + 's';
            if (remaining != null && remaining > 0) info += ' · 剩余约' + remaining + 's';
            text.textContent = info;
        }
    },

    _hideProgress() {
        const bar = document.getElementById('bt-progress-wrap');
        if (bar) bar.style.display = 'none';
    },

    showBacktestResults(data, reqBody) {
        if (data.error) {
            this._clearBacktestSnapshot();
            this.toast(data.error, 'error');
            document.getElementById('bt-results').style.display = 'none';
            return;
        }

        const safe = (v, d = 0) => v != null ? v : d;
        document.getElementById('bt-results').style.display = '';

        // 显示预热期信息
        const warmupDays = data.warmup_days || 0;
        const warmupInfo = document.getElementById('bt-warmup-info');
        const period = data.period || reqBody?.period || 'daily';
        const periodLabels = {'daily':'日线','1m':'1分钟','5m':'5分钟','15m':'15分钟','30m':'30分钟','60m':'60分钟'};
        if (warmupInfo) {
            const parts = [];
            if (warmupDays > 0) parts.push(`预热期: ${warmupDays} 个周期`);
            if (period !== 'daily') parts.push(`K线周期: ${periodLabels[period] || period}`);
            if (parts.length > 0) {
                warmupInfo.textContent = parts.join(' | ');
                warmupInfo.style.display = '';
            } else {
                warmupInfo.style.display = 'none';
            }
        }

        document.getElementById('bt-return').textContent = (safe(data.total_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-annual').textContent = (safe(data.annual_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-dd').textContent = (safe(data.max_drawdown) * 100).toFixed(2) + '%';
        document.getElementById('bt-sharpe').textContent = safe(data.sharpe_ratio);
        document.getElementById('bt-sortino').textContent = safe(data.sortino_ratio);
        document.getElementById('bt-calmar').textContent = safe(data.calmar_ratio);
        document.getElementById('bt-info-ratio').textContent = safe(data.information_ratio);
        document.getElementById('bt-alpha').textContent = safe(data.alpha);
        document.getElementById('bt-beta').textContent = safe(data.beta);
        document.getElementById('bt-winrate').textContent = (safe(data.win_rate) * 100).toFixed(1) + '%';
        document.getElementById('bt-pl-ratio').textContent = safe(data.profit_loss_ratio);
        document.getElementById('bt-max-win-streak').textContent = safe(data.max_consecutive_wins);
        document.getElementById('bt-max-loss-streak').textContent = safe(data.max_consecutive_losses);
        document.getElementById('bt-trades').textContent = safe(data.total_trades);

        this._lastBacktestData = data;
        this._lastBacktestBody = reqBody;
        this._setBacktestDiagnoseEnabled(true);

        const curve = data.equity_curve || [];
        const benchmarkCurve = data.benchmark_curve || [];
        if (curve.length > 0) {
            // 使用 datetime（如果有）或 date 作为标签
            const labels = curve.map(p => p.datetime || p.date);
            const datasets = [{ data: curve.map(p => p.equity), fill: true, label: '策略收益' }];
            if (benchmarkCurve.length > 0) {
                const bmMap = {};
                benchmarkCurve.forEach(p => { bmMap[p.date] = p.equity; });
                const bmData = curve.map(p => bmMap[p.date] != null ? bmMap[p.date] * (curve[0]?.equity || 1) : null);
                datasets.push({
                    data: bmData,
                    fill: false,
                    label: '基准',
                    borderDash: [5, 5],
                    borderColor: 'rgba(255,152,0,0.8)',
                    backgroundColor: 'transparent',
                    pointRadius: 0,
                });
            }
            ChartFactory.line('bt-equity-chart', {
                labels,
                datasets,
            }, 'equity');
        }

        const trades = data.trades || [];
        const tbody = document.querySelector('#bt-trades-table tbody');
        if (trades.length > 0) {
            tbody.innerHTML = trades.map(t => `
                <tr><td>${this.escapeHTML(t.datetime) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.escapeHTML(t.entry_price) || '--'}</td></tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">无交易记录</td></tr>';
        }

        const alerts = data.risk_alerts || [];
        if (alerts.length > 0) {
            document.getElementById('bt-alerts-card').style.display = '';
            document.querySelector('#bt-alerts-table tbody').innerHTML = alerts.map(a => `
                <tr><td>${this.escapeHTML(a.date)}</td><td><span class="badge badge-${a.level === 'critical' ? 'danger' : 'warning'}">${this.escapeHTML(a.level)}</span></td><td>${this.escapeHTML(a.category)}</td><td>${this.escapeHTML(a.message)}</td></tr>
            `).join('');
        } else {
            document.getElementById('bt-alerts-card').style.display = 'none';
        }

        if (reqBody) this.loadBacktestCharts(reqBody);
    },


});
