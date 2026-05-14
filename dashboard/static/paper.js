/* ── 模拟盘控制 ── */

const Paper = {
    _inited: false,
    _controlsBound: false,

    init() {
        if (this._inited) return;
        this._inited = true;
        this._bindControls();
        if (typeof PaperTrading !== 'undefined' && PaperTrading.init) {
            PaperTrading.init();
        }
    },

    _bindControls() {
        if (this._controlsBound) return;
        this._controlsBound = true;

        const startBtn = document.getElementById('pp-start-btn');
        if (startBtn) {
            startBtn.removeAttribute('onclick');
            startBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.start();
            });
        }

        const stopBtn = document.getElementById('pp-stop-btn');
        if (stopBtn) {
            stopBtn.removeAttribute('onclick');
            stopBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.stop();
            });
        }

        const panel = document.getElementById('paper-panel-console');
        const resetBtn = panel
            ? [...panel.querySelectorAll('.flex-center > button.btn')].find(btn => btn.textContent.trim() === '重置') || null
            : null;
        if (resetBtn) {
            resetBtn.removeAttribute('onclick');
            resetBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.reset();
            });
        }

        const trainBtn = document.getElementById('pp-train-btn');
        if (trainBtn) {
            trainBtn.removeAttribute('onclick');
            trainBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.trainQlib();
            });
        }
    },

    async start() {
        // 优先从多选搜索框获取，兼容旧的文本输入
        let codes = [];
        if (App.paperMultiSearch) {
            codes = App.paperMultiSearch.getSelectedCodes();
        }
        if (codes.length === 0) { App.toast('请选择至少一只股票', 'error'); return; }

        // 收集策略参数
        const params = {};
        document.querySelectorAll('.pp-param-input').forEach(el => {
            const name = el.dataset.param;
            const val = parseFloat(el.value);
            if (name && !isNaN(val)) params[name] = val;
        });

        const body = {
            strategy: document.getElementById('pp-strategy').value,
            codes,
            interval: parseInt(document.getElementById('pp-interval').value, 10) || 30,
            cash: parseFloat(document.getElementById('pp-cash').value) || 50000,
            enable_risk: document.getElementById('pp-risk').value === 'true',
            params: Object.keys(params).length > 0 ? params : null,
        };

        const btn = document.getElementById('pp-start-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="skeleton-pulse" style="display:inline-block;width:1em;height:1em;border-radius:50%;vertical-align:middle;margin-right:4px"></span>启动中...'; }

        try {
            await App.fetchJSON('/api/paper/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                label: '启动模拟盘',
            });
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
            await App.fetchJSON('/api/paper/stop', { method: 'POST', label: '停止模拟盘' });
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
            await App.fetchJSON('/api/paper/reset', { method: 'POST', label: '重置模拟盘' });
            App.toast('模拟盘已重置', 'success');
            this._stopPolling();
            this.loadStatus();
            PaperTrading.refreshAll();
        } catch (e) {
            App.toast('重置失败: ' + e.message, 'error');
        }
    },

    async trainQlib() {
        if (!confirm('开始训练 qlib ML 模型？\n这需要几分钟时间，训练期间不影响其他功能。')) return;
        const btn = document.getElementById('pp-train-btn');
        try {
            if (btn) { btn.disabled = true; btn.textContent = '训练中...'; }
            const data = await App.fetchJSON('/api/qlib/train', { method: 'POST' });
            if (data.success) {
                App.toast('qlib 训练已启动，请稍后查看预测结果', 'success');
                // 轮询训练状态
                this._pollTrainStatus();
            } else {
                App.toast(data.message || '训练启动失败', 'error');
            }
        } catch (e) {
            App.toast('训练请求失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '训练ML'; }
        }
    },

    async _pollTrainStatus() {
        const check = async () => {
            try {
                const data = await App.fetchJSON('/api/qlib/train/status');
                if (data.training) {
                    setTimeout(check, 10000);
                } else {
                    App.toast('qlib 训练完成！', 'success');
                }
            } catch { /* ignore */ }
        };
        setTimeout(check, 10000);
    },

    async loadStatus() {
        // 委托给 PaperTrading 模块统一管理状态渲染
        if (typeof PaperTrading !== 'undefined' && PaperTrading.loadStatus) {
            await PaperTrading.loadStatus();
            // 同步启动/停止按钮状态
            const startBtn = document.getElementById('pp-start-btn');
            const stopBtn = document.getElementById('pp-stop-btn');
            if (startBtn) startBtn.disabled = PaperTrading.state.isRunning;
            if (stopBtn) stopBtn.disabled = !PaperTrading.state.isRunning;
        }
    },

    _startPolling() {
        // PaperTrading 模块已管理轮询，此处仅确保其启动
        if (typeof PaperTrading !== 'undefined' && PaperTrading.startPolling) {
            PaperTrading.startPolling();
        }
    },

    _stopPolling() {
        if (typeof PaperTrading !== 'undefined' && PaperTrading.stopPolling) {
            PaperTrading.stopPolling();
        }
    },
};
