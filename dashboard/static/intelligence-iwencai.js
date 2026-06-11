/* ── 情报模块：问财工作台 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});
    const state = Intelligence.state || (Intelligence.state = {});

    function normalizeStockCode(value) {
        const raw = String(value ?? '').trim();
        const suffixMatch = raw.match(/^(\d{6})(?:\.(?:SH|SZ|BJ))?$/i);
        if (suffixMatch) return suffixMatch[1];

        const prefixMatch = raw.match(/^(?:sh|sz|bj)(\d{6})$/i);
        if (prefixMatch) return prefixMatch[1];

        const looseMatch = raw.match(/\b(\d{6})\b/);
        return looseMatch ? looseMatch[1] : '';
    }

    function pickField(row, names) {
        for (const name of names) {
            if (Object.prototype.hasOwnProperty.call(row, name)) {
                const value = row[name];
                if (value !== null && value !== undefined && String(value).trim() !== '') {
                    return value;
                }
            }
        }

        const normalizedNames = names
            .map((name) => String(name).replace(/\[[^\]]+\]/g, '').replace(/\s+/g, '').toUpperCase())
            .filter(Boolean);
        for (const [key, value] of Object.entries(row)) {
            if (value === null || value === undefined || String(value).trim() === '') continue;
            const normalizedKey = String(key).replace(/\[[^\]]+\]/g, '').replace(/\s+/g, '').toUpperCase();
            if (normalizedNames.some((name) => normalizedKey.includes(name))) {
                return value;
            }
        }
        return '';
    }

    function toNumber(value) {
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        if (typeof value !== 'string') return null;
        const cleaned = value.replace(/[,，%]/g, '').trim();
        if (!cleaned) return null;
        const num = Number(cleaned);
        return Number.isFinite(num) ? num : null;
    }

    function formatNumber(value, digits = 2) {
        const num = toNumber(value);
        if (num === null) return '--';
        return num.toFixed(digits);
    }

    function formatPercent(value) {
        const num = toNumber(value);
        if (num === null) return '--';
        const sign = num > 0 ? '+' : '';
        return `${sign}${num.toFixed(2)}%`;
    }

    function formatMoney(value) {
        const num = toNumber(value);
        if (num === null) return '--';
        const abs = Math.abs(num);
        if (abs >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
        if (abs >= 1e4) return `${(num / 1e4).toFixed(1)}万`;
        return num.toFixed(0);
    }

    function splitTags(value, limit = 3) {
        return String(value ?? '')
            .split(/[;；,，]/)
            .map((item) => item.trim())
            .filter(Boolean)
            .slice(0, limit);
    }

    function compactIndustry(value) {
        const parts = String(value ?? '')
            .split('-')
            .map((part) => part.trim())
            .filter(Boolean);
        if (parts.length === 0) return '--';
        return parts.slice(-2).join(' / ');
    }

    function normalizeIwencaiRow(row) {
        const code = normalizeStockCode(
            pickField(row, ['股票代码', '代码', 'code', 'CODE', '证券代码'])
        );
        const rawCode = pickField(row, ['股票代码', '代码', 'code', 'CODE', '证券代码']) || code;
        const name = pickField(row, ['股票简称', '股票名称', '名称', 'name', 'SECURITY_NAME_ABBR']) || '--';
        const price = pickField(row, ['最新价', '最新价格', '现价', 'price']);
        const changePct = pickField(row, ['最新涨跌幅', '涨跌幅', 'change_pct']);
        const industry = pickField(row, ['所属同花顺行业', '所属行业', '行业']);
        const concept = pickField(row, ['所属概念', '概念', '题材概念']);
        const dde = pickField(row, ['最新DDE大单净额', 'DDE大单净额', '主力净流入', '主力净额']);
        const pe = pickField(row, ['市盈率(PE)[20260527]', '市盈率(PE)', '市盈率', 'PE', 'pe']);
        return {
            code,
            rawCode,
            name,
            price,
            changePct,
            industry,
            concept,
            dde,
            pe,
            row,
        };
    }

    function escapeHTML(value) {
        if (globalThis.App && typeof App.escapeHTML === 'function') {
            return App.escapeHTML(value);
        }
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#x27;');
    }

    function renderIwencaiRow(item, index, viewModel = null) {
        const change = toNumber(item.changePct);
        const changeClass = change == null ? '' : change >= 0 ? 'up' : 'down';
        const tags = splitTags(item.concept);
        const hiddenRawKeys = new Set(['MARKET_CODE', 'CODE']);
        const rawSummary = Object.entries(item.row)
            .filter(([key]) => !hiddenRawKeys.has(String(key).toUpperCase()))
            .filter(([key, value]) => value !== null && value !== undefined && String(value).trim() !== '')
            .slice(0, 10)
            .map(([key, value]) => `${key}: ${String(value).slice(0, 40)}`)
            .join(' | ');
        const rawCodeHtml = !item.code && item.rawCode
            ? `<span>${escapeHTML(String(item.rawCode))}</span>`
            : '';
        const codeHtml = item.code
            ? `<a href="#" class="iwencai-code" data-intel-action="iwencai-open-stock" data-code="${escapeHTML(item.code)}">${escapeHTML(item.code)}</a>`
            : `<span class="text-muted">${escapeHTML(String(item.rawCode || '--'))}</span>`;
        const rowActions = item.code ? [
            canRenderAction(viewModel, 'open_stock')
                ? `<button type="button" class="btn btn-xs" data-intel-action="iwencai-open-stock" data-code="${escapeHTML(item.code)}">打开</button>`
                : '',
            canRenderAction(viewModel, 'add_watchlist')
                ? `<button type="button" class="btn btn-xs" data-intel-action="iwencai-add-one-watchlist" data-code="${escapeHTML(item.code)}">自选</button>`
                : '',
            (canRenderAction(viewModel, 'ask_ai') || canRenderAction(viewModel, 'analyze'))
                ? `<button type="button" class="btn btn-xs" data-intel-action="iwencai-ask-ai" data-code="${escapeHTML(item.code)}">解释</button>`
                : '',
        ].filter(Boolean) : [];
        const actionButtons = rowActions.length
            ? `<div class="iwencai-row-actions">${rowActions.join('')}</div>`
            : '<span class="text-muted">--</span>';
        const reason = viewModel?.source_context?.rank_reason || item.rank_reason || '';

        return `<tr title="${escapeHTML(rawSummary)}" data-code="${escapeHTML(item.code || '')}" data-rank-reason="${escapeHTML(reason)}">
            <td class="iwencai-rank">${index + 1}</td>
            <td class="iwencai-stock-cell">
                <div class="iwencai-stock-name">${escapeHTML(item.name)}</div>
                <div class="iwencai-stock-code">${codeHtml}${rawCodeHtml}</div>
            </td>
            <td class="num">${formatNumber(item.price, 2)}</td>
            <td class="num ${changeClass}">${formatPercent(item.changePct)}</td>
            <td>${escapeHTML(compactIndustry(item.industry))}</td>
            <td><div class="iwencai-tags">${tags.length ? tags.map((tag) => `<span>${escapeHTML(tag)}</span>`).join('') : '<span>--</span>'}</div></td>
            <td class="num">${formatMoney(item.dde)}</td>
            <td class="num">${formatNumber(item.pe, 2)}</td>
            <td>${actionButtons}</td>
        </tr>`;
    }

    function toIwencaiSummaryRow(item) {
        return {
            code: item.code,
            name: item.name,
            price: formatNumber(item.price, 2),
            change_pct: formatPercent(item.changePct),
            industry: compactIndustry(item.industry),
            concepts: splitTags(item.concept),
            dde_net: formatMoney(item.dde),
            pe: formatNumber(item.pe, 2),
        };
    }

    const IWENCAI_STATUS_META = {
        parsing: { label: '解析中', tone: 'info' },
        routed: { label: '已路由', tone: 'info' },
        bucket_pending: { label: '分桶加载中', tone: 'info' },
        result_ready: { label: '结果就绪', tone: 'success' },
        partial_result: { label: '部分结果', tone: 'warning' },
        needs_disambiguation: { label: '需要澄清', tone: 'warning' },
        no_match: { label: '无匹配', tone: 'muted' },
        degraded_data: { label: '数据降级', tone: 'warning' },
        requires_confirmation: { label: '需要确认', tone: 'warning' },
        failed: { label: '失败', tone: 'danger' },
    };

    const DEFAULT_ACTIONS = ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'];
    const ACTION_ALIASES = {
        add_to_watchlist: 'add_watchlist',
        ai_analyze: 'analyze',
        ask_ai: 'ask_ai',
        create_backtest: 'draft_backtest',
        create_basket: 'create_basket',
        draft_backtest: 'draft_backtest',
        explain: 'ask_ai',
        open_stock: 'open_stock',
        send_screener: 'send_screener',
        send_to_screener: 'send_screener',
    };
    const POOL_ACTIONS = new Set(['send_screener', 'add_watchlist', 'create_basket', 'draft_backtest']);
    const BLOCKED_POOL_STATUSES = new Set(['failed', 'no_match', 'needs_disambiguation', 'requires_confirmation']);
    const STANDARD_TASK_ISSUES = {
        parse_failure: { label: '解析失败', reason: '系统没有稳定解析出可执行条件', next_action: '改写为更明确的字段、时间窗口或股票范围' },
        unsupported_field: { label: '字段不支持', reason: '部分字段暂未接入或缺少可验证数据源', next_action: '移除不支持字段，或先按已验证条件继续筛选' },
        stale_cache: { label: '缓存过期', reason: '当前结果来自旧缓存或数据日期偏旧', next_action: '先作为历史线索查看，刷新数据后再生成篮子或回测草案' },
        rate_limited: { label: '源限流', reason: '上游或本地服务暂时限制请求', next_action: '稍后重试，或切换到已有候选池、板块入口继续' },
        timeout: { label: '请求超时', reason: '请求超时，已保留原始问句和来源上下文', next_action: '重试、缩小条件，或先打开候选/板块线索验证' },
        permission_denied: { label: '权限不足', reason: '当前数据源需要权限、登录或凭证', next_action: '使用本地可用字段继续，避免自动写入或执行策略动作' },
        offline_fallback: { label: '离线降级', reason: '外部源不可用，当前使用本地或缓存降级结果', next_action: '查看数据时间和覆盖范围，确认后再生成后续动作' },
        no_match: { label: '无匹配', reason: '没有找到匹配结果，建议放宽条件或切换分桶', next_action: '删除最窄条件，或先查看相关板块/主题' },
        ambiguous_market_scope: { label: '范围歧义', reason: '市场、时间或股票主体范围不明确', next_action: '补充 A 股、港股、时间窗口或具体股票后继续' },
        write_confirmation_required: { label: '写入确认', reason: '该动作可能写入工作区，需要用户确认后继续', next_action: '确认写入前先检查候选池和来源上下文' },
        request_failed: { label: '请求失败', reason: '请求失败，已保留原始问句和来源上下文', next_action: '重试、改写条件，或改用股票/板块入口继续' },
        degraded_data: { label: '数据降级', reason: '部分字段或来源不可用，结果为降级视图', next_action: '查看缺失原因，必要时只使用已验证字段' },
        partial_source_failure: { label: '部分源失败', reason: '只返回部分结果，缺失证据已保留为空态或降级分桶', next_action: '先打开候选股验证，再决定是否生成篮子' },
    };

    function normalizeActionName(value) {
        const raw = String(value || '')
            .trim()
            .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
            .replace(/[-\s:]+/g, '_')
            .toLowerCase();
        return ACTION_ALIASES[raw] || raw;
    }

    function normalizeActions(actions) {
        const rawActions = Array.isArray(actions) && actions.length ? actions : DEFAULT_ACTIONS;
        const seen = new Set();
        const normalized = [];
        rawActions.forEach((action) => {
            const item = action && typeof action === 'object' ? action : { id: action };
            if (item.enabled === false) return;
            const name = normalizeActionName(item.id || item.action || item.type || item.name || item);
            if (!name || seen.has(name)) return;
            seen.add(name);
            normalized.push(name);
        });
        return normalized.length ? normalized : DEFAULT_ACTIONS;
    }

    function hasAction(viewModel, action) {
        const allowed = new Set(normalizeActions(viewModel?.actions));
        return allowed.has(normalizeActionName(action));
    }

    function canRenderAction(viewModel, action) {
        const normalizedAction = normalizeActionName(action);
        if (!hasAction(viewModel, normalizedAction)) return false;
        if (POOL_ACTIONS.has(normalizedAction)) {
            return (viewModel?.normalizedRows?.length || 0) > 0 && !BLOCKED_POOL_STATUSES.has(viewModel?.status);
        }
        return true;
    }

    function normalizeIntent(resp, query, rows) {
        const intent = resp?.intent && typeof resp.intent === 'object' ? resp.intent : {};
        const rawType = typeof intent.type === 'string' && intent.type.trim() ? intent.type.trim() : '';
        const looksLikeCode = /^\s*(?:sh|sz|bj)?\d{6}(?:\.(?:SH|SZ|BJ))?\s*$/i.test(query);
        const type = rawType || (looksLikeCode ? 'stock_lookup' : 'natural_language_screener');
        const confidence = Number(intent.confidence);
        return {
            type,
            confidence: Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence)) : (rows.length ? 0.72 : 0.48),
            reason: intent.reason || (type === 'natural_language_screener' ? '按自然语言选股条件路由' : '按股票/功能入口路由'),
        };
    }

    function normalizeCondition(condition) {
        const item = condition && typeof condition === 'object' ? condition : {};
        const hit = Number(item.hit_count ?? item.count ?? item.matches);
        const rawText = item.raw_text || item.text || item.label || item.field || '';
        const status = item.status || (Number.isFinite(hit) ? 'ready' : 'degraded_data');
        return {
            raw_text: rawText,
            field: item.field || rawText || '条件',
            op: item.op || item.operator || '',
            value: item.value ?? '',
            window: item.window || item.period || '',
            hit_count: Number.isFinite(hit) ? hit : null,
            status,
            unavailable_reason: item.unavailable_reason || item.missing_reason || (Number.isFinite(hit) ? '' : '后端未返回命中数'),
        };
    }

    function inferKnownConditions(part) {
        const text = String(part || '').trim();
        if (!text) return [];
        const rules = [
            {
                re: /高股息率|高股息|股息率高|高分红|分红高/g,
                build: (raw) => normalizeCondition({ raw_text: raw, field: '股息率', op: 'rank', value: raw, window: 'latest' }),
            },
            {
                re: /低估值|估值低|低PE|PE低|低PB|PB低|低市盈率|市盈率低|低市净率|市净率低/g,
                build: (raw) => normalizeCondition({ raw_text: raw, field: '估值', op: 'screen', value: raw, window: 'latest' }),
            },
            {
                re: /近?\d+(?:日|天)?(?:持续)?放量|放量|量比高|成交量放大|成交量放量/g,
                build: (raw) => {
                    const match = raw.match(/近?(\d+)(?:日|天)?/);
                    return normalizeCondition({ raw_text: raw, field: '成交量', op: 'volume_up', value: raw, window: match ? `${match[1]}d` : '' });
                },
            },
            {
                re: /近?\d+(?:日|天)?主力净流入|主力净流入|净流入|资金流入/g,
                build: (raw) => {
                    const match = raw.match(/近?(\d+)(?:日|天)?/);
                    return normalizeCondition({ raw_text: raw, field: '资金流', op: 'inflow', value: raw, window: match ? `${match[1]}d` : '' });
                },
            },
        ];
        const matches = [];
        rules.forEach((rule, ruleIndex) => {
            rule.re.lastIndex = 0;
            let match = rule.re.exec(text);
            while (match) {
                matches.push({
                    index: match.index,
                    ruleIndex,
                    length: match[0].length,
                    condition: rule.build(match[0]),
                });
                match = rule.re.exec(text);
            }
        });
        matches.sort((a, b) => a.index - b.index || a.ruleIndex - b.ruleIndex || b.length - a.length);
        const occupied = [];
        const conditions = [];
        matches.forEach((match) => {
            const end = match.index + match.length;
            if (occupied.some(([start, stop]) => match.index < stop && end > start)) return;
            occupied.push([match.index, end]);
            conditions.push(match.condition);
        });
        return conditions;
    }

    function inferConditionFromPart(part) {
        if (/股息|分红/.test(part)) {
            return normalizeCondition({ raw_text: part, field: '股息率', op: 'rank', value: part, window: 'latest' });
        }
        if (/估值|PE|PB|市盈率|市净率/i.test(part)) {
            return normalizeCondition({ raw_text: part, field: '估值', op: 'screen', value: part, window: 'latest' });
        }
        if (/放量|量比|成交量/.test(part)) {
            const match = part.match(/近?(\d+)日/);
            return normalizeCondition({ raw_text: part, field: '成交量', op: 'volume_up', value: part, window: match ? `${match[1]}d` : '' });
        }
        if (/净流入|主力|资金/.test(part)) {
            return normalizeCondition({ raw_text: part, field: '资金流', op: 'inflow', value: part, window: '' });
        }
        return normalizeCondition({ raw_text: part, field: part, op: 'contains', value: part, window: '' });
    }

    function inferParsedConditions(query) {
        const parts = String(query || '')
            .split(/[\s,，;；]+/)
            .map((item) => item.trim())
            .filter(Boolean);
        const conditions = [];
        parts.slice(0, 8).forEach((part) => {
            const known = inferKnownConditions(part);
            if (known.length) {
                conditions.push(...known);
            } else {
                conditions.push(inferConditionFromPart(part));
            }
        });
        return conditions.slice(0, 8);
    }

    function conditionSummary(conditions) {
        return (conditions || [])
            .map((item) => item.raw_text || item.field)
            .filter(Boolean)
            .slice(0, 4)
            .join(' / ');
    }

    function normalizeBucketItems(bucket) {
        const items = Array.isArray(bucket?.items) ? bucket.items : [];
        return items.map((item) => {
            if (item && typeof item === 'object' && (item.code || item['股票代码'] || item.CODE)) {
                return normalizeIwencaiRow(item.row && typeof item.row === 'object' ? item.row : item);
            }
            return item;
        });
    }

    function buildBuckets(resp, normalizedRows) {
        const fromResp = Array.isArray(resp?.buckets) ? resp.buckets : [];
        const buckets = fromResp.map((bucket) => ({
            id: String(bucket.id || bucket.type || bucket.name || '').trim() || 'bucket',
            name: bucket.name || bucket.label || bucket.id || '结果分桶',
            status: bucket.status || 'result_ready',
            items: normalizeBucketItems(bucket),
            count: Number.isFinite(Number(bucket.count)) ? Number(bucket.count) : normalizeBucketItems(bucket).length,
            description: bucket.description || '',
        })).filter((bucket) => bucket.id);

        if (!buckets.some((bucket) => bucket.id === 'candidates')) {
            buckets.unshift({
                id: 'candidates',
                name: '候选股票',
                status: normalizedRows.length ? 'result_ready' : 'no_match',
                items: normalizedRows,
                count: normalizedRows.length,
                description: '按问财条件命中的股票候选',
            });
        }
        if (!buckets.some((bucket) => bucket.id === 'themes')) {
            buckets.push({ id: 'themes', name: '板块主题', status: 'degraded_data', items: [], count: 0, description: '等待主题/板块证据接入' });
        }
        if (!buckets.some((bucket) => bucket.id === 'news')) {
            buckets.push({ id: 'news', name: '新闻证据', status: 'degraded_data', items: [], count: 0, description: '等待新闻/公告证据接入' });
        }
        return buckets;
    }

    function buildSourceContext(query, intent, conditions, selectedBucket, resp, total) {
        const conditionHitCount = {};
        conditions.forEach((condition) => {
            const key = condition.raw_text || condition.field;
            if (key) conditionHitCount[key] = condition.hit_count;
        });
        const sourceContext = resp?.source_context && typeof resp.source_context === 'object' ? resp.source_context : {};
        const issue = normalizeTaskIssue(resp);
        return {
            ...sourceContext,
            source: sourceContext.source || 'iwencai',
            sourceLabel: sourceContext.sourceLabel || '问财',
            context_type: sourceContext.context_type || 'iwencai',
            raw_query: sourceContext.raw_query || query,
            query,
            intent_type: sourceContext.intent_type || intent.type,
            selected_bucket: selectedBucket,
            result_pool_id: sourceContext.result_pool_id || `iwencai:${Date.now()}`,
            result_total: total,
            parsed_conditions: conditions,
            condition_hit_count: conditionHitCount,
            failure_type: sourceContext.failure_type || issue.type,
            status_reason: sourceContext.status_reason || issue.reason,
            next_action: sourceContext.next_action || issue.next_action,
            provider: sourceContext.provider || resp?.provider || resp?.source_provider || resp?.source_status?.provider || resp?.source || 'iwencai',
            data_as_of: sourceContext.data_as_of || resp?.data_as_of || resp?.as_of || resp?.source_status?.data_as_of || '',
            cache_status: sourceContext.cache_status || resp?.cache_status || resp?.source_status?.cache_status || '',
            data_status: sourceContext.data_status || resp?.data_status || resp?.source_status?.status || resp?.status || '',
            rank_reason: sourceContext.rank_reason || `问财条件: ${conditionSummary(conditions) || query}`,
        };
    }

    function normalizeTaskIssue(resp) {
        const status = String(resp?.status || (resp?.success === false ? 'failed' : '')).trim();
        const rawTypeValue = (
            resp?.failure_type
            || resp?.error_type
            || resp?.degraded_type
            || resp?.source_status?.type
        );
        const rawType = rawTypeValue ? String(rawTypeValue).trim() : '';
        const reason = String(
            resp?.failure_reason
            || resp?.degraded_reason
            || resp?.missing_reason
            || resp?.unavailable_reason
            || resp?.source_status?.reason
            || resp?.error
            || resp?.message
            || ''
        ).trim();
        const reasonText = reason.toLowerCase();
        const inferredType = rawType
            || (/timeout|timed out|超时/.test(reasonText) ? 'timeout' : '')
            || (/rate|limit|限流|频率|过于频繁/.test(reasonText) ? 'rate_limited' : '')
            || (/permission|auth|login|unauthorized|forbidden|权限|登录|认证|凭证/.test(reasonText) ? 'permission_denied' : '')
            || (/stale|cache|缓存|过期|旧/.test(reasonText) ? 'stale_cache' : '')
            || (/unsupported|unknown field|字段|不支持|未接入/.test(reasonText) ? 'unsupported_field' : '')
            || (/offline|fallback|local|离线|本地|降级/.test(reasonText) ? 'offline_fallback' : '')
            || (/parse|parser|解析/.test(reasonText) ? 'parse_failure' : '')
            || (status === 'failed' ? 'request_failed' : '')
            || (status === 'no_match' ? 'no_match' : '')
            || (status === 'degraded_data' ? 'degraded_data' : '')
            || (status === 'partial_result' ? 'partial_source_failure' : '')
            || (status === 'needs_disambiguation' ? 'ambiguous_market_scope' : '')
            || (status === 'requires_confirmation' ? 'write_confirmation_required' : '');
        const standardIssue = STANDARD_TASK_ISSUES[inferredType] || null;
        const nextAction = String(
            resp?.next_action
            || resp?.next_step
            || resp?.source_status?.next_action
            || ''
        ).trim();
        const defaultReason = {
            failed: '请求失败，已保留原始问句和来源上下文',
            no_match: '没有找到匹配结果，建议放宽条件或切换分桶',
            degraded_data: '部分字段或来源不可用，结果为降级视图',
            partial_result: '只返回部分结果，缺失证据已保留为空态或降级分桶',
            needs_disambiguation: '条件存在歧义，需要补充市场、时间或字段约束',
            requires_confirmation: '该动作可能写入工作区，需要用户确认后继续',
        }[status] || '';
        const defaultNextAction = {
            failed: '重试、改写条件，或改用股票/板块入口继续',
            no_match: '删除最窄条件，或先查看相关板块/主题',
            degraded_data: '查看缺失原因，必要时只使用已验证字段',
            partial_result: '先打开候选股验证，再决定是否生成篮子',
            needs_disambiguation: '补充时间窗口、字段或股票范围',
            requires_confirmation: '确认写入动作前先检查候选池',
        }[status] || '';
        return {
            type: inferredType || '',
            label: standardIssue?.label || '',
            reason: reason || standardIssue?.reason || defaultReason,
            next_action: nextAction || standardIssue?.next_action || defaultNextAction,
        };
    }

    function buildContextList(rows, sourceContext) {
        return rows
            .filter((row) => row.code)
            .slice(0, 50)
            .map((row, index) => ({
                code: row.code,
                name: row.name,
                source: 'iwencai',
                sourceLabel: '问财',
                context_type: 'iwencai',
                source_context: { ...sourceContext, rank_reason: index === 0 ? sourceContext.rank_reason : '同一问财候选池' },
                query: sourceContext.query,
                rank_reason: index === 0 ? sourceContext.rank_reason : '同一问财候选池',
                price: formatNumber(row.price, 2),
                change_pct: formatPercent(row.changePct),
                updated_at: sourceContext.data_as_of || '',
            }));
    }

    function buildIwencaiTaskViewModel(resp, query, selectedBucket = null) {
        const data = Array.isArray(resp?.data) ? resp.data : [];
        const displayRows = data.slice(0, 30);
        let normalizedRows = displayRows.map((row) => normalizeIwencaiRow(row));
        const intent = normalizeIntent(resp, query, normalizedRows);
        const parsedConditions = Array.isArray(resp?.parsed_conditions) && resp.parsed_conditions.length
            ? resp.parsed_conditions.map(normalizeCondition)
            : inferParsedConditions(query);
        const buckets = buildBuckets(resp, normalizedRows);
        const candidateBucket = buckets.find((bucket) => bucket.id === 'candidates');
        if (normalizedRows.length && candidateBucket && (!Array.isArray(candidateBucket.items) || candidateBucket.items.length === 0)) {
            candidateBucket.items = normalizedRows;
            candidateBucket.count = Number.isFinite(Number(candidateBucket.count)) && Number(candidateBucket.count) > 0
                ? Number(candidateBucket.count)
                : normalizedRows.length;
        }
        if (!normalizedRows.length && Array.isArray(candidateBucket?.items) && candidateBucket.items.length) {
            normalizedRows = candidateBucket.items.filter((item) => item && typeof item === 'object' && item.code);
            candidateBucket.items = normalizedRows;
            candidateBucket.count = normalizedRows.length;
        }
        const selected = selectedBucket && buckets.some((bucket) => bucket.id === selectedBucket)
            ? selectedBucket
            : (resp?.selected_bucket || buckets[0]?.id || 'candidates');
        const total = Number.isFinite(Number(resp?.total)) ? Number(resp.total) : data.length;
        const sourceContext = buildSourceContext(query, intent, parsedConditions, selected, resp, total);
        const contextList = buildContextList(normalizedRows, sourceContext);
        const status = resp?.status || (resp?.success === false ? 'failed' : normalizedRows.length ? 'result_ready' : 'no_match');
        const issue = normalizeTaskIssue({ ...resp, status });
        return {
            query,
            raw_response: resp,
            data,
            displayRows,
            normalizedRows,
            summaryRows: normalizedRows.map((row) => toIwencaiSummaryRow(row)),
            intent,
            parsed_conditions: parsedConditions,
            buckets,
            selected_bucket: selected,
            actions: normalizeActions(resp?.actions),
            status,
            error: resp?.error || '',
            issue,
            total,
            source_context: { ...sourceContext, selected_bucket: selected },
            contextList,
        };
    }

    function renderConditionChips(conditions) {
        if (!conditions.length) {
            return '<div class="iwencai-empty-note">未解析出结构化条件</div>';
        }
        return `<div class="iwencai-condition-strip">
            ${conditions.map((condition) => {
                const hit = condition.hit_count == null ? condition.unavailable_reason : `${condition.hit_count} 只`;
                const windowText = condition.window ? ` · ${condition.window}` : '';
                return `<span class="iwencai-condition-chip status-${escapeHTML(condition.status)}">
                    <strong>${escapeHTML(condition.raw_text || condition.field)}</strong>
                    <em>${escapeHTML(condition.field)}${windowText}</em>
                    <small>${escapeHTML(hit || '命中数不可用')}</small>
                </span>`;
            }).join('')}
        </div>`;
    }

    function renderBucketTabs(viewModel) {
        return `<div class="iwencai-bucket-tabs" role="tablist">
            ${viewModel.buckets.map((bucket) => {
                const active = bucket.id === viewModel.selected_bucket ? ' is-active' : '';
                return `<button type="button" class="iwencai-bucket-tab${active}" data-intel-action="iwencai-select-bucket" data-bucket-id="${escapeHTML(bucket.id)}">
                    <span>${escapeHTML(bucket.name)}</span>
                    <em>${escapeHTML(bucket.count ?? bucket.items?.length ?? 0)}</em>
                </button>`;
            }).join('')}
        </div>`;
    }

    function renderCandidateTable(viewModel, rows) {
        if (!rows.length) {
            return `<div class="iwencai-empty-note">该分桶暂无候选股票。${escapeHTML(viewModel.error || '')}</div>`;
        }
        return `<div class="table-wrap iwencai-table-wrap"><table class="iwencai-focused-table">
            <thead><tr>
                <th>#</th>
                <th>股票</th>
                <th class="num">最新价</th>
                <th class="num">涨跌幅</th>
                <th>行业</th>
                <th>概念</th>
                <th class="num">DDE净额</th>
                <th class="num">PE</th>
                <th>操作</th>
            </tr></thead>
            <tbody>${rows.map((row, index) => renderIwencaiRow(row, index, viewModel)).join('')}</tbody>
        </table></div>`;
    }

    function renderGenericBucket(viewModel, bucket) {
        const items = Array.isArray(bucket.items) ? bucket.items : [];
        if (!items.length) {
            return `<div class="iwencai-empty-note">${escapeHTML(bucket.description || '该分桶暂无结果；已保留原始问句和来源上下文。')}</div>`;
        }
        return `<div class="iwencai-bucket-cards">
            ${items.slice(0, 12).map((item) => {
                const title = item?.name || item?.title || item?.label || item?.concept || '--';
                const desc = item?.description || item?.summary || item?.reason || viewModel.query;
                return `<article class="iwencai-bucket-card">
                    <strong>${escapeHTML(title)}</strong>
                    <span>${escapeHTML(desc)}</span>
                </article>`;
            }).join('')}
        </div>`;
    }

    function renderBucketContent(viewModel) {
        const bucket = viewModel.buckets.find((item) => item.id === viewModel.selected_bucket) || viewModel.buckets[0];
        if (!bucket) return '<div class="iwencai-empty-note">暂无分桶结果</div>';
        if (bucket.id === 'candidates') {
            return renderCandidateTable(viewModel, bucket.items || viewModel.normalizedRows);
        }
        return renderGenericBucket(viewModel, bucket);
    }

    function renderGlobalActions(viewModel) {
        const total = viewModel.total || viewModel.normalizedRows.length;
        const shown = viewModel.normalizedRows.length;
        const buttons = [
            canRenderAction(viewModel, 'send_screener')
                ? '<button class="btn btn-sm" data-intel-action="iwencai-send-screener">发送至选股器</button>'
                : '',
            canRenderAction(viewModel, 'analyze')
                ? '<button class="btn btn-sm" data-intel-action="iwencai-analyze">交给 AI 分析</button>'
                : '',
            canRenderAction(viewModel, 'add_watchlist')
                ? '<button class="btn btn-sm" data-intel-action="iwencai-add-watchlist">加入自选</button>'
                : '',
            canRenderAction(viewModel, 'create_basket')
                ? '<button class="btn btn-sm" data-intel-action="iwencai-create-basket">生成篮子</button>'
                : '',
            canRenderAction(viewModel, 'draft_backtest')
                ? '<button class="btn btn-sm" data-intel-action="iwencai-draft-backtest">生成回测草案</button>'
                : '',
        ].filter(Boolean).join('');
        return `<div class="iwencai-actions">
            <span class="text-muted text-xs">共 ${escapeHTML(total)} 条，显示前 ${escapeHTML(shown)} 条 · 来源上下文已保留</span>
            ${buttons || '<span class="iwencai-empty-note">当前状态暂无可直接执行动作</span>'}
        </div>`;
    }

    function renderTaskIssue(viewModel) {
        const issue = viewModel.issue || {};
        const shouldShow = ['failed', 'no_match', 'degraded_data', 'partial_result', 'needs_disambiguation', 'requires_confirmation']
            .includes(viewModel.status);
        if (!shouldShow && !issue.reason && !issue.type) {
            return '';
        }
        const typeLabel = issue.label ? `${issue.label} · ${issue.type}` : issue.type;
        const typeText = typeLabel ? `类型: ${typeLabel}` : `状态: ${viewModel.status}`;
        const reasonText = issue.reason || viewModel.error || '已保留原始问句和来源上下文';
        const nextText = issue.next_action || '可继续收窄条件、切换分桶或打开候选股验证';
        const context = viewModel.source_context || {};
        const metaItems = [
            context.provider ? `来源 ${context.provider}` : '',
            context.data_as_of ? `数据 ${context.data_as_of}` : '',
            context.cache_status ? `缓存 ${context.cache_status}` : '',
            context.data_status ? `状态 ${context.data_status}` : '',
        ].filter(Boolean);
        const metaHtml = metaItems.length
            ? `<div class="iwencai-issue-meta">${metaItems.map((item) => `<span>${escapeHTML(item)}</span>`).join('')}</div>`
            : '';
        return `<div class="iwencai-empty-note iwencai-status-note" data-iwencai-issue-type="${escapeHTML(issue.type || viewModel.status)}">
            <strong>${escapeHTML(typeText)}</strong>
            <span>${escapeHTML(reasonText)}</span>
            <small>${escapeHTML(nextText)}</small>
            ${metaHtml}
        </div>`;
    }

    function renderIwencaiTask(viewModel) {
        const statusMeta = IWENCAI_STATUS_META[viewModel.status] || IWENCAI_STATUS_META.degraded_data;
        const confidence = `${Math.round((viewModel.intent.confidence || 0) * 100)}%`;
        return `<section class="iwencai-router" data-iwencai-status="${escapeHTML(viewModel.status)}">
            <header class="iwencai-router-head">
                <div>
                    <div class="iwencai-router-kicker">问财任务路由</div>
                    <h4>${escapeHTML(viewModel.query)}</h4>
                    <p>${escapeHTML(viewModel.intent.reason || '已解析为结构化任务')}</p>
                </div>
                <div class="iwencai-router-meta">
                    <span class="iwencai-status-badge status-${escapeHTML(viewModel.status)}">${escapeHTML(statusMeta.label)}</span>
                    <span>${escapeHTML(viewModel.intent.type)}</span>
                    <span>置信度 ${escapeHTML(confidence)}</span>
                </div>
            </header>
            ${renderTaskIssue(viewModel)}
            ${renderConditionChips(viewModel.parsed_conditions)}
            ${renderBucketTabs(viewModel)}
            ${renderBucketContent(viewModel)}
            ${renderGlobalActions(viewModel)}
        </section>`;
    }

    Object.assign(Intelligence, {
        _buildIwencaiTaskViewModel: buildIwencaiTaskViewModel,

        bindIwencai() {
            if (state.iwencaiBound) return;

            const input = document.getElementById('intel-iwencai-input');
            const btn = document.getElementById('intel-iwencai-btn');
            if (!input || !btn) return;

            state.iwencaiBound = true;

            btn.addEventListener('click', () => this.runIwencai());
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.runIwencai();
                }
            });

            if (typeof App.on === 'function') {
                App.on('hotspot:query-iwencai', ({ concept, source_context: sourceContext, selected_bucket: selectedBucket }) => {
                    if (input) input.value = concept;
                    this.runIwencai({
                        selected_bucket: selectedBucket,
                        source_context: sourceContext,
                    });
                });
            }
        },

        async runIwencai(options = {}) {
            const input = document.getElementById('intel-iwencai-input');
            const el = document.getElementById('intel-iwencai-result');
            if (!input || !el) return;

            const optionQuery = typeof options.query === 'string' ? options.query.trim() : '';
            if (optionQuery) {
                input.value = optionQuery;
            }
            const query = input.value.trim();
            if (!query) return;

            const externalSourceContext = options?.source_context && typeof options.source_context === 'object'
                ? options.source_context
                : null;
            const selectedBucket = typeof options?.selected_bucket === 'string' && options.selected_bucket.trim()
                ? options.selected_bucket.trim()
                : null;

            const parsingViewModel = buildIwencaiTaskViewModel({
                success: true,
                status: 'parsing',
                total: 0,
                data: [],
                actions: ['analyze'],
                parsed_conditions: inferParsedConditions(query),
                source_context: externalSourceContext || {},
            }, query, selectedBucket);
            el.innerHTML = renderIwencaiTask(parsingViewModel);

            try {
                const resp = await App.fetchJSON('/api/llm/iwencai', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query,
                        raw_query: externalSourceContext?.raw_query || query,
                        intent_type: externalSourceContext?.intent_type || null,
                        selected_bucket: selectedBucket || externalSourceContext?.selected_bucket || null,
                        source_context: externalSourceContext || null,
                    }),
                    label: '问财查询',
                    timeout: 30000,
                });

                const viewModel = buildIwencaiTaskViewModel({
                    ...resp,
                    source_context: {
                        ...(resp?.source_context && typeof resp.source_context === 'object' ? resp.source_context : {}),
                        ...(externalSourceContext || {}),
                    },
                    selected_bucket: selectedBucket || resp?.selected_bucket,
                }, query, selectedBucket);
                state.iwencaiResult = {
                    query,
                    data: viewModel.data,
                    summaryRows: viewModel.summaryRows,
                    viewModel,
                };
                const codes = viewModel.normalizedRows.map((row) => row.code).filter(Boolean);
                state.iwencaiActionState = {
                    pool: codes.slice(0, 50),
                    watchlistCodes: codes.slice(0, 20),
                    query,
                    selectedBucket: viewModel.selected_bucket,
                    source_context: viewModel.source_context,
                    contextList: viewModel.contextList,
                    candidates: viewModel.normalizedRows,
                    viewModel,
                };
                el.innerHTML = renderIwencaiTask(viewModel);
                return viewModel;
            } catch (e) {
                const viewModel = buildIwencaiTaskViewModel({
                    success: false,
                    status: 'failed',
                    error: e.message,
                    data: [],
                    selected_bucket: selectedBucket,
                    source_context: externalSourceContext || {},
                }, query, selectedBucket);
                state.iwencaiResult = { query, data: [], summaryRows: [], viewModel };
                state.iwencaiActionState = {
                    pool: [],
                    watchlistCodes: [],
                    query,
                    selectedBucket: viewModel.selected_bucket,
                    source_context: viewModel.source_context,
                    contextList: [],
                    candidates: [],
                    viewModel,
                };
                el.innerHTML = renderIwencaiTask(viewModel);
                return viewModel;
            }
        },

        selectIwencaiBucket(bucketId) {
            const el = document.getElementById('intel-iwencai-result');
            const current = state.iwencaiActionState?.viewModel || state.iwencaiResult?.viewModel;
            if (!el || !current || !bucketId) return false;
            const viewModel = buildIwencaiTaskViewModel({
                ...(current.raw_response || { data: current.data, total: current.total }),
                source_context: current.source_context,
            }, current.query, bucketId);
            state.iwencaiResult = {
                query: viewModel.query,
                data: viewModel.data,
                summaryRows: viewModel.summaryRows,
                viewModel,
            };
            state.iwencaiActionState = {
                ...(state.iwencaiActionState || {}),
                pool: viewModel.normalizedRows.map((row) => row.code).filter(Boolean).slice(0, 50),
                watchlistCodes: viewModel.normalizedRows.map((row) => row.code).filter(Boolean).slice(0, 20),
                query: viewModel.query,
                selectedBucket: viewModel.selected_bucket,
                source_context: viewModel.source_context,
                contextList: viewModel.contextList,
                candidates: viewModel.normalizedRows,
                viewModel,
            };
            el.innerHTML = renderIwencaiTask(viewModel);
            return true;
        },

        getLastResult() {
            return state.iwencaiResult;
        },
    });

    if (typeof Intelligence.init === 'function') {
        Intelligence.init();
    }
})();
