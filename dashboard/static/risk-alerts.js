/* ── 风控模块：实时告警 ── */

Object.assign(App, {
    _rkHandleAlert(alert) {
        if (!alert) return;

        this._rk.activeAlerts.push(alert);

        const level = alert.level || 'warning';
        this.toast(`[风控] ${alert.message}`, level === 'critical' ? 'error' : 'warning');

        this._rkRenderAlertBanner();

        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('风控告警', { body: alert.message });
        }
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
            <button class="btn btn-sm btn-ghost" onclick="App._rkScrollToEvents()">查看详情</button>
            <button class="btn btn-sm btn-ghost" onclick="App._rkDismissAlerts()">忽略</button>
        `;
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
