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

    function renderIwencaiRow(item, index) {
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
            ? `<span>${App.escapeHTML(String(item.rawCode))}</span>`
            : '';
        const codeHtml = item.code
            ? `<a href="#" class="stock-link iwencai-code" data-code="${App.escapeHTML(item.code)}">${App.escapeHTML(item.code)}</a>`
            : `<span class="text-muted">${App.escapeHTML(String(item.rawCode || '--'))}</span>`;

        return `<tr title="${App.escapeHTML(rawSummary)}">
            <td class="iwencai-rank">${index + 1}</td>
            <td class="iwencai-stock-cell">
                <div class="iwencai-stock-name">${App.escapeHTML(item.name)}</div>
                <div class="iwencai-stock-code">${codeHtml}${rawCodeHtml}</div>
            </td>
            <td class="num">${formatNumber(item.price, 2)}</td>
            <td class="num ${changeClass}">${formatPercent(item.changePct)}</td>
            <td>${App.escapeHTML(compactIndustry(item.industry))}</td>
            <td><div class="iwencai-tags">${tags.length ? tags.map((tag) => `<span>${App.escapeHTML(tag)}</span>`).join('') : '<span>--</span>'}</div></td>
            <td class="num">${formatMoney(item.dde)}</td>
            <td class="num">${formatNumber(item.pe, 2)}</td>
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

    Object.assign(Intelligence, {
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
                App.on('hotspot:query-iwencai', ({ concept }) => {
                    if (input) input.value = concept;
                    this.runIwencai();
                });
            }
        },

        async runIwencai() {
            const input = document.getElementById('intel-iwencai-input');
            const el = document.getElementById('intel-iwencai-result');
            if (!input || !el) return;

            const query = input.value.trim();
            if (!query) return;

            el.innerHTML = '<div class="text-center" style="padding:16px"><span class="spinner"></span> 正在查询问财...</div>';

            try {
                const resp = await App.fetchJSON('/api/llm/iwencai', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query }),
                    label: '问财查询',
                    timeout: 30000,
                });

                if (!resp.success) {
                    el.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(resp.error || '查询失败')}</div>`;
                    return;
                }

                const data = Array.isArray(resp.data) ? resp.data : [];

                if (data.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center">未找到匹配结果</div>';
                    return;
                }

                const displayRows = data.slice(0, 30);
                const normalizedRows = displayRows.map((row) => normalizeIwencaiRow(row));
                state.iwencaiResult = {
                    query,
                    data,
                    summaryRows: normalizedRows.map((row) => toIwencaiSummaryRow(row)),
                };
                const tableHtml = `<div class="table-wrap iwencai-table-wrap"><table class="iwencai-focused-table">
                    <thead><tr>
                        <th>#</th>
                        <th>股票</th>
                        <th class="num">最新价</th>
                        <th class="num">涨跌幅</th>
                        <th>行业</th>
                        <th>概念</th>
                        <th class="num">DDE净额</th>
                        <th class="num">PE</th>
                    </tr></thead>
                    <tbody>${normalizedRows.map((row, index) => renderIwencaiRow(row, index)).join('')}</tbody>
                </table></div>`;

                const codes = data
                    .map((row) => normalizeIwencaiRow(row).code)
                    .filter(Boolean);
                state.iwencaiActionState = {
                    pool: codes.slice(0, 50),
                    watchlistCodes: codes.slice(0, 20),
                    query,
                };

                const actionsHtml = `<div class="iwencai-actions">
                    <span class="text-muted text-xs">共 ${resp.total || data.length} 条，显示前 ${displayRows.length} 条</span>
                    <button class="btn btn-sm" data-intel-action="iwencai-send-screener">发送至选股器</button>
                    <button class="btn btn-sm" data-intel-action="iwencai-analyze">交给 AI 分析</button>
                    <button class="btn btn-sm" data-intel-action="iwencai-add-watchlist">加入自选</button>
                </div>`;

                el.innerHTML = tableHtml + actionsHtml;
            } catch (e) {
                el.innerHTML = `<div class="text-muted text-center">查询失败: ${App.escapeHTML(e.message)}</div>`;
            }
        },

        getLastResult() {
            return state.iwencaiResult;
        },
    });

    if (typeof Intelligence.init === 'function') {
        Intelligence.init();
    }
})();
