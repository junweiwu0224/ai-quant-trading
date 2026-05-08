/* ── 通用搜索下拉组件（搜索内置在下拉中） ── */

class SearchBox {
    constructor(inputId, dropdownId, options = {}) {
        this.trigger = document.getElementById(inputId);
        this.dropdown = document.getElementById(dropdownId);
        if (!this.trigger || !this.dropdown) return;

        this.options = {
            maxResults: 20,
            placeholder: '搜索代码或名称...',
            formatItem: (s) => `${s.code} ${s.name}`,
            debounceMs: 300,
            ...options,
        };

        this._items = [];
        this._activeIdx = -1;
        this._dataSource = null;
        this._onSelect = null;
        this._selected = null;
        this._isOpen = false;
        this._debounceTimer = null;
        this._searchVersion = 0;

        this._build();
        this._bind();
    }

    _build() {
        const listId = this.trigger.id + '-list';
        this.dropdown.innerHTML = `
            <div class="sb-filter-wrap">
                <input type="text" class="sb-filter" placeholder="${this.options.placeholder}" autocomplete="off"
                    role="combobox" aria-expanded="false" aria-controls="${listId}" aria-autocomplete="list">
            </div>
            <div class="sb-list" id="${listId}" role="listbox"></div>
        `;
        this.filterInput = this.dropdown.querySelector('.sb-filter');
        this.listEl = this.dropdown.querySelector('.sb-list');
    }

    _bind() {
        // 点击输入框打开下拉
        this.trigger.addEventListener('click', () => this.open());

        // 输入框也可直接输入过滤
        this.trigger.addEventListener('input', () => {
            if (!this._isOpen) this.open();
            this.filterInput.value = this.trigger.value;
            this._debouncedSearch();
        });

        // 下拉内搜索框输入
        this.filterInput.addEventListener('input', () => this._debouncedSearch());

        // 键盘导航
        this.filterInput.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this._activeIdx = Math.min(this._activeIdx + 1, this._items.length - 1);
                this._highlight();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this._activeIdx = Math.max(this._activeIdx - 1, 0);
                this._highlight();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (this._activeIdx >= 0 && this._items[this._activeIdx]) {
                    this._select(this._items[this._activeIdx]);
                }
            } else if (e.key === 'Escape') {
                this.close();
            }
        });

        // 点击列表项
        this.listEl.addEventListener('mousedown', (e) => {
            const item = e.target.closest('.sb-item');
            if (!item) return;
            const idx = parseInt(item.dataset.idx, 10);
            if (this._items[idx]) this._select(this._items[idx]);
        });

        // 点击外部关闭
        this._onDocMousedown = (e) => {
            if (this._isOpen && !this.dropdown.contains(e.target) && e.target !== this.trigger) {
                this.close();
            }
        };
        document.addEventListener('mousedown', this._onDocMousedown);
    }

    setDataSource(fn) { this._dataSource = fn; }
    onSelect(callback) { this._onSelect = callback; }
    setValue(val) { this.trigger.value = val; }

    open() {
        if (this._isOpen) return;
        this._isOpen = true;
        this.dropdown.style.display = 'flex';
        this.filterInput.setAttribute('aria-expanded', 'true');
        this.filterInput.value = '';
        this._search();
        setTimeout(() => this.filterInput.focus(), 50);
    }

    close() {
        this._isOpen = false;
        this.dropdown.style.display = 'none';
        this.filterInput.setAttribute('aria-expanded', 'false');
        this._searchVersion++;  // 使旧的异步搜索请求失效
        this.listEl.innerHTML = '';
        this._items = [];
        this._activeIdx = -1;
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
    }

    destroy() {
        this.close();
        document.removeEventListener('mousedown', this._onDocMousedown);
    }

    _debouncedSearch() {
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
            this._search();
        }, this.options.debounceMs);
    }

    async _search() {
        if (!this._dataSource) return;
        const q = this.filterInput.value.trim().toLowerCase();
        const version = ++this._searchVersion;

        // 显示加载状态
        this.listEl.innerHTML = '<div class="sb-loading">搜索中...</div>';

        try {
            const result = this._dataSource(q);
            // 支持异步数据源
            const items = result instanceof Promise ? await result : result;

            // 检查是否是最新的搜索请求
            if (version !== this._searchVersion) return;

            const sliced = items.slice(0, this.options.maxResults);
            this._items = sliced;
            this._activeIdx = sliced.length > 0 ? 0 : -1;

            if (sliced.length === 0) {
                this.listEl.innerHTML = '<div class="sb-empty">无匹配结果</div>';
                return;
            }

            this.listEl.innerHTML = sliced.map((s, i) =>
                `<div class="sb-item${i === 0 ? ' active' : ''}" data-idx="${i}" role="option" aria-selected="${i === 0}">${App.escapeHTML(this.options.formatItem(s))}</div>`
            ).join('');
        } catch (e) {
            this.listEl.innerHTML = '<div class="sb-empty">搜索失败，请重试</div>';
        }
    }

    _select(item) {
        this.trigger.value = item.code;
        this._selected = item;
        this.close();
        this.trigger.dispatchEvent(new Event('change'));
        if (this._onSelect) this._onSelect(item);
    }

    _highlight() {
        this.listEl.querySelectorAll('.sb-item').forEach((el, i) => {
            const isActive = i === this._activeIdx;
            el.classList.toggle('active', isActive);
            el.setAttribute('aria-selected', isActive);
        });
        // 滚动到可见
        const active = this.listEl.querySelector('.sb-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
    }
}

