/**
 * 市场雷达模块
 * 涨跌幅/振幅/换手率/量比 TOP 10 + 板块轮动 + 北向资金
 */
(function () {
    'use strict';

    let _currentTab = 'gainers';

    async function init() {
        bindTabs();
        loadRadar();
    }

    function bindTabs() {
        document.querySelectorAll('.radar-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.radar-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                _currentTab = tab.dataset.tab;
                loadRadar();
            });
        });
    }

    async function loadRadar() {
        const container = document.getElementById('radar-content');
        if (!container) return;
        container.innerHTML = '<div class="loading"><span class="spinner"></span>加载中...</div>';

        try {
            if (_currentTab === 'sectors') {
                await loadSectors(container);
            } else if (_currentTab === 'northbound') {
                await loadNorthbound(container);
            } else {
                await loadTopStocks(container);
            }
        } catch (e) {
            container.innerHTML = `<div class="text-muted text-center">加载失败: ${App.escapeHTML(e.message)}</div>`;
        }
    }

    async function loadTopStocks(container) {
        const data = await App.fetchJSON('/api/market/radar');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

        const fieldMap = {
            gainers: { list: data.top_gainers, label: '涨幅', suffix: '%' },
            losers: { list: data.top_losers, label: '跌幅', suffix: '%' },
            amplitude: { list: data.top_amplitude, label: '振幅', suffix: '%' },
            turnover: { list: data.top_turnover, label: '换手率', suffix: '%' },
            volume_ratio: { list: data.top_volume_ratio, label: '量比', suffix: '' },
        };

        const cfg = fieldMap[_currentTab] || fieldMap.gainers;
        const items = cfg.list || [];

        container.innerHTML = `
            <div class="table-wrap">
                <table>
                    <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>${cfg.label}</th><th>操作</th></tr></thead>
                    <tbody>${items.map((s, i) => {
                        const val = s.value != null ? s.value.toFixed(2) + cfg.suffix : '--';
                        const cls = _currentTab === 'losers' ? 'text-down' : 'text-up';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td>${App.escapeHTML(s.code || '')}</td>
                            <td>${App.escapeHTML(s.name || '')}</td>
                            <td class="${cls}">${val}</td>
                            <td><button class="btn btn-sm" onclick="App.OverviewRadar.addToWatchlist('${App.escapeHTML(s.code || '')}')">加自选</button></td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    }

    async function loadSectors(container) {
        const data = await App.fetchJSON('/api/market/sectors?type=industry');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

        const sectors = data.sectors || [];
        container.innerHTML = `
            <div class="table-wrap">
                <table>
                    <thead><tr><th>排名</th><th>板块</th><th>涨跌幅</th><th>上涨</th><th>下跌</th><th>领涨股</th></tr></thead>
                    <tbody>${sectors.slice(0, 20).map((s, i) => {
                        const cls = s.change_pct >= 0 ? 'text-up' : 'text-down';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td>${App.escapeHTML(s.name || '')}</td>
                            <td class="${cls}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>
                            <td class="text-up">${s.up_count}</td>
                            <td class="text-down">${s.down_count}</td>
                            <td>${App.escapeHTML(s.leader || '--')}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    }

    async function loadNorthbound(container) {
        const data = await App.fetchJSON('/api/market/northbound');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

        const net = data.today_net || 0;
        const shNet = data.today_sh_net || 0;
        const szNet = data.today_sz_net || 0;
        const cls = net >= 0 ? 'text-up' : 'text-down';

        const flow = data.flow || [];
        // 最近 10 个时间点的迷你图数据
        const recentFlow = flow.slice(-10);

        container.innerHTML = `
            <div class="radar-northbound">
                <div class="radar-nb-summary">
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">今日净流入</span>
                        <span class="radar-nb-value ${cls}">${net >= 0 ? '+' : ''}${net.toFixed(2)} 亿</span>
                    </div>
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">沪股通</span>
                        <span class="radar-nb-value ${shNet >= 0 ? 'text-up' : 'text-down'}">${shNet >= 0 ? '+' : ''}${shNet.toFixed(2)} 亿</span>
                    </div>
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">深股通</span>
                        <span class="radar-nb-value ${szNet >= 0 ? 'text-up' : 'text-down'}">${szNet >= 0 ? '+' : ''}${szNet.toFixed(2)} 亿</span>
                    </div>
                </div>
                ${recentFlow.length > 0 ? `
                <div class="radar-nb-flow">
                    <span class="text-muted" style="font-size:var(--font-size-xs)">最近走势：</span>
                    ${recentFlow.map(f => {
                        const c = f.total_net >= 0 ? 'text-up' : 'text-down';
                        return `<span class="radar-nb-dot ${c}" title="${f.time} ${f.total_net}亿">${f.total_net >= 0 ? '▲' : '▼'}</span>`;
                    }).join('')}
                </div>` : ''}
            </div>
        `;
    }

    async function addToWatchlist(code) {
        if (!code) return;
        try {
            const resp = await fetch(`/api/watchlist/${code}`, { method: 'POST' });
            const data = await resp.json();
            if (data.success) {
                App.toast(`${code} 已加入自选股`, 'success');
            } else {
                App.toast(data.error || '添加失败', 'error');
            }
        } catch {
            App.toast('加入自选股失败', 'error');
        }
    }

    App.OverviewRadar = { init, loadRadar, addToWatchlist };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
