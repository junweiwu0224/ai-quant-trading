/* ── 实时行情 WebSocket 客户端 ── */

const RealtimeQuotes = {
    _ws: null,
    _reconnectTimer: null,
    _quotes: {},
    _listeners: [],
    _subscribed: false,
    _reconnectAttempts: 0,

    connect() {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) return;

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws/quotes`;

        try {
            this._ws = new WebSocket(url);
        } catch (e) {
            console.warn('WebSocket 连接失败:', e);
            this._scheduleReconnect();
            return;
        }

        this._ws.onopen = () => {
            clearTimeout(this._reconnectTimer);
            this._reconnectAttempts = 0;
            // 自动订阅自选股
            this._subscribeWatchlist();
        };

        this._ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                this._handleMessage(msg);
            } catch (err) {
                console.warn('WebSocket 消息解析失败:', err);
            }
        };

        this._ws.onclose = () => {
            this._scheduleReconnect();
        };

        this._ws.onerror = (e) => {
            console.warn('WebSocket 错误:', e);
        };
    },

    disconnect() {
        clearTimeout(this._reconnectTimer);
        if (this._ws) {
            this._ws.close();
            this._ws = null;
        }
    },

    _scheduleReconnect() {
        clearTimeout(this._reconnectTimer);
        const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
        this._reconnectAttempts++;
        this._reconnectTimer = setTimeout(() => this.connect(), delay);
    },

    _handleMessage(msg) {
        switch (msg.type) {
            case 'quotes':
                Object.assign(this._quotes, msg.data);
                this._notifyListeners(msg.data);
                break;
            case 'status':
                this._notifyListeners({ _status: msg });
                break;
            case 'alerts':
                // 预警触发消息
                if (msg.data && Array.isArray(msg.data)) {
                    for (const alert of msg.data) {
                        if (typeof App !== 'undefined' && App.Alerts && App.Alerts.handleAlert) {
                            App.Alerts.handleAlert(alert);
                        }
                    }
                }
                break;
            case 'pong':
                break;
            case 'subscribed':
            case 'unsubscribed':
                break;
        }
    },

    _subscribeWatchlist() {
        // 每次连接都重新订阅（防止重连后丢失订阅）
        App.fetchJSON('/api/watchlist', { silent: true })
            .then(list => {
                const codes = (Array.isArray(list) ? list : []).map(s => s.code);
                if (codes.length > 0 && this._ws && this._ws.readyState === WebSocket.OPEN) {
                    this._ws.send(JSON.stringify({ action: 'subscribe', codes }));
                }
            })
            .catch(() => {});
    },

    subscribe(codes) {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify({ action: 'subscribe', codes }));
        }
    },

    unsubscribe(codes) {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify({ action: 'unsubscribe', codes }));
        }
    },

    getQuote(code) {
        return this._quotes[code] || null;
    },

    getAllQuotes() {
        return { ...this._quotes };
    },

    onUpdate(callback) {
        this._listeners.push(callback);
    },

    _notifyListeners(data) {
        for (const cb of this._listeners) {
            try { cb(data); } catch (e) { console.warn('行情回调异常:', e); }
        }
    },

    getStatus() {
        if (!this._ws) return 'disconnected';
        switch (this._ws.readyState) {
            case WebSocket.CONNECTING: return 'connecting';
            case WebSocket.OPEN: return 'connected';
            case WebSocket.CLOSING: return 'closing';
            case WebSocket.CLOSED: return 'closed';
            default: return 'unknown';
        }
    },
};
