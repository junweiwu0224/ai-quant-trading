/* ── 自选股管理 ── */

const Watchlist = {
    _searchBox: null,

    init() {
        this._searchBox = new SearchBox('watchlist-input', 'watchlist-search-results', {
            maxResults: 8,
            formatItem: (s) => `${s.code} ${s.name}`,
        });
        this._searchBox.setDataSource((q) => {
            if (!App.stockCache) return [];
            return App.stockCache.filter(s =>
                s.code.includes(q) || (s.name && s.name.toLowerCase().includes(q))
            );
        });
        this._searchBox.onSelect(() => this.add());

        // Enter 键直接添加
        const input = document.getElementById('watchlist-input');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); this.add(); }
            });
        }
    },

    async add() {
        const code = this._searchBox ? this._searchBox.getValue() : '';
        if (!code) { App.toast('请输入股票代码', 'error'); return; }
        if (!/^\d{6}$/.test(code)) { App.toast('请输入 6 位股票代码', 'error'); return; }

        try {
            const res = await fetch('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            App.toast(`已添加 ${code}`, 'success');
            if (this._searchBox) this._searchBox.setValue('');
            App.loadOverview();
        } catch (e) {
            App.toast('添加失败: ' + e.message, 'error');
        }
    },

    async remove(code) {
        if (!confirm(`确定删除 ${code}？`)) return;
        try {
            const res = await fetch(`/api/watchlist/${code}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            App.toast(`已删除 ${code}`, 'success');
            App.loadOverview();
        } catch (e) {
            App.toast('删除失败: ' + e.message, 'error');
        }
    },

    async sync() {
        const btn = document.querySelector('button[onclick="Watchlist.sync()"]');
        if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="spinner"></span>同步中...'; }
        try {
            const res = await fetch('/api/watchlist/sync', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            App.toast(`同步完成: ${data.synced || 0} 只`, 'success');
            App.loadOverview();
        } catch (e) {
            App.toast('同步失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || '同步数据'; }
        }
    },

    render(stocks) {
        const stockBody = document.querySelector('#ov-stocks-table tbody');
        const hintEl = document.getElementById('ov-stock-hint');
        if (!stockBody) return;

        const list = Array.isArray(stocks) ? stocks : [];
        if (list.length > 0) {
            if (hintEl) hintEl.textContent = `(共 ${list.length} 只)`;
            stockBody.innerHTML = list.slice(0, 20).map(s => `
                <tr>
                    <td>${App.escapeHTML(s.code)}</td>
                    <td>${App.escapeHTML(s.name) || '--'}</td>
                    <td>${App.escapeHTML(s.industry) || '--'}</td>
                    <td>${s.latest_price ? '¥' + s.latest_price : '--'}</td>
                    <td><button class="btn btn-danger btn-sm" onclick="Watchlist.remove('${App.escapeHTML(s.code)}')">删除</button></td>
                </tr>
            `).join('');
        } else {
            if (hintEl) hintEl.textContent = '';
            stockBody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无自选股，使用上方搜索框添加</td></tr>';
        }
    },
};
