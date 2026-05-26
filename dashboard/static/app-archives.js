(function attachAppArchives(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        // ── 实验快照系统 ──
        _SNAPSHOT_KEY: 'quant_snapshots',
        _SIM_SNAPSHOT_KEY: 'quant_sim_snapshots',

        /** 保存当前研发页实验状态为快照 */
        saveSnapshot(name) {
            const snapshot = {
                id: Date.now().toString(36),
                name: name || `实验 ${new Date().toLocaleString('zh-CN')}`,
                timestamp: Date.now(),
                data: {},
            };

            const fields = {
                'alpha-code': 'alpha-code', 'alpha-start': 'alpha-start', 'alpha-end': 'alpha-end',
                'bt-code': 'bt-code', 'bt-start': 'bt-start', 'bt-end': 'bt-end', 'bt-cash': 'bt-cash',
                'bt-strategy': 'bt-strategy', 'bt-benchmark': 'bt-benchmark',
                'ensemble-codes': 'ensemble-codes', 'ensemble-start': 'ensemble-start', 'ensemble-end': 'ensemble-end',
                'compare-codes-input': 'compare-codes-input',
            };
            for (const [key, id] of Object.entries(fields)) {
                const el = document.getElementById(id);
                if (el?.value) snapshot.data[key] = el.value;
            }

            const snapshots = this._loadSnapshots();
            snapshots.unshift(snapshot);
            if (snapshots.length > 20) snapshots.length = 20;
            localStorage.setItem(this._SNAPSHOT_KEY, JSON.stringify(snapshots));
            this.toast(`快照已保存: ${snapshot.name}`, 'success');
            return snapshot;
        },

        /** 加载快照到研发页 */
        loadSnapshot(id) {
            const snapshots = this._loadSnapshots();
            const snap = snapshots.find(s => s.id === id);
            if (!snap) { this.toast('快照不存在', 'error'); return; }

            for (const [key, value] of Object.entries(snap.data)) {
                const el = document.getElementById(key);
                if (el) el.value = value;
            }
            this._researchSession = { ...this._researchSession, ...snap.data };
            this.toast(`已加载快照: ${snap.name}`, 'success');
        },

        /** 导出所有快照为 JSON 文件 */
        exportSnapshots() {
            const snapshots = this._loadSnapshots();
            if (snapshots.length === 0) { this.toast('没有可导出的快照', 'info'); return; }

            const blob = new Blob([JSON.stringify(snapshots, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `quant-snapshots-${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
            this.toast('快照已导出', 'success');
        },

        /** 从 JSON 文件导入快照 */
        importSnapshots(file) {
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const imported = JSON.parse(reader.result);
                    if (!Array.isArray(imported)) throw new Error('格式错误');
                    const existing = this._loadSnapshots();
                    const merged = [...imported, ...existing];
                    const unique = merged.filter((s, i, arr) => arr.findIndex(x => x.id === s.id) === i);
                    if (unique.length > 20) unique.length = 20;
                    localStorage.setItem(this._SNAPSHOT_KEY, JSON.stringify(unique));
                    this.toast(`已导入 ${imported.length} 个快照`, 'success');
                } catch (e) {
                    this.toast('导入失败: ' + e.message, 'error');
                }
            };
            reader.readAsText(file);
        },

        _loadSnapshots() {
            try {
                return JSON.parse(localStorage.getItem(this._SNAPSHOT_KEY) || '[]');
            } catch {
                return [];
            }
        },

        /** 保存当前模拟盘绩效快照 */
        saveSimSnapshot() {
            const metrics = {
                id: Date.now().toString(36),
                name: `策略 ${new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`,
                timestamp: Date.now(),
                cumReturn: document.getElementById('pt-cumulative-return')?.textContent || '--',
                maxDD: document.getElementById('pt-max-drawdown')?.textContent || '--',
                sharpe: document.getElementById('pt-sortino-ratio')?.textContent || '--',
                winRate: document.getElementById('pt-win-rate-perf')?.textContent || '--',
            };

            const snapshots = this._loadSimSnapshots();
            snapshots.unshift(metrics);
            if (snapshots.length > 10) snapshots.length = 10;
            localStorage.setItem(this._SIM_SNAPSHOT_KEY, JSON.stringify(snapshots));
            this.renderSimCompare();
            this.toast('模拟盘快照已保存', 'success');
        },

        /** 渲染策略对比表 */
        renderSimCompare() {
            const tbody = document.querySelector('#sim-compare-table tbody');
            if (!tbody) return;
            const snapshots = this._loadSimSnapshots();
            if (snapshots.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无对比数据，点击"保存当前快照"</td></tr>';
                return;
            }
            tbody.innerHTML = snapshots.map(s => {
                const date = new Date(s.timestamp).toLocaleDateString('zh-CN');
                return `<tr>
                <td>${this.escapeHTML(s.name)}</td>
                <td>${date}</td>
                <td>${s.cumReturn}</td>
                <td>${s.maxDD}</td>
                <td>${s.sharpe}</td>
                <td>${s.winRate}</td>
                <td><button class="btn btn-sm" data-app-action="delete-sim-snapshot" data-snapshot-id="${this.escapeHTML(s.id)}">删除</button></td>
            </tr>`;
            }).join('');
        },

        deleteSimSnapshot(id) {
            const snapshots = this._loadSimSnapshots().filter(s => s.id !== id);
            localStorage.setItem(this._SIM_SNAPSHOT_KEY, JSON.stringify(snapshots));
            this.renderSimCompare();
        },

        _loadSimSnapshots() {
            try {
                return JSON.parse(localStorage.getItem(this._SIM_SNAPSHOT_KEY) || '[]');
            } catch {
                return [];
            }
        },

        /** 导出所有关键数据（dump all） */
        async dumpAll() {
            this.toast('正在导出数据...', 'info');
            const so = { silent: true };
            const [snapshot, trades, watchlist, alerts, qlib, status] = await Promise.allSettled([
                this.fetchJSON('/api/portfolio/snapshot', so),
                this.fetchJSON('/api/portfolio/trades/recent?limit=100', so),
                this.fetchJSON('/api/watchlist', so),
                this.fetchJSON('/api/alerts/rules', so),
                this.fetchJSON('/api/qlib/top?top_n=50', so),
                this.fetchJSON('/api/system/status', so),
            ]);

            const dump = {
                version: '1.0',
                timestamp: new Date().toISOString(),
                portfolio: snapshot.status === 'fulfilled' ? snapshot.value : null,
                trades: trades.status === 'fulfilled' ? trades.value : null,
                watchlist: watchlist.status === 'fulfilled' ? watchlist.value : null,
                alerts: alerts.status === 'fulfilled' ? alerts.value : null,
                qlib: qlib.status === 'fulfilled' ? qlib.value : null,
                system: status.status === 'fulfilled' ? status.value : null,
                snapshots: this._loadSnapshots(),
                simSnapshots: this._loadSimSnapshots(),
                localStorage: { ...localStorage },
            };

            const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `quant-dump-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
            a.click();
            URL.revokeObjectURL(url);
            this.toast('数据导出完成', 'success');
        },

        // ── 隐私模式 ──
        _privacyMode: false,

        togglePrivacy() {
            this._privacyMode = !this._privacyMode;
            document.documentElement.classList.toggle('privacy-mode', this._privacyMode);
            this.toast(this._privacyMode ? '隐私模式已开启' : '隐私模式已关闭', 'info');
        },
    });
})(window);
