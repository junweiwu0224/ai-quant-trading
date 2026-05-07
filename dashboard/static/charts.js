/* ── 图表工厂 — 从 CSS 变量读取颜色 ── */

const ChartFactory = {
    _instances: {},

    getColors() {
        const s = getComputedStyle(document.documentElement);
        return {
            primary: s.getPropertyValue('--chart-1').trim() || '#8b8680',
            success: s.getPropertyValue('--chart-2').trim() || '#10b981',
            warning: s.getPropertyValue('--chart-3').trim() || '#e0aa14',
            danger: s.getPropertyValue('--chart-4').trim() || '#c65746',
            muted: s.getPropertyValue('--chart-5').trim() || '#6d6760',
            tertiary: s.getPropertyValue('--chart-6').trim() || '#a29c95',
            quaternary: s.getPropertyValue('--chart-7').trim() || '#726d67',
            text: s.getPropertyValue('--text-secondary').trim() || '#6d6760',
            textMuted: s.getPropertyValue('--text-tertiary').trim() || '#a29c95',
            border: s.getPropertyValue('--border-color').trim() || '#e3e1db',
        };
    },

    palette() {
        const c = this.getColors();
        return [c.primary, c.success, c.warning, c.danger, c.muted, c.tertiary, c.quaternary];
    },

    destroy(key) {
        if (this._instances[key]) {
            this._instances[key].destroy();
            this._instances[key] = null;
        }
    },

    showEmpty(canvasId) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        const parent = el.parentElement;
        if (parent && !parent.querySelector('.chart-empty')) {
            parent.style.position = 'relative';
            const msg = document.createElement('div');
            msg.className = 'chart-empty';
            msg.textContent = '暂无数据';
            parent.appendChild(msg);
        }
    },

    _baseOptions() {
        const c = this.getColors();
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 10, color: c.textMuted, font: { size: 11 } }, grid: { color: c.border + '40' } },
                y: { ticks: { color: c.textMuted, font: { size: 11 } }, grid: { color: c.border + '40' } },
            },
        };
    },

    line(canvasId, data, key, opts = {}) {
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const c = this.getColors();
        const config = {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: data.datasets.map((ds, i) => ({
                    label: ds.label || '',
                    data: ds.data,
                    borderColor: ds.color || this.palette()[i],
                    backgroundColor: ds.fill ? (ds.color || this.palette()[i]) + '1a' : undefined,
                    fill: !!ds.fill,
                    pointRadius: ds.pointRadius ?? 0,
                    borderWidth: ds.borderWidth ?? 1.5,
                    borderDash: ds.borderDash || [],
                    yAxisID: ds.yAxisID,
                })),
            },
            options: { ...this._baseOptions(), ...opts },
        };
        if (data.datasets.some(ds => ds.yAxisID)) {
            config.options.scales = { ...config.options.scales };
        }
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },

    bar(canvasId, data, key, opts = {}) {
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const config = {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: data.colors || data.values.map((_, i) => this.palette()[i % this.palette().length] + 'b3'),
                    borderColor: data.borderColors || data.values.map((_, i) => this.palette()[i % this.palette().length]),
                    borderWidth: 1,
                }],
            },
            options: { ...this._baseOptions(), ...opts },
        };
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },

    doughnut(canvasId, data, key, opts = {}) {
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const c = this.getColors();
        const config = {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{ data: data.values, backgroundColor: this.palette() }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'right', labels: { color: c.text, font: { size: 11 } } } },
                ...opts,
            },
        };
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },

    pie(canvasId, data, key, opts = {}) {
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const c = this.getColors();
        const config = {
            type: 'pie',
            data: {
                labels: data.labels,
                datasets: [{ data: data.values, backgroundColor: this.palette() }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'right', labels: { color: c.text, font: { size: 11 } } } },
                ...opts,
            },
        };
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },

    horizontalBar(canvasId, data, key, opts = {}) {
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const c = this.getColors();
        const config = {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: (data.color || c.primary) + 'b3',
                    borderColor: data.color || c.primary,
                    borderWidth: 1,
                }],
            },
            options: {
                ...this._baseOptions(),
                indexAxis: 'y',
                scales: {
                    x: { ticks: { color: c.textMuted }, grid: { color: c.border + '40' } },
                    y: { ticks: { color: c.text, font: { size: 11 } }, grid: { display: false } },
                },
                ...opts,
            },
        };
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },
};
