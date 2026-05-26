/* ── 模拟盘：持仓 / 止损 / 平仓 ── */

if (!globalThis.PaperTrading) {
    globalThis.PaperTrading = {};
}

Object.assign(globalThis.PaperTrading, {
    async loadPositions() {
        try {
            const data = await App.fetchJSON('/api/paper/positions');
            this.state.positions = data.data || [];
            await this._fetchStockNames(this.state.positions.map(p => p.code));
            this.renderPositions();
            this.renderPositionPie();
        } catch (e) {
            console.error('加载持仓失败:', e);
        }
    },

    async _fetchStockNames(codes) {
        const missing = codes.filter(c => !this._stockNameCache[c]);
        if (missing.length === 0) return;
        try {
            const results = await Promise.allSettled(
                missing.map(code => App.fetchJSON(`/api/stock/detail/${code}`).then(d => ({ code, name: d.name || code })))
            );
            results.forEach(r => {
                if (r.status === 'fulfilled') {
                    this._stockNameCache[r.value.code] = r.value.name;
                }
            });
        } catch {}
    },

    _calcStopLossDistance(pos) {
        const price = pos.current_price;
        const avg = pos.avg_price;
        if (!price || !avg) return { slDist: null, tpDist: null, slPct: null, tpPct: null };
        const slDist = pos.stop_loss_price ? ((price - pos.stop_loss_price) / price * 100) : null;
        const tpDist = pos.take_profit_price ? ((pos.take_profit_price - price) / price * 100) : null;
        const pnlPct = (price / avg - 1) * 100;
        return { slDist, tpDist, pnlPct };
    },

    _renderStopLossBar(pos) {
        const { slDist, tpDist, pnlPct } = this._calcStopLossDistance(pos);
        if (slDist === null && tpDist === null) return '';

        const sl = pos.stop_loss_price;
        const tp = pos.take_profit_price;
        if (sl && tp && tp > sl) {
            const range = tp - sl;
            const pct = Math.max(0, Math.min(100, ((pos.current_price - sl) / range) * 100));
            const barColor = pnlPct >= 0 ? 'var(--up-color)' : 'var(--down-color)';
            return `<div class="stop-bar-wrap" title="止损 ${sl.toFixed(2)} | 止盈 ${tp.toFixed(2)}">
                <div class="stop-bar">
                    <div class="stop-bar-fill" style="width:${pct}%;background:${barColor}"></div>
                    <div class="stop-bar-marker" style="left:0" title="止损"></div>
                    <div class="stop-bar-marker" style="left:100%" title="止盈"></div>
                </div>
                <div class="stop-bar-labels">
                    <span class="text-down">${slDist !== null ? slDist.toFixed(1) + '%' : '--'}</span>
                    <span class="text-up">${tpDist !== null ? '+' + tpDist.toFixed(1) + '%' : '--'}</span>
                </div>
            </div>`;
        }

        let html = '<div class="stop-bar-labels">';
        if (slDist !== null) {
            const cls = slDist < 3 ? 'text-up' : slDist < 8 ? '' : 'text-down';
            html += `<span class="${cls}">距止损 ${slDist.toFixed(1)}%</span>`;
        }
        if (tpDist !== null) {
            html += `<span class="text-up">距止盈 +${tpDist.toFixed(1)}%</span>`;
        }
        html += '</div>';
        return html;
    },

    renderPositions() {
        const tbody = document.querySelector('#pt-positions-table tbody');
        const emptyHint = document.getElementById('pt-positions-empty');
        if (!tbody) return;

        if (this.state.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-muted text-center">暂无持仓</td></tr>';
            if (emptyHint) emptyHint.style.display = 'block';
            return;
        }

        if (emptyHint) emptyHint.style.display = 'none';
        tbody.innerHTML = this.state.positions.map(pos => {
            const pnlClass = pos.unrealized_pnl >= 0 ? 'text-up' : 'text-down';
            const pnlSign = pos.unrealized_pnl >= 0 ? '+' : '';
            const name = this._stockNameCache[pos.code] || pos.code;
            const price = pos.current_price;
            const avg = pos.avg_price;
            const slDist = pos.stop_loss_price ? ((price - pos.stop_loss_price) / price * 100) : null;
            const tpDist = pos.take_profit_price ? ((pos.take_profit_price - price) / price * 100) : null;

            return `<tr>
                <td><a href="#" class="stock-link" data-code="${App.escapeHTML(pos.code)}">${App.escapeHTML(pos.code)}</a> ${App.escapeHTML(name)}</td>
                <td>${pos.volume}</td>
                <td>¥${avg.toFixed(2)}</td>
                <td>¥${price.toFixed(2)}</td>
                <td>¥${pos.market_value.toLocaleString()}</td>
                <td class="${pnlClass}">${pnlSign}¥${pos.unrealized_pnl.toFixed(2)}</td>
                <td class="${pnlClass}">${pnlSign}${pos.unrealized_pnl_pct.toFixed(2)}%</td>
                <td class="sl-tp-cell">
                    ${this._renderStopLossBar(pos)}
                    <div class="sl-tp-inputs">
                        <label class="sl-tp-label">止损
                            <input type="number" class="form-control form-control-sm" step="0.01"
                                   value="${pos.stop_loss_price || ''}"
                                   placeholder="${(avg * 0.95).toFixed(2)}"
                                   data-paper-action="update-stop-loss"
                                   data-code="${App.escapeHTML(pos.code)}"
                                   data-stop-type="stop_loss">
                            ${slDist !== null ? `<span class="sl-tp-dist text-down">-${slDist.toFixed(1)}%</span>` : ''}
                        </label>
                        <label class="sl-tp-label">止盈
                            <input type="number" class="form-control form-control-sm" step="0.01"
                                   value="${pos.take_profit_price || ''}"
                                   placeholder="${(avg * 1.10).toFixed(2)}"
                                   data-paper-action="update-stop-loss"
                                   data-code="${App.escapeHTML(pos.code)}"
                                   data-stop-type="take_profit">
                            ${tpDist !== null ? `<span class="sl-tp-dist text-up">+${tpDist.toFixed(1)}%</span>` : ''}
                        </label>
                    </div>
                </td>
                <td>
                    <div style="display:flex;gap:4px;align-items:center">
                        <input type="number" class="form-control form-control-sm" id="pt-partial-${pos.code}"
                               min="100" step="100" max="${pos.volume}" placeholder="${pos.volume}"
                               style="width:70px;font-size:12px">
                        <button class="btn btn-sm btn-warning" data-paper-action="partial-close" data-code="${App.escapeHTML(pos.code)}" title="部分平仓">部分</button>
                        <button class="btn btn-sm btn-danger" data-paper-action="close-position" data-code="${App.escapeHTML(pos.code)}" title="全部平仓">平仓</button>
                    </div>
                </td>
            </tr>`;
        }).join('');
    },

    async updateStopLoss(code, value, type) {
        const body = {};
        if (type === 'stop_loss') body.stop_loss_price = value ? parseFloat(value) : null;
        else body.take_profit_price = value ? parseFloat(value) : null;

        try {
            await App.fetchJSON(`/api/paper/positions/${code}/stop-loss`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            App.toast('止损止盈价格已更新', 'success');
        } catch (e) {
            App.toast(`更新失败: ${e.message}`, 'error');
        }
    },

    async closePosition(code, volume = null) {
        const confirmMsg = volume ? `确定要平仓 ${code} ${volume}股吗？` : `确定要全部平仓 ${code} 吗？`;
        if (!confirm(confirmMsg)) return;
        try {
            const url = volume ? `/api/paper/positions/${code}/close?volume=${volume}` : `/api/paper/positions/${code}/close`;
            await App.fetchJSON(url, { method: 'POST' });
            App.toast('平仓订单已创建', 'success');
            this.loadOrders();
            this.loadPositions();
        } catch (e) {
            App.toast(`平仓失败: ${e.message}`, 'error');
        }
    },

    async partialClose(code) {
        const input = document.getElementById(`pt-partial-${code}`);
        const volume = input ? parseInt(input.value) : 0;
        const pos = this.state.positions.find(p => p.code === code);
        if (!pos) return;
        if (!volume || volume <= 0) { App.toast('请输入平仓数量', 'error'); return; }
        if (volume > pos.volume) { App.toast(`平仓数量不能超过持仓 ${pos.volume} 股`, 'error'); return; }
        if (volume % 100 !== 0) { App.toast('平仓数量必须为100的整数倍', 'error'); return; }
        await this.closePosition(code, volume);
    },

    async closeAllPositions() {
        if (this.state.positions.length === 0) {
            App.toast('没有持仓需要平仓', 'info');
            return;
        }

        const confirmMsg = `确定要平仓所有 ${this.state.positions.length} 只持仓吗？`;
        if (!confirm(confirmMsg)) return;

        const btn = document.getElementById('pt-close-all-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="skeleton-pulse" style="display:inline-block;width:1em;height:1em;border-radius:50%;vertical-align:middle;margin-right:4px"></span>平仓中...'; }

        try {
            const results = await Promise.allSettled(
                this.state.positions.map(pos =>
                    App.fetchJSON(`/api/paper/positions/${pos.code}/close`, { method: 'POST' })
                        .then(data => {
                            if (!data.success) throw new Error(data.detail || data.message);
                            return { code: pos.code, success: true };
                        })
                        .catch(e => ({ code: pos.code, success: false, error: e.message }))
                )
            );

            const succeeded = results.filter(r => r.status === 'fulfilled' && r.value.success).length;
            const failed = results.length - succeeded;

            if (failed === 0) App.toast(`已平仓 ${succeeded} 只持仓`, 'success');
            else App.toast(`平仓完成：${succeeded} 成功，${failed} 失败`, 'warning');

            this.loadOrders();
            this.loadPositions();
        } catch (e) {
            App.toast(`批量平仓失败: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '一键清仓'; }
        }
    },
});
