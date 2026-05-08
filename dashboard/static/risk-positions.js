/* ── 风控模块：持仓止损止盈管理 ── */

Object.assign(App, {
    _rkRenderPositionSltp() {
        const positions = this._rk.snapshot?.positions;
        const tbody = document.querySelector('#rk-sltp-table tbody');
        if (!tbody) return;

        if (!positions || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-muted" style="text-align:center">暂无持仓</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map(p => {
            const current = Number(p.current_price) || Number(p.avg_price) || 0;
            const cost = Number(p.avg_price) || 0;
            const pnlPct = cost > 0 ? ((current - cost) / cost * 100) : 0;
            const sl = Number(p.stop_loss_price) || 0;
            const tp = Number(p.take_profit_price) || 0;
            const slDist = current > 0 && sl > 0 ? ((current - sl) / current * 100) : null;
            const tpDist = current > 0 && tp > 0 ? ((tp - current) / current * 100) : null;
            const slTriggered = p.stop_loss_triggered;
            const tpTriggered = p.take_profit_triggered;

            const slCls = slTriggered ? 'text-down' : (slDist !== null && slDist < 3 ? 'rk-distance-warn' : 'rk-distance-safe');
            const tpCls = tpTriggered ? 'text-up' : '';

            return `<tr class="${slTriggered ? 'rk-row-danger' : ''}">
                <td><strong>${this.escapeHTML(p.code)}</strong></td>
                <td>${this.escapeHTML(p.name || '--')}</td>
                <td>${cost.toFixed(2)}</td>
                <td>${current.toFixed(2)}</td>
                <td class="${pnlPct >= 0 ? 'text-up' : 'text-down'}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</td>
                <td class="rk-editable"><input type="number" data-sl="${this.escapeHTML(p.code)}" value="${sl || ''}" step="0.01" placeholder="止损价" style="width:80px"></td>
                <td class="${slCls}">${slDist !== null ? slDist.toFixed(1) + '%' : '--'}</td>
                <td class="rk-editable"><input type="number" data-tp="${this.escapeHTML(p.code)}" value="${tp || ''}" step="0.01" placeholder="止盈价" style="width:80px"></td>
                <td class="${tpCls}">${tpDist !== null ? tpDist.toFixed(1) + '%' : '--'}</td>
                <td><button class="btn btn-sm rk-sltp-save" data-code="${this.escapeHTML(p.code)}">保存</button></td>
            </tr>`;
        }).join('');

        if (!this._rk._sltpBound) {
            tbody.addEventListener('click', e => {
                const btn = e.target.closest('.rk-sltp-save');
                if (btn) this._rkSaveSltp(btn.dataset.code);
            });

            const batchBtn = document.getElementById('rk-batch-sltp');
            if (batchBtn) batchBtn.addEventListener('click', () => this._rkShowBatchModal());
            this._rk._sltpBound = true;
        }
    },

    async _rkSaveSltp(code) {
        const slInput = document.querySelector(`input[data-sl="${code}"]`);
        const tpInput = document.querySelector(`input[data-tp="${code}"]`);

        const body = { code };
        if (slInput && slInput.value) body.stop_loss = parseFloat(slInput.value);
        if (tpInput && tpInput.value) body.take_profit = parseFloat(tpInput.value);

        if (!body.stop_loss && !body.take_profit) {
            this.toast('请设置止损价或止盈价', 'info');
            return;
        }

        try {
            const resp = await this.fetchJSON('/api/portfolio/stoploss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (resp.success) {
                this.toast(`${code} 止损止盈已保存`, 'success');
                await this.loadRisk();
            } else {
                this.toast('保存失败: ' + (resp.message || '未知错误'), 'error');
            }
        } catch (e) {
            this.toast('保存失败: ' + e.message, 'error');
        }
    },

    _rkShowBatchModal() {
        document.querySelector('.modal-overlay')?.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:480px">
                <h2>批量设置止损止盈</h2>
                <div class="form-group mt-md">
                    <label>止损模式</label>
                    <select id="rk-batch-sl-mode">
                        <option value="fixed">固定百分比</option>
                        <option value="trailing">追踪止损</option>
                    </select>
                </div>
                <div class="form-group mt-sm">
                    <label>止损幅度 (%)</label>
                    <input type="number" id="rk-batch-sl-pct" value="5" min="1" max="50" step="0.5">
                </div>
                <div class="form-group mt-sm">
                    <label>止盈幅度 (%)</label>
                    <input type="number" id="rk-batch-tp-pct" value="20" min="1" max="100" step="1">
                </div>
                <div class="modal-actions">
                    <button class="btn btn-ghost" id="rk-batch-cancel">取消</button>
                    <button class="btn btn-primary" id="rk-batch-confirm">应用到全部持仓</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
        overlay.querySelector('#rk-batch-cancel').addEventListener('click', () => overlay.remove());
        overlay.querySelector('#rk-batch-confirm').addEventListener('click', async () => {
            const slPct = parseFloat(overlay.querySelector('#rk-batch-sl-pct').value) / 100;
            const tpPct = parseFloat(overlay.querySelector('#rk-batch-tp-pct').value) / 100;

            if (isNaN(slPct) || slPct <= 0 || slPct >= 1) {
                this.toast('止损幅度需在 1-99% 之间', 'error');
                return;
            }
            if (isNaN(tpPct) || tpPct <= 0 || tpPct > 5) {
                this.toast('止盈幅度需在 1-500% 之间', 'error');
                return;
            }

            const positions = this._rk.snapshot?.positions || [];
            if (positions.length === 0) {
                this.toast('暂无持仓', 'info');
                return;
            }

            overlay.remove();
            let success = 0;

            for (const p of positions) {
                const price = Number(p.current_price) || Number(p.avg_price);
                if (!price) continue;

                const body = {
                    code: p.code,
                    stop_loss: +(price * (1 - slPct)).toFixed(2),
                    take_profit: +(price * (1 + tpPct)).toFixed(2),
                };

                try {
                    const resp = await this.fetchJSON('/api/portfolio/stoploss', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    if (resp.success) success++;
                } catch (_) {}
            }

            this.toast(`已批量设置 ${success}/${positions.length} 只持仓`, 'success');
            await this.loadRisk();
        });
    },
});
