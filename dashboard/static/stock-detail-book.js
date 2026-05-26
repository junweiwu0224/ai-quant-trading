/* ── 股票详情页：盘口 / L2 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadOrderBook(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/order-book/${code}`);
            if (!data || stale()) return;
            this._renderOrderBook(data.asks, data.bids);
        } catch (e) {
            console.error('加载盘口失败:', e);
        }
    },

    // ── L2 十档行情 ──

    setOrderBookLevels(levels) {
        this._l2Levels = levels;
        // 更新按钮状态
        document.querySelectorAll('.sd-ob-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.levels) === levels);
        });
        // 重新渲染
        if (this._l2Data) {
            this._renderL2OrderBook(this._l2Data);
        }
    },

    _connectL2(code) {
        this._disconnectL2();
        if (!code) return;

        try {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const rawUrl = `${proto}//${location.host}/ws/l2`;
            const url = (typeof App !== 'undefined' && App.withAPIKey) ? App.withAPIKey(rawUrl) : rawUrl;
            const ws = new WebSocket(url);
            this._l2Ws = ws;

            ws.onopen = () => {
                this._l2RetryCount = 0;
                ws.send(JSON.stringify({ action: 'subscribe', code }));
                const badge = document.getElementById('sd-ob-source');
                if (badge) { badge.textContent = 'L2'; badge.title = 'L2 十档行情（模拟）'; }
            };

            ws.onmessage = (evt) => {
                try {
                    const msg = JSON.parse(evt.data);
                    if (msg.type === 'l2' && msg.data) {
                        this._l2Data = msg.data;
                        this._renderL2OrderBook(msg.data);
                    }
                } catch (e) { /* ignore */ }
            };

            ws.onclose = () => {
                const badge = document.getElementById('sd-ob-source');
                if (badge) { badge.textContent = 'L1'; badge.title = 'L1 五档行情'; }
                // 断线重连（指数退避，最多 3 次）
                if (this._currentCode === code && (this._l2RetryCount || 0) < 3) {
                    const delay = Math.min(1000 * Math.pow(2, this._l2RetryCount || 0), 8000);
                    this._l2RetryCount = (this._l2RetryCount || 0) + 1;
                    this._l2ReconnectTimer = setTimeout(() => {
                        this._l2ReconnectTimer = null;
                        this._connectL2(code);
                    }, delay);
                }
            };
        } catch (e) {
            console.warn('L2 WebSocket 连接失败:', e);
        }
    },

    _disconnectL2() {
        if (this._l2ReconnectTimer) {
            clearTimeout(this._l2ReconnectTimer);
            this._l2ReconnectTimer = null;
        }
        if (this._l2Ws) {
            try { this._l2Ws.close(); } catch (e) { /* ignore */ }
            this._l2Ws = null;
        }
        this._l2Data = null;
        const badge = document.getElementById('sd-ob-source');
        if (badge) { badge.textContent = 'L1'; badge.title = 'L1 五档行情'; }
    },

    _renderL2OrderBook(data) {
        const asksEl = document.getElementById('sd-asks');
        const bidsEl = document.getElementById('sd-bids');
        if (!asksEl || !bidsEl || !data) return;

        const levels = this._l2Levels;
        const asks = (data.asks || []).slice(0, levels);
        const bids = (data.bids || []).slice(0, levels);

        // 价差显示
        const spreadEl = document.getElementById('sd-ob-spread');
        if (spreadEl && asks.length > 0 && bids.length > 0) {
            const spread = (asks[0].price - bids[0].price).toFixed(2);
            const midPrice = ((asks[0].price + bids[0].price) / 2).toFixed(2);
            const spreadPct = bids[0].price > 0
                ? ((asks[0].price - bids[0].price) / bids[0].price * 100).toFixed(3)
                : '0';
            spreadEl.innerHTML = `<span>价差 ${spread} (${spreadPct}%)</span><span>中间价 ${midPrice}</span>`;
        }

        // 卖盘（从高到低显示，所以反转）
        const asksReversed = [...asks].reverse();
        asksEl.innerHTML = '<div class="sd-ob-title">卖盘</div>' +
            asksReversed.map((a, i) => {
                const level = levels - i;
                return `<div class="sd-ob-row ask">
                    <span class="sd-ob-level">卖${level}</span>
                    <span class="sd-ob-price">${a.price ? a.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${a.volume || '--'}</span>
                    ${levels > 5 ? `<span class="sd-ob-orders">${a.orders || ''}</span>` : ''}
                </div>`;
            }).join('');

        // 买盘
        bidsEl.innerHTML = '<div class="sd-ob-title">买盘</div>' +
            bids.map((b, i) => {
                return `<div class="sd-ob-row bid">
                    <span class="sd-ob-level">买${i + 1}</span>
                    <span class="sd-ob-price">${b.price ? b.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${b.volume || '--'}</span>
                    ${levels > 5 ? `<span class="sd-ob-orders">${b.orders || ''}</span>` : ''}
                </div>`;
            }).join('');
    },

    _renderOrderBook(asks, bids) {
        // 如果有 L2 数据，使用 L2 渲染
        if (this._l2Data && this._l2Levels > 5) {
            this._renderL2OrderBook(this._l2Data);
            return;
        }

        const asksEl = document.getElementById('sd-asks');
        const bidsEl = document.getElementById('sd-bids');
        if (!asksEl || !bidsEl) return;

        // 检查是否有有效数据（非交易时段API返回全0）
        const hasData = asks.some(a => a.price > 0) || bids.some(b => b.price > 0);
        if (!hasData) {
            asksEl.innerHTML = '<div class="sd-ob-title">卖盘</div><div class="sd-ob-empty">非交易时段</div>';
            bidsEl.innerHTML = '<div class="sd-ob-title">买盘</div><div class="sd-ob-empty">非交易时段</div>';
            return;
        }

        const spreadEl = document.getElementById('sd-ob-spread');
        if (spreadEl && asks.length > 0 && bids.length > 0 && asks[0].price > 0 && bids[0].price > 0) {
            const spread = (asks[0].price - bids[0].price).toFixed(2);
            spreadEl.innerHTML = `<span>价差 ${spread}</span>`;
        }

        const asksReversed = [...asks].reverse();
        asksEl.innerHTML = '<div class="sd-ob-title">卖盘</div>' +
            asksReversed.map((a, i) => {
                const level = 5 - i;
                return `<div class="sd-ob-row ask">
                    <span class="sd-ob-level">卖${level}</span>
                    <span class="sd-ob-price">${a.price ? a.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${a.volume || '--'}</span>
                </div>`;
            }).join('');

        bidsEl.innerHTML = '<div class="sd-ob-title">买盘</div>' +
            bids.map((b, i) => {
                return `<div class="sd-ob-row bid">
                    <span class="sd-ob-level">买${i + 1}</span>
                    <span class="sd-ob-price">${b.price ? b.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${b.volume || '--'}</span>
                </div>`;
            }).join('');
    },

    _chartTabsBound: false,

});
