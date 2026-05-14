/* ── 风控模块：实时告警 ── */

Object.assign(App, {
    _rkHandleAlert(alert) {
        if (!alert) return;

        this._rk.activeAlerts.push(alert);

        const level = alert.level || 'warning';
        this.toast(`[风控] ${alert.message}`, level === 'critical' ? 'error' : 'warning');

        // 发射到异常聚合条
        this.emit('risk:alert', { level: level === 'critical' ? 'critical' : 'warn', msg: alert.message || '风控告警' });

        this._rkRenderAlertBanner();

        App.notify('风控告警', alert.message, { level: level === 'critical' ? 'critical' : 'warning' });
    },

    _rkRenderAlertBanner() {
        const banner = document.getElementById('rk-alert-banner');
        if (!banner) return;

        const alerts = this._rk.activeAlerts || [];
        if (alerts.length === 0) {
            banner.style.display = 'none';
            return;
        }

        const latest = alerts[alerts.length - 1];
        const level = latest.level || 'warning';
        const count = alerts.length;
        const iconCls = level === 'critical' ? 'rk-alert-dot--critical' : 'rk-alert-dot--warning';

        banner.style.display = 'flex';
        banner.className = `rk-alert-banner ${level}`;
        banner.innerHTML = `
            <span class="rk-alert-dot ${iconCls}"></span>
            <span class="rk-alert-text">
                <strong>${count > 1 ? `${count} 条告警` : '告警'}</strong>: ${this.escapeHTML(latest.message)}
                ${count > 1 ? `<span class="rk-alert-more">（还有 ${count - 1} 条）</span>` : ''}
            </span>
            <button class="btn btn-sm btn-ghost" data-risk-alert-action="view-details">查看详情</button>
            <button class="btn btn-sm btn-ghost" data-risk-alert-action="dismiss-alerts">忽略</button>
        `;

        if (!this._rk._alertBannerBound) {
            banner.addEventListener('click', (e) => {
                const button = e.target.closest('[data-risk-alert-action]');
                if (!button) return;
                e.preventDefault();
                const action = button.dataset.riskAlertAction;
                if (action === 'view-details') {
                    this._rkScrollToEvents();
                    return;
                }
                if (action === 'dismiss-alerts') {
                    this._rkDismissAlerts();
                }
            });
            this._rk._alertBannerBound = true;
        }
    },

    _rkScrollToEvents() {
        const el = document.getElementById('rk-events-section');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    _rkDismissAlerts() {
        this._rk.activeAlerts = [];
        this._rkRenderAlertBanner();
    },

    _rkRequestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    },
});
