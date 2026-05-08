/* ── 风控模块：事件时间线 ── */

Object.assign(App, {
    _rkRenderEvents() {
        const container = document.getElementById('rk-events-timeline');
        if (!container) return;

        const events = this._rk.events || [];
        const filtered = this._rkFilterEvents(events);

        if (filtered.length === 0) {
            container.innerHTML = '<div class="text-muted" style="text-align:center;padding:24px">暂无风控事件</div>';
            return;
        }

        const typeLabels = {
            stop_loss: '止损',
            take_profit: '止盈',
            trailing_stop: '追踪止损',
            position_limit: '仓位限制',
            drawdown_limit: '回撤限制',
        };

        const typeColors = {
            stop_loss: 'badge-danger',
            take_profit: 'badge-success',
            trailing_stop: 'badge-warning',
            position_limit: 'badge-info',
            drawdown_limit: 'badge-danger',
        };

        const page = this._rk._eventsPage || 1;
        const pageSize = 20;
        const paged = filtered.slice(0, page * pageSize);

        container.innerHTML = `<div class="rk-timeline">
            ${paged.map(ev => {
                const timeStr = Utils.formatBeijingTime(ev.created_at);
                const typeLabel = typeLabels[ev.event_type] || ev.event_type;
                const badgeCls = typeColors[ev.event_type] || 'badge-info';

                return `<div class="rk-timeline-item">
                    <div class="rk-timeline-dot ${badgeCls.replace('badge-', '')}"></div>
                    <div class="rk-timeline-time">${timeStr}</div>
                    <div class="rk-timeline-body">
                        <span class="badge ${badgeCls}">${this.escapeHTML(typeLabel)}</span>
                        ${ev.code ? `<span class="rk-timeline-code">${this.escapeHTML(ev.code)}</span>` : ''}
                        ${ev.trigger_price ? `<span class="rk-timeline-price">触发价: ${ev.trigger_price}</span>` : ''}
                        <div class="rk-timeline-reason">${this.escapeHTML(ev.reason || '--')}</div>
                    </div>
                </div>`;
            }).join('')}
        </div>
        ${filtered.length > paged.length ? `<div class="text-center mt-md"><button class="btn btn-sm" onclick="App._rkLoadMoreEvents()">加载更多 (${paged.length}/${filtered.length})</button></div>` : ''}`;

        if (!this._rk._eventsBound) {
            const filterType = document.getElementById('rk-filter-type');
            const filterCode = document.getElementById('rk-filter-code');
            if (filterType) filterType.addEventListener('change', () => { this._rk._eventsPage = 1; this._rkRenderEvents(); });
            if (filterCode) filterCode.addEventListener('input', () => { this._rk._eventsPage = 1; this._rkRenderEvents(); });
            this._rk._eventsBound = true;
        }
    },

    _rkFilterEvents(events) {
        const typeEl = document.getElementById('rk-filter-type');
        const codeEl = document.getElementById('rk-filter-code');
        const typeFilter = typeEl ? typeEl.value : '';
        const codeFilter = codeEl ? codeEl.value.trim() : '';

        return events.filter(ev => {
            if (typeFilter && ev.event_type !== typeFilter) return false;
            if (codeFilter && ev.code && !ev.code.includes(codeFilter)) return false;
            return true;
        });
    },

    _rkLoadMoreEvents() {
        this._rk._eventsPage = (this._rk._eventsPage || 1) + 1;
        this._rkRenderEvents();
    },
});
