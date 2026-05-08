/* ── 通用工具模块 ── */

const Utils = {
    /** 表格排序：点击表头排序 */
    initTableSort(table) {
        if (!table) return;
        const headers = table.querySelectorAll('th[data-sort]');
        headers.forEach(th => {
            th.style.cursor = 'pointer';
            th.style.userSelect = 'none';
            th.addEventListener('click', () => {
                const key = th.dataset.sort;
                const tbody = table.querySelector('tbody');
                if (!tbody) return;
                const rows = [...tbody.querySelectorAll('tr')];
                const idx = [...th.parentNode.children].indexOf(th);
                const currentDir = th.dataset.dir || 'asc';
                const newDir = currentDir === 'asc' ? 'desc' : 'asc';

                // 清除其他列的排序状态
                headers.forEach(h => { h.dataset.dir = ''; h.classList.remove('sort-asc', 'sort-desc'); });
                th.dataset.dir = newDir;
                th.classList.add(newDir === 'asc' ? 'sort-asc' : 'sort-desc');

                rows.sort((a, b) => {
                    const aVal = a.cells[idx]?.textContent.trim() || '';
                    const bVal = b.cells[idx]?.textContent.trim() || '';
                    const aNum = parseFloat(aVal.replace(/[¥,%↑↓+\s]/g, ''));
                    const bNum = parseFloat(bVal.replace(/[¥,%↑↓+\s]/g, ''));
                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return newDir === 'asc' ? aNum - bNum : bNum - aNum;
                    }
                    return newDir === 'asc' ? aVal.localeCompare(bVal, 'zh') : bVal.localeCompare(aVal, 'zh');
                });
                rows.forEach(r => tbody.appendChild(r));
            });
        });
    },

    /** 骨架屏：表格行 */
    skeletonRows(count = 5, cols = 4) {
        return Array.from({ length: count }, () => {
            const cells = Array.from({ length: cols }, (_, i) =>
                `<div class="skeleton-cell skeleton-pulse${i === 0 ? ' short' : ''}"></div>`
            ).join('');
            return `<div class="skeleton-row">${cells}</div>`;
        }).join('');
    },

    /** 骨架屏：统计卡片网格 */
    skeletonCards(count = 6) {
        return Array.from({ length: count }, () =>
            '<div class="skeleton-card"><div class="skel-label skeleton-pulse skeleton-block"></div><div class="skel-value skeleton-pulse skeleton-block"></div></div>'
        ).join('');
    },

    /** 骨架屏：图表（柱状图样式） */
    skeletonChart(barCount = 12) {
        const bars = Array.from({ length: barCount }, () => {
            const h = 30 + Math.random() * 70;
            return `<div class="skel-bar skeleton-pulse" style="height:${h}%"></div>`;
        }).join('');
        return `<div class="skeleton-chart">${bars}</div>`;
    },

    /** 骨架屏：表格 */
    skeletonTable(rows = 5, cols = 5) {
        const headerRow = '<tr>' + Array.from({ length: cols }, () => '<td><div class="skel-cell skeleton-pulse" style="width:60%"></div></td>').join('') + '</tr>';
        const bodyRows = Array.from({ length: rows }, () => {
            const cells = Array.from({ length: cols }, (_, i) =>
                `<td><div class="skel-cell skeleton-pulse" style="width:${50 + Math.random() * 40}%"></div></td>`
            ).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<table class="skeleton-table skeleton-fade-in">${headerRow}${bodyRows}</table>`;
    },

    /** 防抖 */
    debounce(fn, delay = 300) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    },

    /** 复制文本到剪贴板 */
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            // fallback
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            ta.remove();
            return ok;
        }
    },

    /**
     * 表格增强：分页 + 搜索 + 排序
     * @param {string} tableSelector - 表格选择器
     * @param {object} opts
     * @param {number} [opts.pageSize=20] - 每页行数
     * @param {boolean} [opts.searchable=true] - 是否显示搜索框
     * @param {boolean} [opts.sortable=true] - 是否启用排序
     */
    enhanceTable(tableSelector, opts = {}) {
        const table = typeof tableSelector === 'string'
            ? document.querySelector(tableSelector)
            : tableSelector;
        if (!table) return;

        const { pageSize = 20, searchable = true, sortable = true } = opts;
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        // 获取所有数据行（排除骨架屏和空状态行）
        const getAllRows = () => [...tbody.querySelectorAll('tr')].filter(r =>
            !r.querySelector('.skeleton-wrap, .skeleton-cell, .skeleton-pulse') &&
            !r.querySelector('.text-muted') &&
            r.cells.length > 1
        );

        // 创建分页容器
        const wrapper = table.closest('.table-wrap') || table.parentElement;
        let paginationEl = wrapper.querySelector('.table-pagination');
        if (!paginationEl) {
            paginationEl = document.createElement('div');
            paginationEl.className = 'table-pagination';
            wrapper.appendChild(paginationEl);
        }

        let currentPage = 1;
        let searchTerm = '';

        const render = () => {
            const allRows = getAllRows();
            // 搜索过滤
            const filtered = searchTerm
                ? allRows.filter(r => r.textContent.toLowerCase().includes(searchTerm))
                : allRows;

            const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
            if (currentPage > totalPages) currentPage = totalPages;

            const start = (currentPage - 1) * pageSize;
            const pageRows = filtered.slice(start, start + pageSize);

            // 隐藏所有行，显示当前页
            allRows.forEach(r => r.style.display = 'none');
            pageRows.forEach(r => r.style.display = '');

            // 渲染分页控件
            if (totalPages <= 1) {
                paginationEl.innerHTML = filtered.length > 0
                    ? `<span class="table-pagination-info">${filtered.length} 条记录</span>`
                    : '';
                return;
            }

            let html = `<span class="table-pagination-info">${filtered.length} 条记录，第 ${currentPage}/${totalPages} 页</span>`;
            html += '<div class="table-pagination-btns">';
            html += `<button class="btn btn-sm" data-page="1" ${currentPage === 1 ? 'disabled' : ''} title="首页">«</button>`;
            html += `<button class="btn btn-sm" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''} title="上一页">‹</button>`;

            // 页码按钮（最多显示5个）
            let startPage = Math.max(1, currentPage - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

            for (let p = startPage; p <= endPage; p++) {
                html += `<button class="btn btn-sm${p === currentPage ? ' active' : ''}" data-page="${p}">${p}</button>`;
            }

            html += `<button class="btn btn-sm" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''} title="下一页">›</button>`;
            html += `<button class="btn btn-sm" data-page="${totalPages}" ${currentPage === totalPages ? 'disabled' : ''} title="末页">»</button>`;
            html += '</div>';
            paginationEl.innerHTML = html;
        };

        // 绑定分页点击
        paginationEl.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-page]');
            if (!btn || btn.disabled) return;
            currentPage = parseInt(btn.dataset.page);
            render();
        });

        // 搜索框
        if (searchable) {
            let searchEl = wrapper.querySelector('.table-search-input');
            if (!searchEl) {
                const searchWrap = document.createElement('div');
                searchWrap.className = 'table-search-wrap';
                searchWrap.innerHTML = '<input type="text" class="table-search-input form-input" placeholder="搜索表格内容..." aria-label="搜索">';
                wrapper.insertBefore(searchWrap, table);
                searchEl = searchWrap.querySelector('input');
            }
            searchEl.addEventListener('input', this.debounce((e) => {
                searchTerm = e.target.value.toLowerCase().trim();
                currentPage = 1;
                render();
            }, 200));
        }

        // 排序
        if (sortable) {
            this.initTableSort(table);
            // 排序后重新渲染分页
            table.querySelectorAll('th[data-sort]').forEach(th => {
                th.addEventListener('click', () => {
                    setTimeout(() => { currentPage = 1; render(); }, 10);
                });
            });
        }

        // 初始渲染
        render();

        // 返回刷新方法
        return {
            refresh: render,
            goToPage: (p) => { currentPage = p; render(); },
            reset: () => { currentPage = 1; searchTerm = ''; render(); },
        };
    },
};
