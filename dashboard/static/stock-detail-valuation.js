/* ── 股票详情页：PEG 估值快照 ── */
if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadValuationSnapshot(code, stale) {
        const container = document.getElementById('sd-valuation-snapshot');
        if (container) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">加载中...</div>';
        }
        let decision = null;
        try {
            const matrix = await App.fetchJSON(`/api/datahub/decision-matrix?scope=codes&codes=${encodeURIComponent(code)}&limit=1&fast=true`, { silent: true, timeout: 8000 });
            decision = matrix?.items?.[0] || null;
            if (!stale() && decision) {
                this._renderValuationSnapshot({}, decision, true);
            }
        } catch {
            decision = null;
        }
        try {
            const data = await App.fetchJSON(`/api/valuation/stock/${encodeURIComponent(code)}?report_limit=5`, { silent: true, timeout: 20000 });
            if (!data || stale()) return;
            try {
                const matrix = await App.fetchJSON(`/api/datahub/decision-matrix?scope=codes&codes=${encodeURIComponent(code)}&limit=1`, { silent: true, timeout: 8000 });
                decision = matrix?.items?.[0] || null;
            } catch {
                decision = decision || null;
            }
            if (stale()) return;
            this._renderValuationSnapshot(data.data || {}, decision, false);
            await this._renderPeerPanel(data.data || {}, decision, false);
        } catch (e) {
            if (stale()) return;
            if (decision) {
                this._renderValuationSnapshot({}, decision, true);
                await this._renderPeerPanel({}, decision, true);
            } else if (container) {
                container.innerHTML = '<div class="text-muted text-center" style="padding:20px">估值数据加载失败</div>';
            }
        }
    },

    _renderValuationSnapshot(data, decision, isPreview = false) {
        const container = document.getElementById('sd-valuation-snapshot');
        const hint = document.getElementById('sd-valuation-hint');
        if (!container) return;
        if (hint) hint.textContent = isPreview ? '快速预览' : (data.latest_report_date ? `更新 ${data.latest_report_date}` : '');
        if (data.code && hint) {
            hint.textContent = `${hint.textContent || ''}${isPreview ? ' · 同业加载中' : ''}`.trim();
        }

        const fmtNum = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : '--';
        const fmtPct = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : '--';
        const fmtMoney = (value) => Number.isFinite(Number(value)) ? `¥${Number(value).toFixed(2)}` : '--';
        const pegCls = data.peg_next_year != null && data.peg_next_year <= 1 ? 'text-up' : data.peg_next_year > 2 ? 'text-down' : '';
        const upsideCls = data.upside_pct > 0 ? 'text-up' : data.upside_pct < 0 ? 'text-down' : '';
        const score = Number(decision?.decision_score || 0);
        const scoreCls = score >= 78 ? 'score-hot' : score >= 62 ? 'score-warm' : score >= 45 ? 'score-neutral' : 'score-cold';
        const risks = decision?.risk_tags || [];
        const actions = decision?.next_actions || [];
        const sourceBits = [
            data.source ? `估值源 ${data.source}` : '',
            data.source_version ? `版本 ${data.source_version}` : '',
            data.quality_status ? `质量 ${data.quality_status}` : '',
            data.snapshot_at ? `快照 ${data.snapshot_at}` : '',
        ].filter(Boolean);

        container.innerHTML = `
            <div class="sd-valuation-head">
                <span class="valuation-badge">${App.escapeHTML(data.valuation_bucket || data.consensus_label || (isPreview ? '快速预览' : '--'))}</span>
                <span class="text-muted">${isPreview ? 'PEG 快照后台加载中' : `研报覆盖 ${data.report_count || 0} 篇 · ${App.escapeHTML(data.latest_rating || '--')}`}</span>
            </div>
            ${sourceBits.length ? `<div class="sd-source-line">${sourceBits.map((bit) => `<span class="valuation-badge">${App.escapeHTML(bit)}</span>`).join('')}</div>` : ''}
            <div class="sd-valuation-grid">
                <div class="sd-period-item"><label>PE(TTM)</label><span>${fmtNum(data.pe_ttm)}</span></div>
                <div class="sd-period-item"><label>明年增速</label><span>${fmtPct(data.growth_next_year_pct)}</span></div>
                <div class="sd-period-item"><label>PEG</label><span class="${pegCls}">${fmtNum(data.peg_next_year)}</span></div>
                <div class="sd-period-item"><label>目标价</label><span>${fmtMoney(data.target_price)}</span></div>
                <div class="sd-period-item"><label>空间</label><span class="${upsideCls}">${fmtPct(data.upside_pct)}</span></div>
                <div class="sd-period-item"><label>机构</label><span>${App.escapeHTML(data.latest_org || '--')}</span></div>
            </div>
            ${decision ? `
                <div class="sd-decision-box">
                    <div>
                        <span class="datahub-score ${scoreCls}">${score}</span>
                        <strong>${App.escapeHTML(decision.decision_label || '--')}</strong>
                        <span class="text-muted text-xs">风险 ${App.escapeHTML(decision.risk_level || '--')}</span>
                    </div>
                    <div class="sd-decision-tags">
                        ${actions.slice(0, 4).map((tag) => `<span class="datahub-next-tag">${App.escapeHTML(tag)}</span>`).join('')}
                        ${risks.slice(0, 3).map((tag) => `<span class="datahub-risk-tag">${App.escapeHTML(tag)}</span>`).join('')}
                    </div>
                </div>
            ` : ''}
        `;
        this._renderPeerPanel(data, decision, isPreview);
    },

    async _renderPeerPanel(data, decision, isPreview = false) {
        const panel = document.getElementById('sd-peer-panel');
        if (!panel) return;
        const code = data.code || decision?.code;
        if (!code) return;
        if (isPreview && panel.dataset.previewCode === code) return;
        panel.dataset.previewCode = code;
        panel.innerHTML = '<div class="text-muted text-center" style="padding:12px">同业对比加载中...</div>';
        try {
            const peerData = await App.fetchJSON(`/api/valuation/peers/${encodeURIComponent(code)}?limit=8`, { silent: true, timeout: 15000 });
            const peers = peerData.peers || [];
            const summary = peerData.summary || {};
            if (!peers.length) {
                panel.innerHTML = '<div class="text-muted text-center" style="padding:12px">暂无同业对比</div>';
                return;
            }
            panel.innerHTML = `
                <div class="valuation-peer-head">
                    <strong>同业位置</strong>
                    <span>排名 ${summary.target_rank || '--'} / ${summary.peer_count || peers.length} · 中位PEG ${this._fmtNum(summary.median_peg)}</span>
                </div>
                <div class="valuation-peer-list">
                    ${peers.slice(0, 6).map((peer) => `
                        <button class="valuation-peer-item" data-peer-code="${App.escapeHTML(peer.code || '')}">
                            <span>${App.escapeHTML(peer.name || peer.code || '--')}</span>
                            <em>PEG ${this._fmtNum(peer.peg_next_year)} · 增速 ${this._fmtPct(peer.growth_next_year_pct)}</em>
                        </button>
                    `).join('')}
                </div>
            `;
            panel.querySelectorAll('[data-peer-code]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    if (btn.dataset.peerCode) {
                        App.openStockDetail(btn.dataset.peerCode, { source: 'stock-detail:peer' });
                    }
                });
            });
        } catch {
            panel.innerHTML = '<div class="text-muted text-center" style="padding:12px">同业对比加载失败</div>';
        }
    },
});
