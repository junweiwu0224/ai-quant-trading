/* ── 风控模块：规则编辑器 ── */

Object.assign(App, {
    _rkRenderRules() {
        const rules = this._rk.rules;
        const systemRules = this._rk.systemRules;
        if (!rules && (!systemRules || systemRules.length === 0)) return;

        const tbody = document.querySelector('#rk-rules-table tbody');
        if (!tbody) return;

        const ruleDefs = [
            { key: 'max_position_pct', name: '单票仓位上限', fmt: v => (v * 100).toFixed(1) + '%', parse: v => parseFloat(v) / 100, min: 1, max: 100, step: 1, unit: '%' },
            { key: 'max_positions', name: '最大持仓数', fmt: v => v, parse: v => parseInt(v), min: 1, max: 50, step: 1, unit: '' },
            { key: 'max_drawdown', name: '最大回撤止损', fmt: v => (v * 100).toFixed(1) + '%', parse: v => parseFloat(v) / 100, min: 1, max: 100, step: 1, unit: '%' },
            { key: 'max_daily_loss', name: '日亏损限额', fmt: v => (v * 100).toFixed(1) + '%', parse: v => parseFloat(v) / 100, min: 0.5, max: 50, step: 0.5, unit: '%' },
        ];

        const current = rules?.data || rules || {};

        const statusMap = {};
        for (const sr of systemRules) {
            statusMap[sr.name] = sr.status;
        }

        tbody.innerHTML = ruleDefs.map(def => {
            const val = current[def.key];
            const displayVal = val !== undefined ? def.fmt(val) : '--';
            const rawVal = val !== undefined ? (def.unit === '%' ? (val * 100) : val) : '';
            const status = statusMap[def.name] || 'ok';

            return `<tr>
                <td>${this.escapeHTML(def.name)}</td>
                <td class="rk-editable"><input type="number" data-key="${def.key}" data-parse="${def.key}" value="${rawVal}" min="${def.min}" max="${def.max}" step="${def.step}" style="width:80px"> ${def.unit}</td>
                <td>${this.escapeHTML(displayVal)}</td>
                <td><span class="badge badge-${status === 'ok' ? 'success' : 'danger'}">${status === 'ok' ? '正常' : '告警'}</span></td>
            </tr>`;
        }).join('');

        if (!this._rk._rulesLoaded) {
            const saveBtn = document.getElementById('rk-rules-save');
            if (saveBtn) saveBtn.addEventListener('click', () => this._rkSaveRules());

            const resetBtn = document.getElementById('rk-rules-reset');
            if (resetBtn) resetBtn.addEventListener('click', () => this._rkResetRules());

            this._rk._rulesLoaded = true;
        }
    },

    async _rkSaveRules() {
        const inputs = document.querySelectorAll('#rk-rules-table input[data-key]');
        const body = {};

        const defs = {
            max_position_pct: { min: 0.01, max: 1.0 },
            max_positions: { min: 1, max: 50 },
            max_drawdown: { min: 0.01, max: 1.0 },
            max_daily_loss: { min: 0.005, max: 0.5 },
        };

        for (const input of inputs) {
            const key = input.dataset.key;
            let val = parseFloat(input.value);
            if (isNaN(val)) continue;

            if (key.includes('pct') || key.includes('drawdown') || key.includes('loss')) {
                val = val / 100;
            }

            const def = defs[key];
            if (def && (val < def.min || val > def.max)) {
                this.toast(`${key} 取值范围: ${def.min * 100}% - ${def.max * 100}%`, 'error');
                return;
            }

            body[key] = val;
        }

        if (Object.keys(body).length === 0) {
            this.toast('没有需要保存的修改', 'info');
            return;
        }

        try {
            const resp = await this.fetchJSON('/api/paper/risk/rules', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (resp.success) {
                this.toast('风控规则已保存', 'success');
                await this.loadRisk();
            } else {
                this.toast('保存失败: ' + (resp.message || '未知错误'), 'error');
            }
        } catch (e) {
            this.toast('保存失败: ' + e.message, 'error');
        }
    },

    _rkResetRules() {
        const defaults = {
            max_position_pct: 30,
            max_positions: 10,
            max_drawdown: 20,
            max_daily_loss: 5,
        };

        const inputs = document.querySelectorAll('#rk-rules-table input[data-key]');
        for (const input of inputs) {
            const key = input.dataset.key;
            if (defaults[key] !== undefined) {
                input.value = defaults[key];
            }
        }

        this.toast('已重置为默认值，请点击保存', 'info');
    },
});