/* ── 多选搜索下拉组件 ── */

class MultiSearchBox {
    constructor(triggerId, dropdownId, tagsId, options = {}) {
        this.trigger = document.getElementById(triggerId);
        this.dropdown = document.getElementById(dropdownId);
        this.tagsContainer = document.getElementById(tagsId);
        if (!this.trigger || !this.dropdown) return;

        this.options = {
            maxResults: 30,
            placeholder: '搜索代码或名称...',
            formatItem: (s) => `${s.code} ${s.name || ''}`,
            debounceMs: 300,
            ...options,
        };

        this._items = [];
        this._activeIdx = -1;
        this._dataSource = null;
        this._selected = []; // [{code, name, ...}]
        this._isOpen = false;
        this._debounceTimer = null;
        this._searchVersion = 0;

        this._build();
        this._bind();
    }

    _build() {
        const listId = this.trigger.id + '-list';
        this.dropdown.innerHTML = `
            <div class="sb-filter-wrap">
                <input type="text" class="sb-filter" placeholder="${this.options.placeholder}" autocomplete="off"
                    role="combobox" aria-expanded="false" aria-controls="${listId}" aria-autocomplete="list">
            </div>
            <div class="sb-list" id="${listId}" role="listbox"></div>
        `;
        this.filterInput = this.dropdown.querySelector('.sb-filter');
        this.listEl = this.dropdown.querySelector('.sb-list');
    }

