/**
 * 预警管理模块
 * 规则 CRUD + 触发历史 + WebSocket 预警接收
 */
(function () {
    'use strict';

    const _conditionLabels = {
        price_above: '价格突破',
        price_below: '价格跌破',
        change_above: '涨幅超过',
        change_below: '跌幅超过',
        volume_ratio_above: '量比超过',
        turnover_above: '换手率超过',
        amplitude_above: '振幅超过',
    };

    let _rules = [];

    // ── 初始化 ──

    async function init() {
        bindEvents();
        await loadRules();
        loadHistory();
    }

    function bindEvents() {
        document.getElementById('alert-add-btn')?.addEventListener('click', addRule);
    }

    // ── 规则 CRUD ──

    async function loadRules() {
        try {
            const data = await App.fetchJSON('/api/alerts/rules');
            if (data.success) {
                _rules = data.rules || [];
                renderRules();
            }
        } catch (e) {
            console.error('加载预警规则失败:', e);
        }
    }

    async function addRule() {
        const code = document.getElementById('alert-code')?.value?.trim();
        const condition = document.getElementById('alert-condition')?.value;
        const thresholdStr = document.getElementById('alert-threshold')?.value;
        const webhookUrl = document.getElementById('alert-webhook')?.value?.trim() || '';

        if (!code) { App.toast('请输入股票代码', 'error'); return; }
        if (!thresholdStr) { App.toast('请输入阈值', 'error'); return; }

        const threshold = parseFloat(thresholdStr);
        if (isNaN(threshold)) { App.toast('阈值必须是数字', 'error'); return; }

        try {
            const data = await App.fetchJSON('/api/alerts/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, condition, threshold, webhook_url: webhookUrl }),
            });
            if (data.success) {
                App.toast('预警添加成功', 'success');
                await loadRules();
                // 清空输入
                const codeInput = document.getElementById('alert-code');
                const threshInput = document.getElementById('alert-threshold');
                const webhookInput = document.getElementById('alert-webhook');
                if (codeInput) codeInput.value = '';
                if (threshInput) threshInput.value = '';
                if (webhookInput) webhookInput.value = '';
            } else {
                App.toast(data.error || '添加失败', 'error');
            }
        } catch (e) {
            App.toast('添加预警失败: ' + e.message, 'error');
        }
    }

    async function toggleRule(id, enabled) {
        try {
            const data = await App.fetchJSON(`/api/alerts/rules/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !enabled }),
            });
            if (data.success) {
                await loadRules();
            }
        } catch (e) {
            App.toast('更新失败', 'error');
        }
    }

    async function deleteRule(id) {
        try {
            const data = await App.fetchJSON(`/api/alerts/rules/${id}`, {
                method: 'DELETE',
            });
            if (data.success) {
                App.toast('已删除', 'success');
                await loadRules();
            }
        } catch (e) {
            App.toast('删除失败', 'error');
        }
    }

    // ── 渲染 ──

    function renderRules() {
        const tbody = document.querySelector('#alert-rules-table tbody');
        if (!tbody) return;

        if (_rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted text-center">暂无预警规则</td></tr>';
            return;
        }

        tbody.innerHTML = _rules.map(r => {
            const label = _conditionLabels[r.condition] || r.condition;
            const statusClass = r.enabled ? 'text-up' : 'text-muted';
            const statusText = r.enabled ? '启用' : '禁用';
            const webhookBadge = r.webhook_url ? '<span class="text-muted" title="' + App.escapeHTML(r.webhook_url) + '"> 🔔</span>' : '';
            return `<tr>
                <td>${App.escapeHTML(r.code)}${webhookBadge}</td>
                <td>${App.escapeHTML(label)}</td>
                <td>${r.threshold}</td>
                <td><span class="${statusClass}" style="cursor:pointer" onclick="App.Alerts.toggleRule(${r.id}, ${r.enabled})">${statusText}</span></td>
                <td><button class="btn btn-sm" onclick="App.Alerts.deleteRule(${r.id})">删除</button></td>
            </tr>`;
        }).join('');
    }

    async function loadHistory() {
        const container = document.getElementById('alert-history');
        if (!container) return;
        try {
            const data = await App.fetchJSON('/api/alerts/history?limit=20');
            if (data.success && data.alerts?.length) {
                container.innerHTML = data.alerts.map(a =>
                    `<div class="alert-item">
                        <span class="alert-time">${new Date(a.timestamp * 1000).toLocaleTimeString()}</span>
                        <span>${App.escapeHTML(a.message)}</span>
                    </div>`
                ).join('');
            } else {
                container.innerHTML = '<div class="text-muted text-center" style="padding:8px">暂无触发记录</div>';
            }
        } catch {
            container.innerHTML = '<div class="text-muted text-center" style="padding:8px">加载失败</div>';
        }
    }

    // ── WebSocket 预警接收（由 realtime.js 直接调用 App.Alerts.handleAlert） ──

    function handleAlert(alert) {
        // 顶部通知
        App.toast(`[预警] ${alert.message}`, 'warning');

        // 更新历史列表
        const container = document.getElementById('alert-history');
        if (container) {
            const item = document.createElement('div');
            item.className = 'alert-item alert-new';
            item.innerHTML = `
                <span class="alert-time">${new Date(alert.timestamp * 1000).toLocaleTimeString()}</span>
                <span>${App.escapeHTML(alert.message)}</span>
            `;
            container.prepend(item);
            // 限制显示数量
            while (container.children.length > 20) {
                container.removeChild(container.lastChild);
            }
        }

        // 浏览器通知（如果授权）
        if (Notification && Notification.permission === 'granted') {
            new Notification('量化预警', { body: alert.message });
        }
    }

    // ── 公开接口 ──

    App.Alerts = { init, loadRules, addRule, toggleRule, deleteRule, handleAlert };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
