/* ── AI Alpha：因子挖掘 / 公式 / 篮子 / 优化 ── */

Object.assign(App, {
    // ── 自动因子挖掘 ──

    async loadMine() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('因子挖掘中...', 'info');
            const data = await this.postJSON('/api/alpha/mine', { code, start_date: startDate, end_date: endDate, top_n: 30 });
            this.renderMine(data);
            this.toast('因子挖掘完成', 'success');
        } catch (e) {
            this.toast('因子挖掘失败: ' + e.message, 'error');
        }
    },

    renderMine(data) {
        const tbody = document.querySelector('#alpha-mine-table tbody');
        if (!tbody) return;
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted">未发现有效因子</td></tr>';
            return;
        }
        const esc = App.escapeHTML;
        tbody.innerHTML = data.map((f, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${esc(f.name)}</td>
                <td>${esc(f.ic)}</td>
                <td>${esc(f.abs_ic)}</td>
            </tr>
        `).join('');
    },

    initFormulaBasketPickers() {
        if (this._formulaBasketPickersBound) return;
        this._formulaBasketPickersBound = true;

        if (document.getElementById('formula-code') && document.getElementById('formula-code-dropdown') && typeof SearchBox !== 'undefined') {
            this.formulaCodeSearch = new SearchBox('formula-code', 'formula-code-dropdown', {
                maxResults: 30,
                minQueryLength: 1,
                emptyScope: 'watchlist',
                idleMessage: '自选股为空，输入代码或名称搜索全市场',
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            this.formulaCodeSearch.setDataSource((q) => this.searchStockPickerCandidates(q, {
                limit: 50,
                emptyLimit: 50,
                emptyScope: 'watchlist',
                silent: true,
            }));
            this.formulaCodeSearch.onSelect((item) => {
                const input = document.getElementById('formula-code');
                if (input) input.value = item.code;
            });
        }

        if (document.getElementById('basket-code-input') && document.getElementById('basket-code-dropdown') && document.getElementById('basket-code-tags') && typeof MultiSearchBox !== 'undefined') {
            this.basketMultiSearch = new MultiSearchBox('basket-code-input', 'basket-code-dropdown', 'basket-code-tags', {
                maxResults: 40,
                minQueryLength: 1,
                emptyScope: 'watchlist',
                idleMessage: '自选股为空，输入代码或名称搜索全市场',
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            this.basketMultiSearch.setDataSource((q) => this.searchStockPickerCandidates(q, {
                limit: 50,
                emptyLimit: 50,
                emptyScope: 'watchlist',
                silent: true,
            }));
            this.basketMultiSearch.onToggle = () => this._syncBasketCandidatesFromPicker();
        }
    },

    // ── 公式系统 ──

    async loadFormulaEvaluate() {
        const code = document.getElementById('formula-code')?.value?.trim();
        const formula = document.getElementById('formula-source')?.value?.trim();
        const startDate = document.getElementById('formula-start')?.value || '';
        const endDate = document.getElementById('formula-end')?.value || '';
        if (!code || !formula) { this.toast('请填写股票代码和公式', 'error'); return; }

        try {
            this.toast('公式执行中...', 'info');
            const data = await this.postJSON('/api/alpha/formula/evaluate', { code, formula, start_date: startDate, end_date: endDate });
            this.renderFormulaEvaluate(data);
            this.toast(data?.success ? '公式执行完成' : '公式执行失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('公式执行失败: ' + e.message, 'error');
        }
    },

    async loadFormulaScreen() {
        const formula = document.getElementById('formula-source')?.value?.trim();
        const startDate = document.getElementById('formula-start')?.value || '';
        const endDate = document.getElementById('formula-end')?.value || '';
        if (!formula) { this.toast('请先填写公式', 'error'); return; }

        try {
            this.toast('全市场公式选股中...', 'info');
            const data = await this.postJSON('/api/alpha/formula/screen', { formula, start_date: startDate, end_date: endDate });
            this.renderFormulaScreen(data);
            this.toast('全市场选股完成', 'success');
        } catch (e) {
            this.toast('公式选股失败: ' + e.message, 'error');
        }
    },

    async loadFormulaCatalog() {
        try {
            const data = await this.fetchJSON('/api/alpha/formula/catalog');
            this.renderFormulaCatalog(data);
            this.toast('公式目录已加载', 'success');
        } catch (e) {
            this.toast('公式目录加载失败: ' + e.message, 'error');
        }
    },

    renderFormulaEvaluate(data) {
        const successEl = document.getElementById('formula-success');
        const latestEl = document.getElementById('formula-latest-value');
        const matchEl = document.getElementById('formula-match-count');
        const errorEl = document.getElementById('formula-error-list');
        const seriesBody = document.querySelector('#formula-series-table tbody');

        if (successEl) successEl.textContent = data?.success ? '是' : '否';
        if (latestEl) latestEl.textContent = data?.latest_value ?? '--';
        if (matchEl) matchEl.textContent = Array.isArray(data?.series) ? String(data.series.length) : '0';
        if (errorEl) errorEl.textContent = data?.error || '暂无错误';

        if (seriesBody) {
            const esc = App.escapeHTML;
            const rows = Array.isArray(data?.series) ? data.series : [];
            seriesBody.innerHTML = rows.length > 0
                ? rows.map(row => `<tr><td>${esc(row.date)}</td><td>${esc(row.value ?? row.latest_value ?? '--')}</td></tr>`).join('')
                : '<tr><td colspan="2" class="text-muted">暂无结果</td></tr>';
        }
    },

    renderFormulaScreen(data) {
        const matchEl = document.getElementById('formula-match-count');
        const errorEl = document.getElementById('formula-error-list');
        const body = document.querySelector('#formula-screen-table tbody');
        const errors = Array.isArray(data?.errors) ? data.errors : [];

        if (matchEl) matchEl.textContent = String(data?.total ?? 0);
        if (errorEl) {
            errorEl.innerHTML = errors.length > 0
                ? errors.map(item => `<div>${App.escapeHTML(item.code)}: ${App.escapeHTML(item.error)}</div>`).join('')
                : '暂无错误';
        }

        if (body) {
            const matches = Array.isArray(data?.matches) ? data.matches : [];
            const esc = App.escapeHTML;
            body.innerHTML = matches.length > 0
                ? matches.map(item => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td><td>${esc(item.industry)}</td><td>${esc(item.latest_value)}</td></tr>`).join('')
                : '<tr><td colspan="4" class="text-muted">无命中结果</td></tr>';
        }
    },

    renderFormulaCatalog(data) {
        const body = document.querySelector('#formula-catalog-table tbody');
        if (!body) return;
        const funcs = Array.isArray(data?.functions) ? data.functions : [];
        const esc = App.escapeHTML;
        body.innerHTML = funcs.length > 0
            ? funcs.map(item => `<tr><td>${esc(item.name)}</td><td>${esc(item.args)}</td><td>${esc(item.desc)}</td></tr>`).join('')
            : '<tr><td colspan="3" class="text-muted">暂无公式目录</td></tr>';
    },

    // ── 篮子交易 ──

    _normalizeBasketCandidate(item, index = 0) {
        const code = String(item?.code || '').trim();
        if (!/^\d{6}$/.test(code)) return null;
        const probability = Number(item?.probability ?? item?.score);
        const candidate = {
            code,
            name: String(item?.name || code).trim(),
            industry: String(item?.industry || item?.sector || '').trim(),
        };
        if (Number.isFinite(probability)) {
            candidate.probability = probability;
        } else if (Number.isFinite(Number(item?.rank_score))) {
            candidate.rank_score = Number(item.rank_score);
        } else {
            candidate.rank = index + 1;
        }
        return candidate;
    },

    _setBasketCandidates(items, { syncPicker = true } = {}) {
        const seen = new Set();
        const candidates = (Array.isArray(items) ? items : [])
            .map((item, index) => this._normalizeBasketCandidate(item, index))
            .filter(Boolean)
            .filter((item) => {
                if (seen.has(item.code)) return false;
                seen.add(item.code);
                return true;
            });
        const textarea = document.getElementById('basket-candidates');
        if (textarea) {
            textarea.value = candidates.length ? JSON.stringify(candidates, null, 2) : '';
        }
        if (syncPicker && this.basketMultiSearch) {
            this.basketMultiSearch.setSelected(candidates);
        }
        return candidates;
    },

    _syncBasketCandidatesFromPicker() {
        const selected = this.basketMultiSearch ? this.basketMultiSearch.getSelected() : [];
        this._setBasketCandidates(selected, { syncPicker: false });
    },

    useWatchlistForBasket() {
        const watchlist = Array.isArray(this.watchlistCache) ? this.watchlistCache : [];
        if (!watchlist.length) {
            this.toast('自选股为空，请先添加自选股或搜索加入篮子', 'warning');
            return;
        }
        const candidates = this._setBasketCandidates(watchlist.slice(0, 30));
        this.toast(`已导入 ${candidates.length} 只自选股`, 'success');
    },

    clearBasketCandidates() {
        this._setBasketCandidates([]);
        this.clearBasketBacktestDraft?.();
        this.toast('篮子候选已清空', 'success');
    },

    _normalizeBasketBacktestDraft(draft = null) {
        if (!draft || typeof draft !== 'object') return null;
        const sourceContext = draft.source_context && typeof draft.source_context === 'object' ? draft.source_context : {};
        const allowedActions = ['view', 'edit', 'run_backtest_after_confirmation'];
        return {
            ...draft,
            draft_type: String(draft.draft_type || 'event_group_backtest_draft'),
            status: 'draft',
            requires_confirmation: true,
            execution_policy: 'manual_only',
            execution_status: 'not_executed',
            allowed_actions: allowedActions,
            conditions: draft.conditions && typeof draft.conditions === 'object' ? draft.conditions : {},
            source_context: sourceContext,
        };
    },

    _readBasketBacktestDraft() {
        const cached = this._normalizeBasketBacktestDraft(this._iwencaiBasketDraft?.backtest_draft);
        if (cached) return cached;
        const raw = document.getElementById('basket-candidates')?.dataset?.backtestDraft || '';
        if (!raw) return null;
        try {
            return this._normalizeBasketBacktestDraft(JSON.parse(raw));
        } catch {
            return null;
        }
    },

    _readBasketBacktestDraftForSubmit() {
        const draft = this._readBasketBacktestDraft();
        if (!draft) return null;
        const editor = document.getElementById('basket-backtest-draft-conditions');
        let conditions = draft.conditions || {};
        if (editor) {
            try {
                conditions = JSON.parse(editor.value || '{}');
            } catch (error) {
                this._setBasketDraftError(`JSON 格式不正确: ${error.message}`);
                throw new Error('草案条件 JSON 格式不正确');
            }
            if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) {
                this._setBasketDraftError('草案条件必须是 JSON 对象');
                throw new Error('草案条件必须是 JSON 对象');
            }
        }
        this._setBasketDraftError('');
        return this._writeBasketBacktestDraft({
            ...draft,
            conditions,
            status: 'draft',
            requires_confirmation: true,
            execution_policy: 'manual_only',
            execution_status: 'not_executed',
            updated_at: new Date().toISOString(),
        });
    },

    _writeBasketBacktestDraft(draft = null) {
        const normalized = this._normalizeBasketBacktestDraft(draft);
        const textarea = document.getElementById('basket-candidates');
        if (textarea) {
            if (normalized) {
                textarea.dataset.backtestDraft = JSON.stringify(normalized);
            } else {
                delete textarea.dataset.backtestDraft;
            }
        }
        if (!this._iwencaiBasketDraft && normalized) {
            this._iwencaiBasketDraft = {
                query: '',
                candidates: [],
                source_context: normalized.source_context || null,
                draftMode: 'backtest',
                created_at: new Date().toISOString(),
            };
        }
        if (this._iwencaiBasketDraft) {
            this._iwencaiBasketDraft.backtest_draft = normalized;
        }
        return normalized;
    },

    _formatBasketDraftValue(value) {
        if (Array.isArray(value)) return value.join(' / ');
        if (value && typeof value === 'object') {
            if (Array.isArray(value.codes)) return value.codes.join(' / ') || value.type || '待确认';
            return Object.entries(value)
                .slice(0, 3)
                .map(([key, item]) => `${key}: ${Array.isArray(item) ? item.join('/') : item}`)
                .join('；');
        }
        return value == null || value === '' ? '待确认' : String(value);
    },

    _setBasketDraftText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    _setBasketDraftError(message = '') {
        const el = document.getElementById('basket-backtest-draft-error');
        if (!el) return;
        el.textContent = message;
        el.classList.toggle('hidden', !message);
    },

    _basketDraftSourceFields(draft, conditions, eventGroup) {
        const sourceContext = draft.source_context || {};
        const fields = [];
        const query = sourceContext.query || sourceContext.raw_query || this._iwencaiBasketDraft?.query || '';
        const sourceLabel = sourceContext.sourceLabel || sourceContext.source_label || sourceContext.source || '';
        const eventTypes = eventGroup.event_types || conditions.event_types || [];
        const candidateCount = conditions.candidate_count || this._iwencaiBasketDraft?.candidates?.length || '';
        if (sourceLabel) fields.push(['来源', sourceLabel]);
        if (query) fields.push(['原始查询', query]);
        if (eventGroup.event_count || eventGroup.raw_count) {
            fields.push(['事件数', `${eventGroup.event_count || 0} 独立 / ${eventGroup.raw_count || eventGroup.event_count || 0} 原始`]);
        } else if (candidateCount) {
            fields.push(['候选数', `${candidateCount} 只`]);
        }
        if (Array.isArray(eventTypes) && eventTypes.length) fields.push(['事件类型', eventTypes]);
        if (eventGroup.rank_reason || conditions.rank_reason) fields.push(['入选原因', eventGroup.rank_reason || conditions.rank_reason]);
        return fields;
    },

    renderBasketBacktestDraft(draftInput = null) {
        const draft = this._writeBasketBacktestDraft(draftInput || this._readBasketBacktestDraft());
        const panel = document.getElementById('basket-backtest-draft');
        const fields = document.getElementById('basket-backtest-draft-fields');
        const editor = document.getElementById('basket-backtest-draft-conditions');
        if (!panel || !fields || !editor) return;
        this._setBasketDraftError('');
        if (!draft) {
            panel.classList.remove('hidden');
            panel.classList.add('is-empty');
            editor.value = '';
            fields.textContent = '';
            this._setBasketDraftText('basket-backtest-draft-title', '等待事件组草案');
            this._setBasketDraftText('basket-backtest-draft-summary', '从个股事件组或问财候选池生成回测草案后，可在这里核对来源、编辑条件 JSON；草案不会自动执行。');
            this._setBasketDraftText('basket-backtest-draft-status', '空态 · 未执行');
            return;
        }

        const conditions = draft.conditions || {};
        const eventGroup = draft.source_context?.event_group || {};
        const titleParts = [
            eventGroup.stock_name || '',
            eventGroup.stock_code || '',
            conditions.event_date || eventGroup.event_date || '',
        ].filter(Boolean);
        const fallbackTitle = eventGroup.stock_name || eventGroup.stock_code
            ? '事件组回测草案'
            : '候选池回测草案';
        const summary = conditions.hypothesis
            || `${eventGroup.stock_name || eventGroup.stock_code || '事件组'} 回测草案，需人工确认后手动执行计划回测`;
        const fieldItems = [
            ...this._basketDraftSourceFields(draft, conditions, eventGroup),
            ['事件日', conditions.event_date || eventGroup.event_date],
            ['主事件', conditions.primary_event_title || eventGroup.primary_event_title || eventGroup.primary_event_id],
            ['入场', conditions.entry_rule],
            ['退出', conditions.exit_rule],
            ['持有', conditions.holding_periods],
            ['基准', conditions.benchmark],
            ['去重', conditions.dedupe_policy || eventGroup.dedupe_policy],
            ['反证', conditions.counter_evidence_filters],
        ].filter(([, value]) => value != null && value !== '' && !(Array.isArray(value) && !value.length));

        panel.classList.remove('hidden', 'is-empty');
        panel.dataset.executionPolicy = draft.execution_policy || 'manual_only';
        panel.dataset.executionStatus = draft.execution_status || 'not_executed';
        this._setBasketDraftText('basket-backtest-draft-title', titleParts.join(' · ') || fallbackTitle);
        this._setBasketDraftText('basket-backtest-draft-summary', summary);
        this._setBasketDraftText(
            'basket-backtest-draft-status',
            '未执行 · 需确认后手动计划回测 · 草案条件会提交后端审计但不改变执行规则',
        );
        fields.textContent = '';
        fieldItems.forEach(([label, value]) => {
            const item = document.createElement('div');
            item.className = 'basket-backtest-draft-field';
            const key = document.createElement('span');
            key.className = 'basket-backtest-draft-field-key';
            key.textContent = label;
            const val = document.createElement('span');
            val.className = 'basket-backtest-draft-field-value';
            val.textContent = this._formatBasketDraftValue(value);
            item.appendChild(key);
            item.appendChild(val);
            fields.appendChild(item);
        });
        editor.value = JSON.stringify(conditions, null, 2);
    },

    updateBasketBacktestDraftFromEditor() {
        const editor = document.getElementById('basket-backtest-draft-conditions');
        const draft = this._readBasketBacktestDraft();
        if (!editor || !draft) {
            this.toast('暂无可更新的回测草案', 'warning');
            return;
        }
        let conditions;
        try {
            conditions = JSON.parse(editor.value || '{}');
        } catch (error) {
            this._setBasketDraftError(`JSON 格式不正确: ${error.message}`);
            this.toast('草案条件 JSON 格式不正确', 'error');
            return;
        }
        if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) {
            this._setBasketDraftError('草案条件必须是 JSON 对象');
            this.toast('草案条件必须是 JSON 对象', 'error');
            return;
        }
        const updated = this._writeBasketBacktestDraft({
            ...draft,
            conditions,
            status: 'draft',
            requires_confirmation: true,
            execution_policy: 'manual_only',
            execution_status: 'not_executed',
            updated_at: new Date().toISOString(),
        });
        this.renderBasketBacktestDraft(updated);
        this._setBasketDraftText('basket-backtest-draft-status', `未执行 · 条件已更新 ${new Date(updated.updated_at).toLocaleTimeString()} · 需手动计划回测`);
        this.toast('回测草案条件已更新，仍需手动执行计划回测', 'success');
    },

    clearBasketBacktestDraft() {
        this._writeBasketBacktestDraft(null);
        this.renderBasketBacktestDraft(null);
        this._renderBasketDraftAudit(null);
    },

    _parseBasketCandidates() {
        const raw = document.getElementById('basket-candidates')?.value?.trim() || '';
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return this._setBasketCandidates(Array.isArray(parsed) ? parsed : []);
    },

    async loadBasketPlan() {
        const initialCash = Number(document.getElementById('basket-cash')?.value || 0);
        const allocation = document.getElementById('basket-allocation')?.value || 'equal';
        const rebalanceDays = Number(document.getElementById('basket-rebalance')?.value || 5);
        let candidates;
        try {
            candidates = this._parseBasketCandidates();
        } catch (error) {
            this.toast('候选股票格式不正确，请输入 JSON 数组', 'error');
            return;
        }
        if (!candidates.length) { this.toast('请先填写候选股票', 'error'); return; }

        try {
            this.toast('生成篮子计划中...', 'info');
            const data = await this.postJSON('/api/alpha/basket/plan', { candidates, initial_cash: initialCash, allocation, rebalance_days: rebalanceDays });
            this.renderBasketPlan(data);
            this.toast(data?.success ? '篮子计划已生成' : '篮子计划生成失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('篮子计划生成失败: ' + e.message, 'error');
        }
    },

    async loadBasketBacktest() {
        const initialCash = Number(document.getElementById('basket-cash')?.value || 0);
        const allocation = document.getElementById('basket-allocation')?.value || 'equal';
        const rebalanceDays = Number(document.getElementById('basket-rebalance')?.value || 5);
        let candidates;
        try {
            candidates = this._parseBasketCandidates();
        } catch (error) {
            this.toast('候选股票格式不正确，请输入 JSON 数组', 'error');
            return;
        }
        if (!candidates.length) { this.toast('请先填写候选股票', 'error'); return; }

        try {
            const draft = this._readBasketBacktestDraftForSubmit();
            this.toast('篮子回测中...', 'info');
            const payload = { candidates, initial_cash: initialCash, allocation, rebalance_days: rebalanceDays };
            if (draft) {
                payload.backtest_draft = draft;
                payload.backtest_draft_conditions = draft.conditions || {};
            }
            const data = await this.postJSON('/api/alpha/basket/backtest', payload);
            this.renderBasketBacktest(data);
            this.toast(data?.success ? '篮子回测完成' : '篮子回测失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('篮子回测失败: ' + e.message, 'error');
        }
    },

    renderBasketPlan(data) {
        const successEl = document.getElementById('basket-success');
        const targetEl = document.getElementById('basket-target-value');
        const costEl = document.getElementById('basket-estimated-cost');
        const warningEl = document.getElementById('basket-warning-list');
        const body = document.querySelector('#basket-legs-table tbody');

        if (successEl) successEl.textContent = data?.success ? '是' : '否';
        if (targetEl) targetEl.textContent = data?.total_target_value != null ? `¥${Number(data.total_target_value).toFixed(2)}` : '--';
        if (costEl) costEl.textContent = data?.total_estimated_cost != null ? `¥${Number(data.total_estimated_cost).toFixed(2)}` : '--';
        if (warningEl) {
            const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
            warningEl.innerHTML = warnings.length > 0
                ? warnings.map(item => `<div>${App.escapeHTML(item)}</div>`).join('')
                : '暂无警告';
        }

        if (body) {
            const legs = Array.isArray(data?.legs) ? data.legs : [];
            const esc = App.escapeHTML;
            body.innerHTML = legs.length > 0
                ? legs.map(item => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td><td>${esc(item.industry)}</td><td>${esc(item.weight)}</td><td>${esc(item.price)}</td><td>${esc(item.shares)}</td><td>${esc(item.target_value)}</td></tr>`).join('')
                : '<tr><td colspan="7" class="text-muted">暂无持仓腿</td></tr>';
        }
    },

    renderBasketBacktest(data) {
        const summary = document.getElementById('basket-backtest-summary');
        if (!summary) return;
        this._renderBasketDraftAudit(data?.draft_audit || null);
        if (!data?.success) {
            summary.textContent = data?.error || '篮子回测失败';
            return;
        }

        const metrics = data.metrics || {};
        const lines = [
            metrics['总收益率'],
            metrics['年化收益率'],
            metrics['最大回撤'],
            metrics['夏普比率'],
            metrics['胜率'],
        ].filter(Boolean);
        summary.textContent = lines.length > 0 ? lines.join(' | ') : '回测完成';
    },

    _renderBasketDraftAudit(audit = null) {
        const studyEl = document.getElementById('basket-draft-audit-study');
        if (!audit) {
            if (studyEl) {
                studyEl.classList.add('hidden');
                studyEl.innerHTML = '暂无草案审计';
            }
            const warningEl = document.getElementById('basket-warning-list');
            if (warningEl) warningEl.innerHTML = '暂无警告';
            const draft = this._readBasketBacktestDraft();
            this._setBasketDraftText(
                'basket-backtest-draft-status',
                draft
                    ? '未执行 · 草案待后端审计 · 需手动计划回测'
                    : '空态 · 未执行',
            );
            return;
        }
        const sampleCount = Number(audit.sample_count || 0);
        const candidateCount = Number(audit.candidate_count || 0);
        const coverageText = candidateCount > 0 ? `样本 ${sampleCount}/${candidateCount}` : `样本 ${sampleCount}`;
        const statusText = audit.sample_status === 'ready'
            ? `未执行 · 后端已审计草案 · ${coverageText}`
            : `未执行 · 后端已审计草案 · ${audit.sample_status || '样本待补齐'} · ${coverageText}`;
        this._setBasketDraftText('basket-backtest-draft-status', statusText);
        this._renderBasketDraftEventStudy(studyEl, audit);

        const warningEl = document.getElementById('basket-warning-list');
        if (!warningEl) return;
        const warnings = Array.isArray(audit.warnings) ? audit.warnings : [];
        const items = [
            ...warnings,
            audit.conditions_applied_to_backtest === false ? '草案条件仅用于审计，未改变本次篮子回测执行规则' : '',
            audit.note || '',
        ].filter(Boolean);
        warningEl.innerHTML = items.length > 0
            ? items.map(item => `<div>${App.escapeHTML(item)}</div>`).join('')
            : '<div>草案后端审计通过，暂无警告</div>';
    },

    _renderBasketDraftEventStudy(studyEl, audit = null) {
        if (!studyEl) return;
        const esc = App.escapeHTML;
        const stats = audit?.event_statistics || audit?.event_study || {};
        const periods = Array.isArray(stats.holding_periods) && stats.holding_periods.length
            ? stats.holding_periods
            : (Array.isArray(audit?.holding_periods) ? audit.holding_periods : []);
        const periodStats = stats.by_holding_period || stats.period_stats || {};
        const coverage = Number(stats.coverage_ratio ?? audit?.coverage_ratio ?? 0);
        const coveragePct = Number.isFinite(coverage) ? `${(coverage * 100).toFixed(1)}%` : '--';
        const benchmark = stats.benchmark || {};
        const costModel = stats.cost_model || {};
        const benchmarkStatus = benchmark.available
            ? (benchmark.name || benchmark.code || '已计算')
            : ({
                benchmark_not_requested: '未指定',
                missing_benchmark_price_data: '缺基准数据',
            }[benchmark.reason] || '未计算');
        const costStatus = costModel.available
            ? `${Number(costModel.estimated_round_trip_cost_pct || 0).toFixed(2)}%`
            : '未计算';
        const statusLabel = {
            ready: '可统计',
            partial: '部分样本',
            no_sample: '无样本',
            missing_draft: '缺草案',
            insufficient_sample: '样本不足',
        }[stats.status || audit?.sample_status] || (stats.status || audit?.sample_status || '--');
        const periodItems = periods.map((period) => periodStats[String(period)] || {});
        const firstComputedStat = periodItems.find((item) => item.significance_status);
        const significanceLabel = {
            computed_descriptive: '描述性 t 值',
            insufficient_sample: '样本不足',
            zero_variance: '零波动',
        }[firstComputedStat?.significance_status] || (firstComputedStat?.significance_status || '未计算');
        const summaryCards = [
            ['样本覆盖', `${Number(stats.ready_sample_count ?? audit?.sample_count ?? 0)}/${Number(stats.candidate_count ?? audit?.candidate_count ?? 0)}`],
            ['覆盖率', coveragePct],
            ['事件日', audit?.event_date || '--'],
            ['状态', statusLabel],
            ['基准', benchmarkStatus],
            ['估算成本', costStatus],
            ['统计显著性', significanceLabel],
        ];
        const fmtPct = (value) => value == null || value === '' || !Number.isFinite(Number(value)) ? '--' : `${Number(value).toFixed(2)}%`;
        const signedClass = (value) => {
            const num = Number(value);
            if (!Number.isFinite(num)) return '';
            return num >= 0 ? 'text-up' : 'text-down';
        };
        const rows = periods.map((period) => {
            const key = String(period);
            const item = periodStats[key] || {};
            const winRate = item.win_rate == null ? '--' : `${(Number(item.win_rate) * 100).toFixed(1)}%`;
            const tStat = item.t_stat_excess_return ?? item.t_stat_net_return ?? item.t_stat_return;
            return `
                <tr>
                    <td>${esc(period)}日</td>
                    <td>${esc(item.sample_count ?? item.count ?? 0)}</td>
                    <td class="${signedClass(item.mean_return_pct ?? item.mean_return)}">${esc(fmtPct(item.mean_return_pct ?? item.mean_return))}</td>
                    <td>${esc(fmtPct(item.mean_cost_pct))}</td>
                    <td class="${signedClass(item.mean_net_return_pct)}">${esc(fmtPct(item.mean_net_return_pct))}</td>
                    <td class="${signedClass(item.mean_benchmark_return_pct)}">${esc(fmtPct(item.mean_benchmark_return_pct))}</td>
                    <td class="${signedClass(item.mean_excess_return_pct)}">${esc(fmtPct(item.mean_excess_return_pct))}</td>
                    <td>${esc(winRate)}</td>
                    <td>${esc(tStat == null ? '--' : Number(tStat).toFixed(2))}</td>
                </tr>
            `;
        }).join('');
        const best = stats.best_period
            ? `<div class="basket-draft-study-note">最佳窗口：${esc(stats.best_period.period)}日，平均收益 ${esc(Number(stats.best_period.mean_return_pct).toFixed(2))}% · 样本 ${esc(stats.best_period.sample_count)}</div>`
            : '';
        const methodology = stats.methodology || '按事件日后下一交易日入场，按持有期收盘价计算简单收益率。';
        const limitations = Array.isArray(stats.limitations) ? stats.limitations : [];
        studyEl.classList.remove('hidden');
        studyEl.innerHTML = `
            <div class="basket-draft-study-head">
                <strong>事件样本统计</strong>
                <span>${esc(stats.method || 'next_bar_open_to_holding_close')}</span>
            </div>
            <div class="basket-draft-study-metrics">
                ${summaryCards.map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}
            </div>
            ${rows ? `
                <div class="table-wrap basket-draft-study-table">
                    <table>
                        <thead><tr><th>持有</th><th>样本</th><th>毛收益</th><th>成本</th><th>净收益</th><th>基准</th><th>超额</th><th>胜率</th><th>t值</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            ` : '<div class="empty-state compact">暂无可统计收益样本</div>'}
            ${best}
            <div class="basket-draft-study-note">${esc(methodology)}</div>
            ${benchmark.reason ? `<div class="basket-draft-study-note">基准状态：${esc(benchmarkStatus)} · ${esc(benchmark.reason)}</div>` : ''}
            ${limitations.length ? `<div class="basket-draft-study-limits">${limitations.map(item => `<span>${esc(item)}</span>`).join('')}</div>` : ''}
        `;
    },

    async optimizeAlpha() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        const modelType = document.getElementById('alpha-model')?.value || 'lightgbm';
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('超参优化中（约 1-3 分钟）...', 'info');
            const data = await this.postJSON('/api/alpha/optimize', { code, start_date: startDate, end_date: endDate, model_type: modelType, n_trials: 50 });
            if (data.error) {
                this.toast('优化失败: ' + data.error, 'error');
                return;
            }

            // 显示优化结果
            const paramsStr = Object.entries(data.best_params || {})
                .map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(4) : v}`)
                .join(', ');
            this.toast(`优化完成！最佳参数: ${paramsStr}`, 'success');

            // 显示到面板
            const el = document.getElementById('alpha-opt-result');
            if (el) el.textContent = paramsStr || '无';

            // 重新加载分析（静默模式，避免重复 toast）
            await this.loadAlpha({ silent: true });
        } catch (e) {
            this.toast('超参优化失败: ' + e.message, 'error');
        }
    },
});

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
        App.initAlpha?.();
    });
} else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
    App.initAlpha?.();
}
