/**
 * 多股对比模块
 * 归一化收益率对比图（Chart.js），支持缩放和区间标注
 */
(function () {
    'use strict';

    let _chart = null;
    let _codes = [];
    let _multiSearch = null;

    const COLORS = [
        '#4fc3f7', '#ef5350', '#66bb6a', '#ffa726', '#ab47bc',
        '#26a69a', '#ec407a', '#42a5f5',
    ];

    // ── 初始化 ──

    function init() {
        const btn = document.getElementById('compare-run-btn');
        if (!btn) return;

        btn.addEventListener('click', () => run());

        // 初始化 MultiSearchBox
        _multiSearch = new MultiSearchBox('compare-codes-input', 'compare-search-dropdown', 'compare-search-tags', {
            maxResults: 200,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });

        // 限制最多5只
        _multiSearch.onToggle = (item, added) => {
            if (added && _multiSearch.getSelected().length > 5) {
                // 超过5只时移除刚添加的
                _multiSearch._selected = _multiSearch._selected.filter(s => s.code !== item.code);
                _multiSearch._renderTags();
                App.toast('最多选择5只股票', 'error');
            }
        };

        // 数据源：优先全量股票列表，搜索时实时查询
        _multiSearch.setDataSource(async (q) => {
            if (!q) {
                // 无搜索词时显示自选股 + 缓存的全量列表
                const watchlist = App.watchlistCache || [];
                if (watchlist.length > 0) return watchlist;
                // 尝试获取全量列表
                try {
                    return await App.fetchJSON('/api/stock/search?limit=200', { silent: true });
                } catch {
                    return [];
                }
            }
            try {
                return await App.fetchJSON(`/api/stock/search?q=${encodeURIComponent(q)}&limit=50`, { silent: true });
            } catch {
                return [];
            }
        });
    }

    // ── 执行对比 ──

    async function run() {
        const periodSel = document.getElementById('compare-period');
        const countSel = document.getElementById('compare-count');

        const selected = _multiSearch ? _multiSearch.getSelected() : [];
        const codes = selected.map(s => s.code).filter(Boolean);

        if (codes.length < 2) {
            App.toast('至少需要选择2只股票才能对比', 'error');
            return;
        }

        const period = periodSel?.value || 'daily';
        const count = countSel?.value || '60';
        const btn = document.getElementById('compare-run-btn');
        if (btn) { btn.disabled = true; btn.textContent = '加载中...'; }

        try {
            const params = `codes=${encodeURIComponent(codes.join(','))}&period=${period}&count=${count}`;
            const data = await App.fetchJSON(`/api/stock/compare?${params}`);

            if (data.error) {
                App.toast(data.error, 'error');
                return;
            }

            _codes = Object.keys(data.data || {});
            if (_codes.length === 0) {
                App.toast('未获取到数据', 'error');
                return;
            }

            renderChart(data.data);
            renderStats(data.data);
            App.toast(`已加载 ${_codes.length} 只股票`, 'success');
        } catch (e) {
            App.toast('对比数据加载失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '开始对比'; }
        }
    }

    // ── 渲染图表 ──

    function renderChart(stocks) {
        const canvas = document.getElementById('compare-chart');
        if (!canvas) return;

        if (_chart) {
            _chart.destroy();
            _chart = null;
        }

        // 收集所有日期
        const dateSet = new Set();
        for (const code of _codes) {
            for (const d of stocks[code]?.data || []) {
                dateSet.add(d.date);
            }
        }
        const labels = [...dateSet].sort();

        // 构建名称映射（优先API返回，其次MultiSearchBox选中项，最后watchlistCache）
        const nameMap = {};
        if (_multiSearch) {
            for (const s of _multiSearch.getSelected()) {
                if (s.code && s.name) nameMap[s.code] = s.name;
            }
        }
        for (const s of (App.watchlistCache || [])) {
            if (s.code && s.name && !nameMap[s.code]) nameMap[s.code] = s.name;
        }

        // 构建数据集
        const datasets = _codes.map((code, i) => {
            const stock = stocks[code];
            const name = stock?.name || nameMap[code] || code;
            const dateMap = {};
            for (const d of stock?.data || []) {
                dateMap[d.date] = d.value;
            }
            // 对齐到公共日期轴
            const values = [];
            let lastVal = 100;
            for (const date of labels) {
                if (dateMap[date] != null) {
                    lastVal = dateMap[date];
                }
                values.push(lastVal);
            }
            return {
                label: `${code} ${name}`,
                data: values,
                borderColor: COLORS[i % COLORS.length],
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.1,
            };
        });

        const ctx = canvas.getContext('2d');
        _chart = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            pointStyle: 'line',
                            padding: 16,
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const val = ctx.parsed.y;
                                const change = (val - 100).toFixed(2);
                                const sign = change >= 0 ? '+' : '';
                                return `${ctx.dataset.label}: ${val.toFixed(2)} (${sign}${change}%)`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            maxTicksLimit: 10,
                            maxRotation: 0,
                        },
                        grid: { display: false },
                    },
                    y: {
                        title: { display: true, text: '归一化收益（基准=100）' },
                        grid: { color: 'rgba(128,128,128,0.1)' },
                    },
                },
            },
        });
    }

    // ── 渲染统计 ──

    function renderStats(stocks) {
        const container = document.getElementById('compare-stats');
        if (!container) return;

        // 名称映射
        const nameMap = {};
        if (_multiSearch) {
            for (const s of _multiSearch.getSelected()) {
                if (s.code && s.name) nameMap[s.code] = s.name;
            }
        }
        for (const s of (App.watchlistCache || [])) {
            if (s.code && s.name && !nameMap[s.code]) nameMap[s.code] = s.name;
        }

        const rows = _codes.map((code, i) => {
            const stock = stocks[code];
            const name = stock?.name || nameMap[code] || code;
            const data = stock?.data || [];
            if (data.length < 2) return `<tr><td>${code}</td><td>${name}</td><td colspan="3">数据不足</td></tr>`;

            const first = data[0].value;
            const last = data[data.length - 1].value;
            const totalReturn = ((last - first) / first * 100).toFixed(2);

            // 计算最大回撤
            let peak = first;
            let maxDD = 0;
            for (const d of data) {
                if (d.value > peak) peak = d.value;
                const dd = (peak - d.value) / peak * 100;
                if (dd > maxDD) maxDD = dd;
            }

            // 计算日波动率
            const returns = [];
            for (let j = 1; j < data.length; j++) {
                returns.push((data[j].value - data[j - 1].value) / data[j - 1].value);
            }
            const mean = returns.reduce((s, r) => s + r, 0) / returns.length;
            const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
            const dailyVol = Math.sqrt(variance) * 100;

            const color = COLORS[i % COLORS.length];
            const retClass = totalReturn >= 0 ? 'text-up' : 'text-down';
            return `<tr>
                <td><span class="compare-dot" style="background:${color}"></span>${code}</td>
                <td>${App.escapeHTML(name)}</td>
                <td class="${retClass}">${totalReturn >= 0 ? '+' : ''}${totalReturn}%</td>
                <td>${maxDD.toFixed(2)}%</td>
                <td>${dailyVol.toFixed(2)}%</td>
            </tr>`;
        });

        container.innerHTML = `
            <div class="table-wrap">
                <table class="sortable">
                    <thead><tr><th>代码</th><th>名称</th><th>累计收益</th><th>最大回撤</th><th>日波动率</th></tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>
        `;
    }

    // ── 公开接口 ──

    App.Compare = { init, run };
})();
