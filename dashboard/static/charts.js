/* ── 图表工厂 — 从 CSS 变量读取颜色 ── */

const ChartFactory = {
    _instances: {},
    _colorCache: null,

    getColors() {
        if (this._colorCache) return this._colorCache;
        const s = getComputedStyle(document.documentElement);
        this._colorCache = {
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
        return this._colorCache;
    },

    invalidateColors() { this._colorCache = null; },

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

    _removeEmpty(canvasId) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        const empty = el.parentElement?.querySelector('.chart-empty');
        if (empty) empty.remove();
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
            animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: { enabled: true },
            },
            scales: {
                x: { ticks: { maxTicksLimit: 10, color: c.textMuted, font: { size: 11 } }, grid: { color: c.border + '40' } },
                y: { ticks: { color: c.textMuted, font: { size: 11 } }, grid: { color: c.border + '40' } },
            },
        };
    },

    line(canvasId, data, key, opts = {}) {
        this._removeEmpty(canvasId);
        const existing = this._instances[key];
        if (existing && existing.config.type === 'line') {
            existing.data.labels = data.labels;
            existing.data.datasets = data.datasets.map((ds, i) => ({
                label: ds.label || '',
                data: ds.data,
                borderColor: ds.color || this.palette()[i],
                backgroundColor: ds.fill ? (ds.color || this.palette()[i]) + '1a' : undefined,
                fill: !!ds.fill,
                pointRadius: ds.pointRadius ?? 0,
                borderWidth: ds.borderWidth ?? 1.5,
                borderDash: ds.borderDash || [],
                yAxisID: ds.yAxisID,
            }));
            existing.update();
            return existing;
        }
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
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
        this._removeEmpty(canvasId);
        const existing = this._instances[key];
        if (existing && existing.config.type === 'bar') {
            existing.data.labels = data.labels;
            existing.data.datasets[0].data = data.values;
            existing.data.datasets[0].backgroundColor = data.colors || data.values.map((_, i) => this.palette()[i % this.palette().length] + 'b3');
            existing.data.datasets[0].borderColor = data.borderColors || data.values.map((_, i) => this.palette()[i % this.palette().length]);
            existing.update();
            return existing;
        }
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
        this._removeEmpty(canvasId);
        const existing = this._instances[key];
        if (existing && existing.config.type === 'doughnut') {
            existing.data.labels = data.labels;
            existing.data.datasets[0].data = data.values;
            existing.update();
            return existing;
        }
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
        this._removeEmpty(canvasId);
        const existing = this._instances[key];
        if (existing && existing.config.type === 'pie') {
            existing.data.labels = data.labels;
            existing.data.datasets[0].data = data.values;
            existing.update();
            return existing;
        }
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
        this._removeEmpty(canvasId);
        const existing = this._instances[key];
        if (existing && existing.config.type === 'bar' && existing.options.indexAxis === 'y') {
            existing.data.labels = data.labels;
            existing.data.datasets[0].data = data.values;
            existing.update();
            return existing;
        }
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

    scatter(canvasId, data, key, opts = {}) {
        this._removeEmpty(canvasId);
        this.destroy(key);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const c = this.getColors();
        const config = {
            type: 'scatter',
            data: {
                datasets: [{
                    label: key,
                    data: data,
                    backgroundColor: c.primary + '80',
                    borderColor: c.primary,
                    pointRadius: 3,
                }],
            },
            options: {
                ...this._baseOptions(),
                scales: {
                    x: { ticks: { color: c.textMuted }, grid: { color: c.border + '40' } },
                    y: { ticks: { color: c.textMuted }, grid: { color: c.border + '40' } },
                },
                ...opts,
            },
        };
        this._instances[key] = new Chart(ctx.getContext('2d'), config);
        return this._instances[key];
    },
};
