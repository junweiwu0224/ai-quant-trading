/* ── 股票详情页：画线工具 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    // ── 画线工具 ──

    _drawingBound: false,
    _activeDrawing: null,  // 当前正在画的 overlay 类型
    _drawingOverlays: [],  // 已保存的 overlay ID 列表
    _undoStack: [],  // {name, points, styles, drawingId, overlayId}
    _redoStack: [],
    _suppressRemove: false,

    _bindDrawingToolbar() {
        if (this._drawingBound) return;
        this._drawingBound = true;

        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.sd-draw-btn');
            if (!btn) return;

            // 清空按钮
            if (btn.id === 'sd-draw-clear') {
                this._clearAllDrawings();
                return;
            }

            // 多日叠加按钮
            if (btn.id === 'sd-multiday-btn') {
                this._toggleMultiDayOverlay(btn);
                return;
            }

            const overlayName = btn.dataset.overlay;
            if (!overlayName) return;

            // 切换 active 状态
            const wasActive = btn.classList.contains('active');
            document.querySelectorAll('.sd-draw-btn[data-overlay]').forEach(b => b.classList.remove('active'));

            if (wasActive) {
                this._activeDrawing = null;
                return;
            }

            btn.classList.add('active');
            this._activeDrawing = overlayName;
            this._startDrawing(overlayName);
        });
    },

    _startDrawing(overlayName) {
        const chart = this._klineChart;
        if (!chart) return;

        // 配置不同画线类型的样式
        const styleMap = {
            horizontalStraightLine: { line: { color: '#e6a817', size: 1, style: 'dashed' } },
            straightLine: { line: { color: '#4fc3f7', size: 1, style: 'solid' } },
            fibonacciLine: { line: { color: '#ab47bc', size: 1, style: 'dashed' } },
        };

        const overlayId = chart.createOverlay({
            name: overlayName,
            styles: styleMap[overlayName] || {},
            lock: false,
            onDrawEnd: (event) => {
                this._onDrawingComplete(overlayName, event);
                // 取消 active 状态
                document.querySelectorAll('.sd-draw-btn[data-overlay]').forEach(b => b.classList.remove('active'));
                this._activeDrawing = null;
            },
            onRemoved: (event) => {
                this._onDrawingRemoved(event);
            },
        });
    },

    _onDrawingComplete(overlayName, event) {
        const overlay = event.overlay || event;
        const points = overlay.points || [];
        if (points.length < 1) return;

        // 保存到后端
        this._saveDrawingToBackend(overlayName, points, overlay.styles || {}).then(id => {
            // 推入撤销栈
            this._undoStack.push({
                name: overlayName,
                points: [...points],
                styles: { ...(overlay.styles || {}) },
                drawingId: id || null,
                overlayId: overlay.id || null,
            });
            this._redoStack = [];
        });
    },

    _onDrawingRemoved(event) {
        if (this._suppressRemove) return;  // 撤销操作时不删后端
        const overlay = event.overlay || event;
        const drawingId = overlay?.extendData?.drawingId;
        if (drawingId) {
            fetch(`/api/stock/drawings/${drawingId}`, { method: 'DELETE' }).catch(() => {});
        }
    },

    async _saveDrawingToBackend(overlayName, points, styles) {
        if (!this._currentCode) return null;
        try {
            const data = await App.fetchJSON(`/api/stock/drawings/${this._currentCode}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    overlay_name: overlayName,
                    points: points,
                    styles: styles,
                }),
                label: '保存画线',
            });
            if (data?.success && data.id) {
                this._drawingOverlays.push(data.id);
                return data.id;
            }
        } catch (e) {
            console.error('保存画线失败:', e);
        }
        return null;
    },

    async _loadDrawings() {
        if (!this._currentCode || !this._klineChart) return;
        try {
            const data = await App.fetchJSON(`/api/stock/drawings/${this._currentCode}`);
            if (!data?.drawings) return;

            this._drawingOverlays = [];
            const chart = this._klineChart;

            for (const d of data.drawings) {
                const points = typeof d.points === 'string' ? JSON.parse(d.points) : d.points;
                const styles = typeof d.styles === 'string' ? JSON.parse(d.styles) : (d.styles || {});
                if (!points || points.length < 1) continue;

                chart.createOverlay({
                    name: d.overlay_name,
                    points: points,
                    styles: styles,
                    lock: false,
                    extendData: { drawingId: d.id },
                    onRemoved: (event) => {
                        this._onDrawingRemoved(event);
                    },
                });
                this._drawingOverlays.push(d.id);
            }
        } catch (e) {
            console.error('加载画线失败:', e);
        }
    },

    async _clearAllDrawings() {
        if (!this._currentCode) return;
        if (!confirm('确定清空所有画线？')) return;

        const chart = this._klineChart;
        if (chart) {
            chart.removeOverlay();  // 不传参数 = 移除所有 overlay
        }

        try {
            await fetch(`/api/stock/drawings/${this._currentCode}/all`, { method: 'DELETE' });
            this._drawingOverlays = [];
            this._undoStack = [];
            this._redoStack = [];
            App.toast('画线已清空', 'success');
        } catch (e) {
            console.error('清空画线失败:', e);
        }
    },

    undoDrawing() {
        if (this._undoStack.length === 0) return;
        const item = this._undoStack.pop();
        const chart = this._klineChart;
        if (!chart) return;

        // 删除后端记录（静默）
        if (item.drawingId) {
            fetch(`/api/stock/drawings/${item.drawingId}`, { method: 'DELETE' }).catch(() => {});
            this._drawingOverlays = this._drawingOverlays.filter(id => id !== item.drawingId);
        }

        // 移除图表上的 overlay
        this._suppressRemove = true;
        if (item.overlayId) {
            chart.removeOverlay(item.overlayId);
        }
        this._suppressRemove = false;

        this._redoStack.push(item);
        App.toast('撤销画线', 'info');
    },

    redoDrawing() {
        if (this._redoStack.length === 0) return;
        const item = this._redoStack.pop();
        const chart = this._klineChart;
        if (!chart) return;

        const styleMap = {
            horizontalStraightLine: { line: { color: '#e6a817', size: 1, style: 'dashed' } },
            straightLine: { line: { color: '#4fc3f7', size: 1, style: 'solid' } },
            fibonacciLine: { line: { color: '#ab47bc', size: 1, style: 'dashed' } },
        };

        chart.createOverlay({
            name: item.name,
            points: item.points,
            styles: item.styles || styleMap[item.name] || {},
            lock: false,
            onDrawEnd: (event) => this._onDrawingComplete(item.name, event),
            onRemoved: (event) => this._onDrawingRemoved(event),
        });

        this._saveDrawingToBackend(item.name, item.points, item.styles || {}).then(id => {
            item.drawingId = id;
            this._undoStack.push(item);
        });
        App.toast('重做画线', 'info');
    },

    _bindDrawingShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            // 仅在行情详情 tab 激活时响应
            const stockTab = document.getElementById('tab-stock');
            if (!stockTab || stockTab.style.display === 'none') return;
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                this.undoDrawing();
            }
            if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
                e.preventDefault();
                this.redoDrawing();
            }
        });
    },

});