    _bind() {
        this.trigger.addEventListener('click', () => this.open());
        this.trigger.addEventListener('input', () => {
            if (!this._isOpen) this.open();
            this.filterInput.value = this.trigger.value;
            this._debouncedSearch();
        });
        this.filterInput.addEventListener('input', () => this._debouncedSearch());
        this.filterInput.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this._activeIdx = Math.min(this._activeIdx + 1, this._items.length - 1);
                this._highlight();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this._activeIdx = Math.max(this._activeIdx - 1, 0);
                this._highlight();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (this._activeIdx >= 0 && this._items[this._activeIdx]) {
                    this._toggle(this._items[this._activeIdx]);
                }
            } else if (e.key === 'Escape') {
                this.close();
            }
        });
        this.listEl.addEventListener('mousedown', (e) => {
            const item = e.target.closest('.sb-item');
            if (!item) return;
            const idx = parseInt(item.dataset.idx, 10);
            if (this._items[idx]) this._toggle(this._items[idx]);
        });
        this.tagsContainer.addEventListener('click', (e) => {
            const tag = e.target.closest('.sb-tag-remove');
            if (!tag) return;
            const code = tag.dataset.code;
            const item = this._selected.find(s => s.code === code);
            this._selected = this._selected.filter(s => s.code !== code);
            this._renderTags();
            this._search();
            if (this.onToggle && item) {
                this.onToggle(item, false);
            }
        });
        this._onDocMousedown = (e) => {
            if (this._isOpen && !this.dropdown.contains(e.target) && e.target !== this.trigger) {
                this.close();
            }
        };
        document.addEventListener('mousedown', this._onDocMousedown);
    }

    setDataSource(fn) { this._dataSource = fn; }

    getSelected() { return [...this._selected]; }
    getSelectedCodes() { return this._selected.map(s => s.code); }

    setSelected(items) {
        this._selected = [...items];
        this._renderTags();
    }

    open() {
        if (this._isOpen) return;
        this._isOpen = true;
        this.dropdown.style.display = 'flex';
        this.filterInput.setAttribute('aria-expanded', 'true');
        this.filterInput.value = '';
        this._search();
        setTimeout(() => this.filterInput.focus(), 50);
    }

    close() {
        this._isOpen = false;
        this.dropdown.style.display = 'none';
        this.filterInput.setAttribute('aria-expanded', 'false');
        this._searchVersion++;  // 使旧的异步搜索请求失效
        this.listEl.innerHTML = '';
        this._items = [];
        this._activeIdx = -1;
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
    }

    destroy() {
        this.close();
        document.removeEventListener('mousedown', this._onDocMousedown);
    }

    _toggle(item) {
        const idx = this._selected.findIndex(s => s.code === item.code);
        const wasSelected = idx >= 0;
        if (wasSelected) {
            this._selected.splice(idx, 1);
        } else {
            this._selected.push(item);
        }
        this._renderTags();
        this._search();
        // 回调通知外部
        if (this.onToggle) {
            this.onToggle(item, !wasSelected);
        }
    }

    _renderTags() {
        this.tagsContainer.innerHTML = this._selected.map(s => {
            const label = s.name ? `${s.code} ${s.name}` : s.code;
            return `<span class="sb-tag">${App.escapeHTML(label)}<span class="sb-tag-remove" data-code="${App.escapeHTML(s.code)}">&times;</span></span>`;
        }).join('');
        // 输入框保持为空，标签区已展示选中项
        this.trigger.value = '';
    }

    _debouncedSearch() {
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
            this._search();
        }, this.options.debounceMs);
    }

    async _search() {
        if (!this._dataSource) return;
        const q = this.filterInput.value.trim().toLowerCase();
        const version = ++this._searchVersion;

        // 显示加载状态
        this.listEl.innerHTML = '<div class="sb-loading">搜索中...</div>';

        try {
            const result = this._dataSource(q);
            // 支持异步数据源
            const all = result instanceof Promise ? await result : result;

            // 检查是否是最新的搜索请求
            if (version !== this._searchVersion) return;

            const selectedCodes = new Set(this._selected.map(s => s.code));

            // 过滤掉已选中的股票
            const filtered = all.filter(s => !selectedCodes.has(s.code));
            this._items = filtered.slice(0, this.options.maxResults);
            this._activeIdx = this._items.length > 0 ? 0 : -1;

            if (this._items.length === 0) {
                this.listEl.innerHTML = '<div class="sb-empty">无匹配结果</div>';
                return;
            }

            this.listEl.innerHTML = this._items.map((s, i) =>
                `<div class="sb-item${i === 0 ? ' active' : ''}" data-idx="${i}" role="option" aria-selected="${i === 0}">${App.escapeHTML(this.options.formatItem(s))}</div>`
            ).join('');
        } catch (e) {
            this.listEl.innerHTML = '<div class="sb-empty">搜索失败，请重试</div>';
        }
    }

    _highlight() {
        this.listEl.querySelectorAll('.sb-item').forEach((el, i) => {
            const isActive = i === this._activeIdx;
            el.classList.toggle('active', isActive);
            el.setAttribute('aria-selected', isActive);
        });
        const active = this.listEl.querySelector('.sb-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
    }
}
