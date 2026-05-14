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
    let _conditionalOrders = [];
    let _delegatedActionsBound = false;

    // ── 初始化 ──

    async function init() {
        bindEvents();
        bindActionDelegation();
        await loadRules();
        await loadConditionalOrders();
        loadHistory();
        loadConditionalOrderEvents();
    }

    function bindEvents() {
        document.getElementById('alert-add-btn')?.addEventListener('click', addRule);
        document.getElementById('cond-add-btn')?.addEventListener('click', addConditionalOrder);
    }

    function bindActionDelegation() {
        if (_delegatedActionsBound) {
            return;
        }

        _delegatedActionsBound = true;
        document.addEventListener('click', (e) => {
            const actionEl = e.target.closest('[data-alert-action]');
            if (!actionEl) {
                return;
            }

            const action = actionEl.dataset.alertAction;
            const id = parseInt(actionEl.dataset.id || '', 10);
            if (!Number.isFinite(id)) {
                return;
            }

            e.preventDefault();

            if (action === 'toggle-rule') {
                const enabled = actionEl.dataset.enabled === 'true';
                toggleRule(id, enabled);
                return;
            }

            if (action === 'delete-rule') {
                deleteRule(id);
                return;
            }

            if (action === 'toggle-conditional') {
                const enabled = actionEl.dataset.enabled === 'true';
                toggleConditionalOrder(id, enabled);
                return;
            }

            if (action === 'delete-conditional') {
                deleteConditionalOrder(id);
            }
        });
    }

    // ── 规则 CRUD ──

    async function loadRules() {
        try {
            const data = await App.fetchJSON('/api/alerts/rules');
            if (data.success) {
                _rules = data.rules || [];
                renderRules();
                renderConditionalRuleOptions();
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

    async function loadConditionalOrders() {
        try {
            const data = await App.fetchJSON('/api/conditional-orders/rules');
            if (data.success) {
                _conditionalOrders = data.data || [];
                renderConditionalOrders();
            }
        } catch (e) {
            App.toast('加载条件单失败: ' + e.message, 'error');
        }
    }

    async function addConditionalOrder() {
        const alertRuleId = parseInt(document.getElementById('cond-alert-rule')?.value || '', 10);
        const alertRule = _rules.find(r => r.id === alertRuleId);
        const direction = document.getElementById('cond-direction')?.value || 'buy';
        const orderType = document.getElementById('cond-order-type')?.value || 'market';
        const priceValue = document.getElementById('cond-price')?.value;
        const volume = parseInt(document.getElementById('cond-volume')?.value || '', 10);
        const maxAmount = parseFloat(document.getElementById('cond-max-amount')?.value || '0');
        const cooldown = parseInt(document.getElementById('cond-cooldown')?.value || '300', 10);
        const enabled = document.getElementById('cond-enabled')?.checked === true;

        if (!alertRule) { App.toast('请选择预警规则', 'error'); return; }
        if (!Number.isFinite(volume) || volume <= 0 || volume % 100 !== 0) { App.toast('数量必须是100的正整数倍', 'error'); return; }
        if (orderType === 'limit' && (!priceValue || parseFloat(priceValue) <= 0)) { App.toast('限价单必须填写有效价格', 'error'); return; }

        try {
            const data = await App.fetchJSON('/api/conditional-orders/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    alert_rule_id: alertRuleId,
                    code: alertRule.code,
                    direction,
                    order_type: orderType,
                    price: orderType === 'limit' ? parseFloat(priceValue) : null,
                    volume,
                    max_amount: Number.isFinite(maxAmount) ? maxAmount : 0,
                    enabled,
                    cooldown: Number.isFinite(cooldown) ? cooldown : 300,
                }),
            });
            if (data.success) {
                App.toast('条件单已创建', 'success');
                await loadConditionalOrders();
            } else {
                App.toast(data.error || '条件单创建失败', 'error');
            }
        } catch (e) {
            App.toast('条件单创建失败: ' + e.message, 'error');
        }
    }

    async function toggleConditionalOrder(id, enabled) {
        try {
            const data = await App.fetchJSON(`/api/conditional-orders/rules/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !enabled }),
            });
            if (data.success) await loadConditionalOrders();
        } catch (e) {
            App.toast('条件单更新失败', 'error');
        }
    }

    async function deleteConditionalOrder(id) {
        try {
            const data = await App.fetchJSON(`/api/conditional-orders/rules/${id}`, { method: 'DELETE' });
            if (data.success) {
                App.toast('条件单已删除', 'success');
                await loadConditionalOrders();
            }
        } catch (e) {
            App.toast('条件单删除失败', 'error');
        }
    }

    async function loadConditionalOrderEvents() {
        const container = document.getElementById('cond-events');
        if (!container) return;
        try {
            const data = await App.fetchJSON('/api/conditional-orders/events?limit=20');
            if (data.success) {
                renderConditionalOrderEvents(data.data || []);
            }
        } catch {
            container.innerHTML = '<div class="text-muted text-center" style="padding:8px">加载失败</div>';
        }
    }

    // ── 渲染 ──

    function renderRules() {
        const tbody = document.querySelector('#alert-rules-table tbody');
        if (!tbody) return;

        if (_rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted text-center">暂无预警规则</td></tr>';
            renderConditionalRuleOptions();
            return;
        }

        tbody.innerHTML = _rules.map(r => {
            const label = _conditionLabels[r.condition] || r.condition;
            const statusClass = r.enabled ? 'text-up' : 'text-muted';
            const statusText = r.enabled ? '启用' : '禁用';
            const webhookBadge = r.webhook_url ? '<span class="text-muted" title="' + App.escapeHTML(r.webhook_url) + '">通知</span>' : '';
            return `<tr>
                <td>${App.escapeHTML(r.code)}${webhookBadge}</td>
                <td>${App.escapeHTML(label)}</td>
                <td>${r.threshold}</td>
                <td><span class="${statusClass}" style="cursor:pointer" data-alert-action="toggle-rule" data-id="${r.id}" data-enabled="${r.enabled ? 'true' : 'false'}">${statusText}</span></td>
                <td><button class="btn btn-sm" data-alert-action="delete-rule" data-id="${r.id}">删除</button></td>
            </tr>`;
        }).join('');
        renderConditionalRuleOptions();
    }

    function renderConditionalRuleOptions() {
        const select = document.getElementById('cond-alert-rule');
        if (!select) return;
        const current = select.value;
        const options = _rules.map(r => {
            const label = _conditionLabels[r.condition] || r.condition;
            return `<option value="${r.id}">${App.escapeHTML(r.code)} ${App.escapeHTML(label)} ${r.threshold}</option>`;
        }).join('');
        select.innerHTML = `<option value="">选择预警规则</option>${options}`;
        if (current && select.querySelector(`option[value="${current}"]`)) select.value = current;
    }

    function renderConditionalOrders() {
        const tbody = document.querySelector('#cond-rules-table tbody');
        if (!tbody) return;
        if (_conditionalOrders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无条件单</td></tr>';
            return;
        }

        tbody.innerHTML = _conditionalOrders.map(rule => {
            const alertRule = _rules.find(r => r.id === rule.alert_rule_id);
            const alertLabel = alertRule ? `${alertRule.code} ${_conditionLabels[alertRule.condition] || alertRule.condition}` : `#${rule.alert_rule_id}`;
            const statusClass = rule.enabled ? 'text-up' : 'text-muted';
            const statusText = rule.enabled ? '启用' : '禁用';
            return `<tr>
                <td>${App.escapeHTML(alertLabel)}</td>
                <td>${App.escapeHTML(rule.code)}</td>
                <td>${rule.direction === 'buy' ? '买入' : '卖出'}</td>
                <td>${rule.order_type === 'market' ? '市价' : '限价'}</td>
                <td>${rule.volume}</td>
                <td><span class="${statusClass}" style="cursor:pointer" data-alert-action="toggle-conditional" data-id="${rule.id}" data-enabled="${rule.enabled ? 'true' : 'false'}">${statusText}</span></td>
                <td><button class="btn btn-sm" data-alert-action="delete-conditional" data-id="${rule.id}">删除</button></td>
            </tr>`;
        }).join('');
    }

    function renderConditionalOrderEvents(events) {
        const container = document.getElementById('cond-events');
        if (!container) return;
        if (!events.length) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:8px">暂无执行记录</div>';
            return;
        }
        container.innerHTML = events.map(event => {
            const time = event.created_at ? new Date(event.created_at).toLocaleTimeString() : '--';
            const orderText = event.order_id ? `，订单 ${App.escapeHTML(event.order_id)}` : '';
            return `<div class="alert-item">
                <span class="alert-time">${time}</span>
                <span>${App.escapeHTML(event.code)} ${App.escapeHTML(event.action)}：${App.escapeHTML(event.reason)}${orderText}</span>
            </div>`;
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
        // 发射到异常聚合条
        App.emit('alert:triggered', { code: alert.code, msg: alert.message || '预警触发' });

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
            loadConditionalOrderEvents();
            // 限制显示数量
            while (container.children.length > 20) {
                container.removeChild(container.lastChild);
            }
        }

        // 浏览器通知 + 音频提醒
        App.notify('量化预警', alert.message, { level: 'warning' });
    }

    // ── 公开接口 ──

    App.Alerts = {
        init,
        loadRules,
        addRule,
        toggleRule,
        deleteRule,
        handleAlert,
        loadConditionalOrders,
        addConditionalOrder,
        toggleConditionalOrder,
        deleteConditionalOrder,
        loadConditionalOrderEvents,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
