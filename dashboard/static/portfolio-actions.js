/* ── 持仓模块：操作（平仓/止损止盈/导出） ── */

Object.assign(App, {
    // ── 一键平仓 ──
    pfFullClose(code) {
        this._pf._closingCode = code;
        const modal = document.getElementById('pf-close-modal');
        document.getElementById('pf-close-info').textContent = `确定要全部清仓 ${code} 吗？`;
        document.getElementById('pf-close-code-display').textContent = code;
        document.getElementById('pf-close-confirm').value = '';
        document.getElementById('pf-close-confirm-btn').disabled = true;
        modal.style.display = '';

        const input = document.getElementById('pf-close-confirm');
        const btn = document.getElementById('pf-close-confirm-btn');
        input.oninput = () => { btn.disabled = input.value !== code; };
        btn.onclick = () => this._pfDoClose(code);
    },

    async _pfDoClose(code) {
        try {
            const data = await this.fetchJSON('/api/portfolio/close', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            this.toast(data.message || '平仓成功', 'success');
            this.pfCloseModal();
            setTimeout(() => this.loadPortfolio(), 1000);
        } catch (e) {
            this.toast('平仓失败: ' + (e.message || e), 'error');
        }
    },

    pfCloseModal() {
        document.getElementById('pf-close-modal').style.display = 'none';
        this._pf._closingCode = null;
    },

    // ── 部分平仓 ──
    pfPartialClose(code, maxVol) {
        this._pf._partialCode = code;
        const modal = document.getElementById('pf-partial-modal');
        document.getElementById('pf-partial-info').textContent = `卖出 ${code} 的部分持仓`;
        document.getElementById('pf-partial-max').textContent = maxVol;
        const input = document.getElementById('pf-partial-vol');
        input.value = '';
        input.max = maxVol;
        document.getElementById('pf-partial-confirm-btn').disabled = true;
        modal.style.display = '';

        const btn = document.getElementById('pf-partial-confirm-btn');
        input.oninput = () => {
            const v = parseInt(input.value);
            btn.disabled = isNaN(v) || v <= 0 || v > maxVol;
        };
        btn.onclick = () => this._pfDoPartialClose(code, parseInt(input.value));
    },

    async _pfDoPartialClose(code, volume) {
        try {
            const data = await this.fetchJSON('/api/portfolio/close', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, volume }),
            });
            this.toast(data.message || '卖出成功', 'success');
            this.pfPartialModal();
            setTimeout(() => this.loadPortfolio(), 1000);
        } catch (e) {
            this.toast('卖出失败: ' + (e.message || e), 'error');
        }
    },

    pfPartialModal() {
        document.getElementById('pf-partial-modal').style.display = 'none';
        this._pf._partialCode = null;
    },

    // ── 止损止盈编辑 ──
    pfEditSltp(code, name) {
        this._pf._sltpCode = code;
        const pos = this._pf.positions.find(p => p.code === code);
        const modal = document.getElementById('pf-sltp-modal');
        document.getElementById('pf-sltp-name').textContent = `${name} (${code})`;
        document.getElementById('pf-sltp-sl').value = pos ? pos.stop_loss_price : '';
        document.getElementById('pf-sltp-tp').value = pos ? pos.take_profit_price : '';
        modal.style.display = '';
    },

    async pfSaveSltp() {
        const code = this._pf._sltpCode;
        const sl = parseFloat(document.getElementById('pf-sltp-sl').value) || null;
        const tp = parseFloat(document.getElementById('pf-sltp-tp').value) || null;

        if (!sl && !tp) {
            this.toast('请至少填写一个价格', 'error');
            return;
        }

        try {
            const body = { code };
            if (sl) body.stop_loss = sl;
            if (tp) body.take_profit = tp;

            await this.fetchJSON('/api/portfolio/stoploss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            this.toast('止损止盈已更新', 'success');
            this.pfSltpModal();
            this.loadPortfolio();
        } catch (e) {
            this.toast('保存失败: ' + (e.message || e), 'error');
        }
    },

    pfSltpModal() {
        document.getElementById('pf-sltp-modal').style.display = 'none';
        this._pf._sltpCode = null;
    },

    // ── 导出 ──
    pfExportCSV() {
        window.open('/api/portfolio/export?format=csv', '_blank');
    },

    pfExportJSON() {
        window.open('/api/portfolio/export?format=json', '_blank');
    },
});
