/* ── 模拟盘：订单与下单流程 ── */

if (!globalThis.PaperTrading) {
    globalThis.PaperTrading = {};
}

Object.assign(globalThis.PaperTrading, {
    async createOrder() {
        const code = document.getElementById('pt-code').value.trim();
        const direction = document.getElementById('pt-direction').value;
        const orderType = document.getElementById('pt-order-type').value;
        const price = document.getElementById('pt-price').value;
        const volume = parseInt(document.getElementById('pt-volume').value);

        if (!code) {
            App.toast('请输入股票代码', 'error');
            return;
        }
        if (!volume || volume <= 0) {
            App.toast('请输入有效数量', 'error');
            return;
        }
        if (volume % 100 !== 0) {
            App.toast('数量必须是100的整数倍', 'error');
            return;
        }

        if (orderType === 'stop_loss' && price) {
            const quote = this._currentQuote;
            if (quote && parseFloat(price) >= quote.price) {
                App.toast(`止损价应低于当前价 ${quote.price}`, 'error');
                return;
            }
        }
        if (orderType === 'take_profit' && price) {
            const quote = this._currentQuote;
            if (quote && parseFloat(price) <= quote.price) {
                App.toast(`止盈价应高于当前价 ${quote.price}`, 'error');
                return;
            }
        }

        const body = { code, direction, order_type: orderType, volume };
        if (orderType !== 'market' && price) {
            body.price = parseFloat(price);
        }

        const submitBtn = document.querySelector('#pt-order-form button[type="submit"]');
        const origText = submitBtn ? submitBtn.textContent : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = '提交中...';
        }

        try {
            const data = await App.fetchJSON('/api/paper/orders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            App.toast(`订单创建成功: ${data.data.order_id}`, 'success');
            this.loadOrders();
            this.loadPositions();
            App.emit('data:portfolio-updated', { source: 'order' });
        } catch (e) {
            App.toast(`创建订单失败: ${e.message}`, 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = origText;
            }
        }
    },

    async cancelOrder(orderId) {
        if (!confirm('确定要撤销此订单吗？')) return;
        try {
            await App.fetchJSON(`/api/paper/orders/${orderId}`, { method: 'DELETE' });
            App.toast('订单已撤销', 'success');
            this.loadOrders();
            App.emit('data:portfolio-updated', { source: 'cancel' });
        } catch (e) {
            App.toast(`撤销订单失败: ${e.message}`, 'error');
        }
    },

    async loadOrders() {
        try {
            const data = await App.fetchJSON('/api/paper/orders?status=pending&page_size=100');
            this.state.orders = data.data.items || [];
            this.renderOrders();
        } catch (e) {
            console.error('加载订单失败:', e);
        }
    },

    renderOrders() {
        const tbody = document.querySelector('#pt-orders-table tbody');
        if (!tbody) return;
        if (this.state.orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无挂单</td></tr>';
            return;
        }
        tbody.innerHTML = this.state.orders.map(order => {
            const typeMap = { market: '市价', limit: '限价', stop_loss: '止损', take_profit: '止盈' };
            const dirClass = order.direction === 'buy' ? 'text-up' : 'text-down';
            const dirText = order.direction === 'buy' ? '买入' : '卖出';
            return `<tr>
                <td><a href="#" class="stock-link" data-code="${App.escapeHTML(order.code)}">${App.escapeHTML(order.code)}</a></td>
                <td class="${dirClass}">${dirText}</td>
                <td>${typeMap[order.order_type] || order.order_type}</td>
                <td>${order.price ? '¥' + order.price.toFixed(2) : '市价'}</td>
                <td>${order.volume}</td>
                <td><span class="badge badge-warning">待撮合</span></td>
                <td>
                    <button class="btn btn-sm btn-danger" data-paper-action="cancel-order" data-order-id="${App.escapeHTML(order.order_id)}">撤销</button>
                </td>
            </tr>`;
        }).join('');
    },

    togglePriceInput() {
        const orderType = document.getElementById('pt-order-type').value;
        const priceGroup = document.getElementById('pt-price-group');
        if (priceGroup) priceGroup.style.display = orderType === 'market' ? 'none' : 'block';
    },
});
