/* ── 模拟盘控制 ── */

const Paper = {
    _pollInterval: null,

    async start() {
        // 优先从多选搜索框获取，兼容旧的文本输入
        let codes = [];
        if (App.paperMultiSearch) {
            codes = App.paperMultiSearch.getSelectedCodes();
        }
        if (codes.length === 0) {
            const codesRaw = document.getElementById('pp-codes').value.trim();
            if (codesRaw) codes = codesRaw.split(/[,，\s]+/).filter(Boolean);
        }
        if (codes.length === 0) { App.toast('请选择至少一只股票', 'error'); return; }

        const body = {
            strategy: document.getElementById('pp-strategy').value,
            codes,
            interval: parseInt(document.getElementById('pp-interval').value, 10) || 30,
            cash: parseFloat(document.getElementById('pp-cash').value) || 1000000,
            enable_risk: document.getElementById('pp-risk').value === 'true',
        };

        const btn = document.getElementById('pp-start-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>启动中...'; }

        try {
            const res = await fetch('/api/paper/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            App.toast('模拟盘已启动', 'success');
            this._startPolling();
            this.loadStatus();
        } catch (e) {
            App.toast('启动失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '启动'; }
        }
    },

    async stop() {
        try {
            const res = await fetch('/api/paper/stop', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            App.toast('模拟盘已停止', 'success');
            this._stopPolling();
            this.loadStatus();
        } catch (e) {
            App.toast('停止失败: ' + e.message, 'error');
        }
    },

    async reset() {
        if (!confirm('确定重置模拟盘？将清空所有持仓和交易记录。')) return;
        try {
            const res = await fetch('/api/paper/reset', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            App.toast('模拟盘已重置', 'success');
            this._stopPolling();
            this.loadStatus();
        } catch (e) {
            App.toast('重置失败: ' + e.message, 'error');
        }
    },

    async loadStatus() {
        try {
            const data = await App.fetchJSON('/api/paper/status');
            const statusEl = document.getElementById('pp-status');
            const equityEl = document.getElementById('pp-equity');
            const posCountEl = document.getElementById('pp-pos-count');
            const tradeCountEl = document.getElementById('pp-trade-count');
            const startBtn = document.getElementById('pp-start-btn');
            const stopBtn = document.getElementById('pp-stop-btn');

            if (statusEl) {
                statusEl.textContent = data.running ? '运行中' : '已停止';
                statusEl.className = 'stat-value ' + (data.running ? 'text-success' : '');
            }
            if (equityEl) equityEl.textContent = data.equity != null ? App.fmt(data.equity) : '--';
            if (posCountEl) posCountEl.textContent = Object.keys(data.positions || {}).length;
            if (tradeCountEl) tradeCountEl.textContent = data.trade_count || 0;

            if (startBtn) startBtn.disabled = data.running;
            if (stopBtn) stopBtn.disabled = !data.running;

            if (data.running && !this._pollInterval) {
                this._startPolling();
            } else if (!data.running && this._pollInterval) {
                this._stopPolling();
            }
        } catch (e) {
            // silent
        }
    },

    _startPolling() {
        this._stopPolling();
        this._pollInterval = setInterval(() => this.loadStatus(), 5000);
    },

    _stopPolling() {
        if (this._pollInterval) {
            clearInterval(this._pollInterval);
            this._pollInterval = null;
        }
    },
};
