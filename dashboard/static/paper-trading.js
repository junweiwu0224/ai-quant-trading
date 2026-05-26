/* ── 模拟盘完整功能 ── */

const PaperTrading = {
    // ────────────── 状态 ──────────────
    state: {
        isRunning: false,
        config: {},
        positions: [],
        orders: [],
        trades: [],
        performance: {},
        equityCurve: [],
        riskEvents: [],
    },

    // ────────────── 图表实例 ──────────────
    charts: {
        equityCurve: null,
        monthlyHeatmap: null,
        returnDist: null,
        weekdayEffect: null,
        positionPie: null,
        dailyReturns: null,
    },

    // ────────────── 股票名称缓存 ──────────────
    _stockNameCache: {},
    _delegatedActionsBound: false,
    _historyControlsBound: false,

    // ────────────── 轮询管理 ──────────────
    polling: {
        status: { interval: 5000, timer: null },
        positions: { interval: 10000, timer: null },
        orders: { interval: 3000, timer: null },
        equity: { interval: 30000, timer: null },
    },

    // ────────────── 初始化 ──────────────
    _loaded: false,

    init() {
        this.bindEvents();
        this.bindActionDelegation();
        this.bindHistoryControls();
        this.initSubTabs();
        this.loadStrategyList();
        if (!this._loaded) this._showSkeletons();
        this.loadStatus();
        this.loadPositions();
        this.loadOrders();
        this.loadPerformance();
        this.loadEquityCurve();
        this.loadTrades();
        this.loadRiskEvents();
        this.loadDailyReturns();
        this.startPolling();
    },

    // ────────────── 子 Tab 切换 ──────────────
    initSubTabs() {
        document.querySelectorAll('#paper-sub-tabs .paper-sub-tab').forEach(btn => {
            btn.addEventListener('click', () => this.switchSubTab(btn.dataset.tab));
        });
    },

    switchSubTab(tabName) {
        // 更新 Tab 按钮状态
        document.querySelectorAll('#paper-sub-tabs .paper-sub-tab').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
        });
        // 更新面板显示
        document.querySelectorAll('#paper-sub-panels .paper-sub-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== `paper-panel-${tabName}`);
        });
        // 切换到对应 Tab 时加载数据
        if (tabName === 'perf') {
            this.loadDailyReturns();
            this.loadMonthlyHeatmap();
            this.loadReturnDistribution();
            this.loadWeekdayEffect();
            this.loadPerformanceTrend();
            this.loadTradeFrequency();
        } else if (tabName === 'trade') {
            this.loadTrades();
        } else if (tabName === 'history') {
            this.loadTrades();
            this.loadRiskEvents();
        }
    },

    // ────────────── 动态策略列表 ──────────────
    async loadStrategyList() {
        try {
            const data = await App.fetchJSON('/api/strategy/list');
            const strategies = data.data || data || [];
            const select = document.getElementById('pp-strategy');
            if (!select || !Array.isArray(strategies)) return;

            // 保留当前选中值
            const currentValue = select.value;

            // 清空并重新填充
            select.innerHTML = '';
            strategies.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.name || s.id;
                opt.textContent = s.label || s.display_name || s.name || s.id;
                select.appendChild(opt);
            });

            // 恢复选中状态
            if (currentValue && select.querySelector(`option[value="${currentValue}"]`)) {
                select.value = currentValue;
            }

            // 如果没有策略，添加默认选项
            if (strategies.length === 0) {
                select.innerHTML = `
                    <option value="dual_ma">双均线策略</option>
                    <option value="bollinger">布林带策略</option>
                    <option value="momentum">动量策略</option>
                `;
            }
        } catch (e) {
            console.warn('加载策略列表失败，使用默认策略:', e);
            // 保持默认策略列表
        }
    },

    _showSkeletons() {
        document.querySelectorAll('#tab-paper .stat-value').forEach(el => {
            el.classList.add('skeleton-text');
        });
    },

    _hideSkeletons() {
        document.querySelectorAll('#tab-paper .stat-value.skeleton-text').forEach(el => {
            el.classList.remove('skeleton-text');
        });
    },

    _showChartEmpty(canvas, message = '暂无数据') {
        if (!canvas) return;
        const wrap = canvas.parentElement;
        if (!wrap) return;
        let overlay = wrap.querySelector('.chart-empty-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'chart-empty-overlay';
            overlay.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--color-text-muted,#9ca3af);font-size:0.875rem;pointer-events:none;z-index:1;';
            wrap.style.position = 'relative';
            wrap.appendChild(overlay);
        }
        overlay.textContent = message;
        overlay.style.display = 'flex';
    },

    _hideChartEmpty(canvas) {
        if (!canvas) return;
        const wrap = canvas.parentElement;
        if (!wrap) return;
        const overlay = wrap.querySelector('.chart-empty-overlay');
        if (overlay) overlay.style.display = 'none';
    },

    bindEvents() {
        // 订单表单提交
        const orderForm = document.getElementById('pt-order-form');
        if (orderForm) {
            orderForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createOrder();
            });
        }

        // 订单类型切换
        const orderTypeSelect = document.getElementById('pt-order-type');
        if (orderTypeSelect) {
            orderTypeSelect.addEventListener('change', () => {
                this.togglePriceInput();
            });
        }

        // 快捷数量按钮
        document.querySelectorAll('.pt-qty-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const qty = parseInt(btn.dataset.qty);
                document.getElementById('pt-volume').value = qty;
            });
        });

        // 刷新按钮
        document.getElementById('pt-refresh-btn')?.addEventListener('click', () => {
            this.refreshAll();
        });

        // 股票代码输入 - 搜索下拉 + 实时行情预览
        const codeInput = document.getElementById('pt-code');
        const codeDropdown = document.getElementById('pt-code-dropdown');
        if (codeInput && codeDropdown) {
            this._codeSearch = new SearchBox('pt-code', 'pt-code-dropdown', {
                placeholder: '搜索股票代码或名称...',
                formatItem: (s) => `${s.code} ${s.name}`,
                maxResults: 15,
            });
            // 数据源：全市场股票（与Console子Tab一致）
            const fullMarketSource = (query) => {
                const list = App._allStocks || [];
                if (!query) return list.slice(0, 50).map(s => ({ code: s.code, name: s.name || s.code }));
                const q = query.toLowerCase();
                return list.filter(s =>
                    (s.code && s.code.includes(q)) || (s.name && s.name.toLowerCase().includes(q))
                ).slice(0, 50).map(s => ({ code: s.code, name: s.name || s.code }));
            };
            this._codeSearch.setDataSource(fullMarketSource);
            this._codeSearch.onSelect((item) => {
                codeInput.value = item.code;
                this._loadQuotePreview(item.code);
                this._updateEstimatedCost();
            });
            // 保留手动输入时的行情预览
            let debounceTimer = null;
            codeInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => this._loadQuotePreview(codeInput.value.trim()), 300);
            });
        }

        // P1 #4: 数量/价格变化时更新预估花费
        const volumeInput = document.getElementById('pt-volume');
        const priceInput = document.getElementById('pt-price');
        const updateEstCost = () => this._updateEstimatedCost();
        if (volumeInput) volumeInput.addEventListener('input', updateEstCost);
        if (priceInput) priceInput.addEventListener('input', updateEstCost);
    },

    bindActionDelegation() {
        if (this._delegatedActionsBound) {
            return;
        }

        this._delegatedActionsBound = true;
        document.addEventListener('click', (e) => {
            const button = e.target.closest('[data-paper-action]');
            if (!button) {
                return;
            }

            const action = button.dataset.paperAction;
            e.preventDefault();

            if (action === 'cancel-order') {
                const orderId = typeof button.dataset.orderId === 'string' ? button.dataset.orderId.trim() : '';
                if (orderId) {
                    this.cancelOrder(orderId);
                }
                return;
            }

            if (action === 'partial-close') {
                const code = typeof button.dataset.code === 'string' ? button.dataset.code.trim() : '';
                if (code) {
                    this.partialClose(code);
                }
                return;
            }

            if (action === 'close-position') {
                const code = typeof button.dataset.code === 'string' ? button.dataset.code.trim() : '';
                if (code) {
                    this.closePosition(code);
                }
                return;
            }

            if (action === 'load-trades-page') {
                const page = parseInt(button.dataset.page || '', 10);
                if (Number.isFinite(page) && page > 0) {
                    this.loadTrades(page);
                }
                return;
            }

            if (action === 'export-trades') {
                const format = button.dataset.format === 'json' ? 'json' : 'csv';
                this.exportTrades(format);
            }
        });

        document.addEventListener('change', (e) => {
            const input = e.target.closest('[data-paper-action="update-stop-loss"]');
            if (!input) {
                return;
            }

            const code = typeof input.dataset.code === 'string' ? input.dataset.code.trim() : '';
            const type = typeof input.dataset.stopType === 'string' ? input.dataset.stopType.trim() : '';
            if (!code || !type) {
                return;
            }

            this.updateStopLoss(code, input.value, type);
        });
    },

    bindHistoryControls() {
        if (this._historyControlsBound) {
            return;
        }

        this._historyControlsBound = true;

        const closeAllBtn = document.getElementById('pt-close-all-btn');
        if (closeAllBtn) {
            closeAllBtn.removeAttribute('onclick');
            closeAllBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.closeAllPositions();
            });
        }

        const filterCodeInput = document.getElementById('pt-filter-code');
        if (filterCodeInput) {
            filterCodeInput.removeAttribute('oninput');
            filterCodeInput.addEventListener('input', () => {
                this.onTradeFilterChange();
            });
        }

        const filterDirectionSelect = document.getElementById('pt-filter-direction');
        if (filterDirectionSelect) {
            filterDirectionSelect.removeAttribute('onchange');
            filterDirectionSelect.addEventListener('change', () => {
                this.onTradeFilterChange();
            });
        }
    },

    _updateEstimatedCost() {
        const estEl = document.getElementById('pt-est-cost');
        if (!estEl) return;
        const volume = parseInt(document.getElementById('pt-volume')?.value) || 0;
        const priceInput = document.getElementById('pt-price')?.value;
        const orderType = document.getElementById('pt-order-type')?.value;
        // 市价单用行情价，限价单用输入价
        const price = (orderType !== 'market' && priceInput) ? parseFloat(priceInput) : (this._currentQuote?.price || 0);
        if (volume > 0 && price > 0) {
            const cost = volume * price;
            estEl.style.display = '';
            estEl.querySelector('span').textContent = App.fmt(cost);
        } else {
            estEl.style.display = 'none';
        }
    },

    // ────────────── 实时行情预览 ──────────────
    async _loadQuotePreview(code) {
        const preview = document.getElementById('pt-quote-preview');
        if (!preview) return;

        if (!code || code.length < 6) {
            preview.classList.add('hidden');
            return;
        }

        try {
            const data = await App.fetchJSON(`/api/stock/detail/${code}`);
            if (!data || !data.name) {
                preview.classList.add('hidden');
                return;
            }

            const quote = data;
            const price = quote.current_price || quote.price;
            const change = quote.change_pct || 0;
            const changeClass = change >= 0 ? 'text-up' : 'text-down';
            const changeSign = change >= 0 ? '+' : '';

            // 保存当前行情供下单校验
            this._currentQuote = { price, name: quote.name, code };

            document.getElementById('pt-quote-name').textContent = quote.name || '--';
            document.getElementById('pt-quote-code').textContent = code;
            document.getElementById('pt-quote-price').textContent = price ? `¥${price.toFixed(2)}` : '--';
            document.getElementById('pt-quote-price').className = change >= 0 ? 'text-up' : 'text-down';
            document.getElementById('pt-quote-change').textContent = change ? `${changeSign}${change.toFixed(2)}%` : '--';
            document.getElementById('pt-quote-change').className = changeClass;
            document.getElementById('pt-quote-high').textContent = quote.high ? `¥${quote.high.toFixed(2)}` : '--';
            document.getElementById('pt-quote-low').textContent = quote.low ? `¥${quote.low.toFixed(2)}` : '--';
            document.getElementById('pt-quote-volume').textContent = quote.volume ? this._formatVolume(quote.volume) : '--';

            preview.classList.remove('hidden');
        } catch (e) {
            preview.classList.add('hidden');
        }
    },

    _formatVolume(vol) {
        if (vol >= 100000000) return (vol / 100000000).toFixed(2) + '亿';
        if (vol >= 10000) return (vol / 10000).toFixed(2) + '万';
        return vol.toString();
    },

    // 订单/持仓/风控操作拆到 paper-trading-trade.js / paper-trading-position.js
    // Charts, history, status, and polling moved to paper-trading-performance.js
};

globalThis.PaperTrading = PaperTrading;
