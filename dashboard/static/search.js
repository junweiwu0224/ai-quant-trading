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
            ...options,
        };

        this._items = [];
        this._activeIdx = -1;
        this._dataSource = null;
        this._onSelect = null;
        this._selected = null;
        this._isOpen = false;

        this._build();
        this._bind();
    }

    _build() {
        this.dropdown.innerHTML = `
            <div class="sb-filter-wrap">
                <input type="text" class="sb-filter" placeholder="${this.options.placeholder}" autocomplete="off">
            </div>
            <div class="sb-list"></div>
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
            this._search();
        });

        // 下拉内搜索框输入
        this.filterInput.addEventListener('input', () => this._search());

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
        document.addEventListener('mousedown', (e) => {
            if (this._isOpen && !this.dropdown.contains(e.target) && e.target !== this.trigger) {
                this.close();
            }
        });
    }

    setDataSource(fn) { this._dataSource = fn; }
    onSelect(callback) { this._onSelect = callback; }
    getValue() { return this.trigger.value.trim(); }
    setValue(val) { this.trigger.value = val; }

    open() {
        if (this._isOpen) return;
        this._isOpen = true;
        this.dropdown.style.display = 'flex';
        this.filterInput.value = '';
        this._search();
        setTimeout(() => this.filterInput.focus(), 50);
    }

    close() {
        this._isOpen = false;
        this.dropdown.style.display = 'none';
        this.listEl.innerHTML = '';
        this._items = [];
        this._activeIdx = -1;
    }

    _search() {
        if (!this._dataSource) return;
        const q = this.filterInput.value.trim().toLowerCase();
        const items = this._dataSource(q).slice(0, this.options.maxResults);
        this._items = items;
        this._activeIdx = items.length > 0 ? 0 : -1;

        if (items.length === 0) {
            this.listEl.innerHTML = '<div class="sb-empty">无匹配结果</div>';
            return;
        }

        this.listEl.innerHTML = items.map((s, i) =>
            `<div class="sb-item${i === 0 ? ' active' : ''}" data-idx="${i}">${this.options.formatItem(s)}</div>`
        ).join('');
    }

    _select(item) {
        this.trigger.value = item.code;
        this._selected = item;
        this.close();
        this.trigger.dispatchEvent(new Event('change'));
        if (this._onSelect) this._onSelect(item);
    }

    _highlight() {
        this.listEl.querySelectorAll('.sb-item').forEach((el, i) =>
            el.classList.toggle('active', i === this._activeIdx)
        );
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
            ...options,
        };

        this._items = [];
        this._activeIdx = -1;
        this._dataSource = null;
        this._selected = []; // [{code, name, ...}]
        this._isOpen = false;

        this._build();
        this._bind();
    }

    _build() {
        this.dropdown.innerHTML = `
            <div class="sb-filter-wrap">
                <input type="text" class="sb-filter" placeholder="${this.options.placeholder}" autocomplete="off">
            </div>
            <div class="sb-list"></div>
        `;
        this.filterInput = this.dropdown.querySelector('.sb-filter');
        this.listEl = this.dropdown.querySelector('.sb-list');
    }

    _bind() {
        this.trigger.addEventListener('click', () => this.open());
        this.trigger.addEventListener('input', () => {
            if (!this._isOpen) this.open();
            this.filterInput.value = this.trigger.value;
            this._search();
        });
        this.filterInput.addEventListener('input', () => this._search());
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
            this._selected = this._selected.filter(s => s.code !== code);
            this._renderTags();
            this._search();
        });
        document.addEventListener('mousedown', (e) => {
            if (this._isOpen && !this.dropdown.contains(e.target) && e.target !== this.trigger) {
                this.close();
            }
        });
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
        this.filterInput.value = '';
        this._search();
        setTimeout(() => this.filterInput.focus(), 50);
    }

    close() {
        this._isOpen = false;
        this.dropdown.style.display = 'none';
        this.listEl.innerHTML = '';
        this.items = [];
        this._activeIdx = -1;
    }

    _toggle(item) {
        const idx = this._selected.findIndex(s => s.code === item.code);
        if (idx >= 0) {
            this._selected.splice(idx, 1);
        } else {
            this._selected.push(item);
        }
        this._renderTags();
        this._search();
    }

    _renderTags() {
        this.tagsContainer.innerHTML = this._selected.map(s =>
            `<span class="sb-tag">${App.escapeHTML(s.code)}<span class="sb-tag-remove" data-code="${App.escapeHTML(s.code)}">&times;</span></span>`
        ).join('');
        // 更新隐藏值
        this.trigger.value = this._selected.map(s => s.code).join(',');
    }

    _search() {
        if (!this._dataSource) return;
        const q = this.filterInput.value.trim().toLowerCase();
        const all = this._dataSource(q);
        const selectedCodes = new Set(this._selected.map(s => s.code));

        this._items = all.slice(0, this.options.maxResults);
        this._activeIdx = this._items.length > 0 ? 0 : -1;

        if (this._items.length === 0) {
            this.listEl.innerHTML = '<div class="sb-empty">无匹配结果</div>';
            return;
        }

        this.listEl.innerHTML = this._items.map((s, i) => {
            const checked = selectedCodes.has(s.code);
            return `<div class="sb-item${i === 0 ? ' active' : ''}${checked ? ' sb-checked' : ''}" data-idx="${i}">
                <span class="sb-check">${checked ? '✓' : ''}</span>${this.options.formatItem(s)}
            </div>`;
        }).join('');
    }

    _highlight() {
        this.listEl.querySelectorAll('.sb-item').forEach((el, i) =>
            el.classList.toggle('active', i === this._activeIdx)
        );
        const active = this.listEl.querySelector('.sb-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
    }
}
