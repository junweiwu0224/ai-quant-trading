<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, BarChart3, Bookmark, ChevronRight, ExternalLink, MessageSquareText, RefreshCw, Save, Trash2 } from 'lucide-vue-next'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../api/client'
import type { DecisionResearch } from '../types'

type Row = Record<string, any>
type Tab = 'overview' | 'intraday' | 'context' | 'advanced' | 'flow' | 'book' | 'fundamentals' | 'compare' | 'drawings'
type Indicator = 'MA' | 'BOLL' | 'MACD' | 'KDJ' | 'RSI' | 'WR' | 'OBV'

const route = useRoute()
const tabs: Array<{ key: Tab; label: string }> = [
  { key: 'overview', label: 'K 线与指标' },
  { key: 'intraday', label: '分时与多周期' },
  { key: 'context', label: '共振与新闻' },
  { key: 'advanced', label: '证据与扩展' },
  { key: 'flow', label: '资金流' },
  { key: 'book', label: '盘口' },
  { key: 'fundamentals', label: '财务与估值' },
  { key: 'compare', label: '行业与比较' },
  { key: 'drawings', label: '画线' },
]

const tab = ref<Tab>('overview')
const period = ref('daily')
const count = ref(120)
const data = ref<DecisionResearch | null>(null)
const quote = ref<Row | null>(null)
const kline = ref<Row | null>(null)
const timeline = ref<Row | null>(null)
const timelineMulti = ref<Row | null>(null)
const multiTimeframe = ref<Row | null>(null)
const news = ref<Row | null>(null)
const northbound = ref<Row | null>(null)
const chips = ref<Row | null>(null)
const dragonTiger = ref<Row | null>(null)
const reports = ref<Row | null>(null)
const alphaSignals = ref<Row | null>(null)
const peers = ref<Row | null>(null)
const reportAnalysis = ref<Row | null>(null)
const reportAnalyzing = ref(false)
const capitalFlow = ref<Row | null>(null)
const orderBook = ref<Row | null>(null)
const valuation = ref<Row | null>(null)
const profitTrend = ref<Row | null>(null)
const shareholders = ref<Row | null>(null)
const dividends = ref<Row | null>(null)
const announcements = ref<Row | null>(null)
const industry = ref<Row | null>(null)
const comparison = ref<Row | null>(null)
const drawings = ref<Row[]>([])
const loading = ref(false)
const tabLoading = ref(false)
const message = ref('')
const tabMessage = ref('')
const updatedAt = ref('')
const indicator = ref<Indicator>('MA')
const compareCodes = ref('600519,000001,300750')
const drawingName = ref('趋势线')
const drawingDate = ref('')
const drawingPrice = ref('')
let loadSequence = 0

const symbol = computed(() => String(route.params.symbol || ''))
const market = computed(() => String(route.params.market || 'CN').toUpperCase())
const capability = computed<Row>(() => (data.value?.market as Row | undefined) || {})
const capabilityMatchesRoute = computed(() => String(capability.value.market || '').toUpperCase() === market.value)
const canLoadLegacyResearch = computed(() => market.value === 'CN' && capabilityMatchesRoute.value)
const capabilityMessage = computed(() => {
  const reason = String(capability.value.fallback_reason || capability.value.source_status || '').trim()
  if (market.value !== 'CN') {
    return `${capability.value.label || market.value} 当前没有已连接的研究 provider，已停止调用 A 股数据接口。${reason ? `原因：${reason}` : ''}`
  }
  if (!capabilityMatchesRoute.value) return '市场能力响应与当前路由不一致，已停止加载研究数据。'
  return '当前市场能力未确认，已停止加载研究数据。'
})
const bars = computed<Row[]>(() => {
  const source = Array.isArray(kline.value?.klines) ? kline.value.klines : data.value?.bars || []
  return source.filter((item: Row) => item && Number(item.close) > 0)
})
const latest = computed(() => bars.value[bars.value.length - 1] || null)
const firstClose = computed(() => Number(bars.value[0]?.close || 0))
const totalChange = computed(() => firstClose.value > 0 && Number(latest.value?.close) > 0 ? (Number(latest.value.close) / firstClose.value - 1) * 100 : null)
const sourceLabel = computed(() => String(kline.value?.source || data.value?.market?.source || '本地研究 API'))
const sourceDate = computed(() => String(kline.value?.latest_local_date || latest.value?.date || '未知'))
const stale = computed(() => Boolean(kline.value?.stale || kline.value?.degraded || data.value?.market?.automatic_push === false))

function clearResearchData() {
  data.value = null
  quote.value = null
  kline.value = null
  timeline.value = null
  timelineMulti.value = null
  multiTimeframe.value = null
  news.value = null
  northbound.value = null
  chips.value = null
  dragonTiger.value = null
  reports.value = null
  alphaSignals.value = null
  peers.value = null
  reportAnalysis.value = null
  capitalFlow.value = null
  orderBook.value = null
  valuation.value = null
  profitTrend.value = null
  shareholders.value = null
  dividends.value = null
  announcements.value = null
  industry.value = null
  comparison.value = null
  drawings.value = []
}

const chartPoints = computed(() => {
  const values = bars.value.map((bar) => Number(bar.close)).filter((value) => Number.isFinite(value) && value > 0)
  if (!values.length) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const spread = max - min || Math.max(max * 0.01, 1)
  return bars.value.map((bar, index) => ({
    x: 18 + (index / Math.max(1, values.length - 1)) * 724,
    y: 226 - ((Number(bar.close) - min) / spread) * 196,
    close: Number(bar.close),
  }))
})
function chartCoordinate(value: number): string {
  return Number.isFinite(value) ? (Math.round(value * 10) / 10).toString() : '0'
}

const linePath = computed(() => chartPoints.value.map((point, index) => `${index ? 'L' : 'M'} ${chartCoordinate(point.x)} ${chartCoordinate(point.y)}`).join(' '))
const volumeBars = computed(() => {
  const values = bars.value.map((bar) => Number(bar.volume || 0))
  const max = Math.max(...values, 1)
  return bars.value.slice(-60).map((bar, index, list) => ({
    key: `${bar.date}-${index}`,
    height: Math.max(4, Number(bar.volume || 0) / max * 54),
    positive: index === 0 || Number(bar.close) >= Number(list[index - 1]?.close),
  }))
})
const quoteMetrics = computed(() => {
  const item = quote.value || {}
  return [
    ['最新价', item.price], ['涨跌幅', item.change_pct == null ? null : `${item.change_pct}%`],
    ['开盘', item.open], ['最高', item.high], ['最低', item.low], ['成交量', item.volume],
    ['成交额', item.amount], ['换手率', item.turnover_rate == null ? null : `${item.turnover_rate}%`],
  ]
})
const compareSeries = computed(() => {
  const value = comparison.value?.data
  return value && typeof value === 'object' ? Object.entries(value as Record<string, Row>) : []
})
const timeframeRows = computed(() => {
  const source = multiTimeframe.value || {}
  return [
    ['daily', '日线'], ['weekly', '周线'], ['monthly', '月线'],
  ].map(([key, label]) => ({ key, label, ...(source[key] && typeof source[key] === 'object' ? source[key] : {}) }))
})
const newsRows = computed(() => list(news.value, 'news'))
const chipRows = computed(() => list(chips.value, 'chips'))
const northboundRows = computed(() => list(northbound.value, 'records'))
const dragonRows = computed(() => list(dragonTiger.value, 'records'))
const reportRows = computed(() => list(reports.value, 'reports'))
const alphaSignalRows = computed(() => list(alphaSignals.value, 'signals'))
const peerRows = computed(() => list(peers.value, 'peers'))
const indicatorRows = computed(() => Object.entries(indicatorSnapshot(bars.value.map((bar) => Number(bar.close)).filter((value) => Number.isFinite(value)), indicator.value)).map(([label, value]) => ({ label, value })))
const hasIndicatorValue = computed(() => indicatorRows.value.some((item) => item.value != null))
const indicatorHistory = computed(() => {
  const closes = bars.value.map((bar) => Number(bar.close)).filter((value) => Number.isFinite(value))
  const start = Math.max(0, closes.length - 12)
  return bars.value.slice(start).map((bar, index) => ({ date: bar.date, ...indicatorSnapshot(closes.slice(0, start + index + 1), indicator.value) })) as Row[]
})
const fundamentalRows = computed(() => {
  const item = { ...(quote.value || {}), ...(valuation.value || {}) }
  return [
    ['市盈率 TTM', item.pe_ttm], ['市销率', item.ps_ratio], ['股息率', item.dividend_yield],
    ['每股收益', item.eps], ['每股净资产', item.bps], ['营业收入', item.revenue],
    ['营收增速', item.revenue_growth], ['净利润', item.net_profit], ['净利增速', item.net_profit_growth],
    ['毛利率', item.gross_margin], ['净利率', item.net_margin], ['ROE', item.roe], ['资产负债率', item.debt_ratio],
  ]
})

function list(value: unknown, key: string): Row[] {
  const item = value as Row | null
  return Array.isArray(item?.[key]) ? item[key] : []
}

function numberOrDash(value: unknown, digits = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function signed(value: unknown, suffix = '') {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const formatted = number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })
  return `${number > 0 ? '+' : ''}${formatted}${suffix}`
}

function actionClass(value: unknown) {
  return Number(value) >= 0 ? 'good' : 'bad'
}

function average(values: number[], period: number) {
  if (values.length < period) return null
  return values.slice(-period).reduce((total, item) => total + item, 0) / period
}

function standardDeviation(values: number[], period: number) {
  const sample = values.slice(-period)
  if (sample.length < period) return null
  const mean = sample.reduce((total, item) => total + item, 0) / period
  return Math.sqrt(sample.reduce((total, item) => total + (item - mean) ** 2, 0) / period)
}

function rsi(values: number[], period = 14) {
  if (values.length < period + 1) return null
  const changes = values.slice(-period - 1).slice(1).map((item, index) => item - values.slice(-period - 1)[index])
  const gains = changes.reduce((total, item) => total + Math.max(item, 0), 0) / period
  const losses = changes.reduce((total, item) => total + Math.max(-item, 0), 0) / period
  return losses === 0 ? 100 : 100 - 100 / (1 + gains / losses)
}

function indicatorSnapshot(values: number[], kind: Indicator): Record<string, number | null> {
  if (kind === 'MA') return { MA5: average(values, 5), MA10: average(values, 10), MA20: average(values, 20) }
  if (kind === 'BOLL') {
    const middle = average(values, 20)
    const deviation = standardDeviation(values, 20)
    return { 中轨: middle, 上轨: middle == null || deviation == null ? null : middle + deviation * 2, 下轨: middle == null || deviation == null ? null : middle - deviation * 2 }
  }
  if (kind === 'RSI') return { RSI14: rsi(values) }
  if (kind === 'MACD') {
    if (values.length < 35) return { DIF: null, DEA: null, 柱: null }
    let ema12 = values[0]
    let ema26 = values[0]
    const diffs: number[] = []
    for (const close of values) {
      ema12 = ema12 * 11 / 13 + close * 2 / 13
      ema26 = ema26 * 25 / 27 + close * 2 / 27
      diffs.push(ema12 - ema26)
    }
    let dea = diffs[0]
    for (const diff of diffs) dea = dea * 8 / 10 + diff * 2 / 10
    const dif = diffs[diffs.length - 1]
    return { DIF: dif, DEA: dea, 柱: (dif - dea) * 2 }
  }
  if (kind === 'WR') {
    const period = 14
    const sample = values.slice(-period)
    if (sample.length < period) return { WR14: null }
    const high = Math.max(...sample)
    const low = Math.min(...sample)
    return { WR14: high === low ? -50 : -100 * (high - values[values.length - 1]) / (high - low) }
  }
  if (kind === 'OBV') {
    if (values.length < 2) return { OBV: null }
    const volumes = bars.value.map((bar) => Number(bar.volume || 0)).filter((value) => Number.isFinite(value))
    let obv = 0
    for (let index = 1; index < values.length; index += 1) obv += (values[index] >= values[index - 1] ? 1 : -1) * (volumes[index] || 0)
    return { OBV: obv }
  }
  if (values.length < 9) return { K: null, D: null, J: null }
  const kdjWindow = values.slice(-9)
  const high = Math.max(...kdjWindow)
  const low = Math.min(...kdjWindow)
  const rsv = high === low ? 50 : (values[values.length - 1] - low) / (high - low) * 100
  const k = 2 / 3 * 50 + 1 / 3 * rsv
  const d = 2 / 3 * 50 + 1 / 3 * k
  return { K: k, D: d, J: 3 * k - 2 * d }
}

function trendLabel(value: unknown) {
  if (value === 'bullish') return '看多'
  if (value === 'bearish') return '看空'
  return '中性'
}

function trendClass(value: unknown) {
  if (value === 'bullish') return 'good'
  if (value === 'bearish') return 'bad'
  return 'muted'
}

function sentimentLabel(value: unknown) {
  const score = Number(value)
  if (!Number.isFinite(score)) return '未知'
  if (score >= 0.1) return '偏多'
  if (score <= -0.1) return '偏空'
  return '中性'
}

function signalText(value: unknown) {
  return Array.isArray(value) && value.length ? value.map((item) => String((item as Row).name || '')).filter(Boolean).join('、') : '没有额外信号'
}

async function loadKline() {
  if (!symbol.value || !canLoadLegacyResearch.value) return
  const requestedSymbol = symbol.value
  const requestedMarket = market.value
  try {
    const nextKline = await api.stockKline(requestedSymbol, period.value, count.value, requestedMarket)
    if (requestedSymbol === symbol.value && requestedMarket === market.value) kline.value = nextKline
  } catch (error) {
    kline.value = null
    tabMessage.value = error instanceof Error ? error.message : 'K 线加载失败'
  }
}

async function load() {
  const requestedSymbol = symbol.value
  const requestedMarket = market.value
  const sequence = ++loadSequence
  if (!requestedSymbol) {
    message.value = '缺少标的代码'
    return
  }
  loading.value = true
  message.value = ''
  tabMessage.value = ''
  clearResearchData()
  try {
    const [researchResult] = await Promise.allSettled([
      api.decisionResearch(requestedMarket, requestedSymbol),
    ])
    if (sequence !== loadSequence) return
    if (researchResult.status === 'rejected') {
      message.value = researchResult.reason instanceof Error ? researchResult.reason.message : '研究能力加载失败'
      return
    }

    data.value = researchResult.value
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    if (!canLoadLegacyResearch.value) {
      message.value = capabilityMessage.value
      return
    }

    const results = await Promise.allSettled([
      api.stockQuote(requestedSymbol, requestedMarket),
      api.stockKline(requestedSymbol, period.value, count.value, requestedMarket),
      api.stockDrawings(requestedSymbol, requestedMarket),
    ])
    if (sequence !== loadSequence) return
    const [quoteResult, klineResult, drawingResult] = results
    if (quoteResult.status === 'fulfilled') quote.value = quoteResult.value
    if (klineResult.status === 'fulfilled') kline.value = klineResult.value
    if (drawingResult.status === 'fulfilled') drawings.value = list(drawingResult.value, 'drawings')
    if (results.every((item) => item.status === 'rejected')) message.value = '研究数据暂时不可用，请检查数据源状态。'
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function loadTab(nextTab: Tab) {
  tab.value = nextTab
  tabMessage.value = ''
  if (!symbol.value || nextTab === 'overview') return
  if (!canLoadLegacyResearch.value) {
    tabMessage.value = capabilityMessage.value
    return
  }
  if (nextTab === 'drawings') return
  const requestedMarket = market.value
  tabLoading.value = true
  try {
    if (nextTab === 'intraday') {
      const [intraday, multi] = await Promise.all([api.stockTimeline(symbol.value, requestedMarket), api.stockTimelineMulti(symbol.value, 5, requestedMarket)])
      timeline.value = intraday
      timelineMulti.value = multi
    } else if (nextTab === 'context') {
      const [timeframe, newsResponse] = await Promise.all([api.stockMultiTimeframe(symbol.value, requestedMarket), api.stockNews(symbol.value, requestedMarket)])
      multiTimeframe.value = timeframe
      news.value = newsResponse
    } else if (nextTab === 'advanced') {
      const end = new Date()
      const start = new Date(end)
      start.setMonth(start.getMonth() - 6)
      const signalQuery = new URLSearchParams({ code: symbol.value, start_date: start.toISOString().slice(0, 10), end_date: end.toISOString().slice(0, 10) }).toString()
      const [chipsResult, dragonResult, reportsResult, northboundResult, alphaResult, peersResult] = await Promise.allSettled([
        api.stockChips(symbol.value, 120, requestedMarket), api.stockDragonTiger(symbol.value, 90, requestedMarket), api.stockReports(symbol.value, 10, requestedMarket),
        api.stockNorthbound(symbol.value, requestedMarket), api.alphaKlineSignals(signalQuery, requestedMarket), api.valuationPeers(symbol.value, 8, requestedMarket),
      ])
      if (chipsResult.status === 'fulfilled') chips.value = chipsResult.value
      if (dragonResult.status === 'fulfilled') dragonTiger.value = dragonResult.value
      if (reportsResult.status === 'fulfilled') reports.value = reportsResult.value
      if (northboundResult.status === 'fulfilled') northbound.value = northboundResult.value
      if (alphaResult.status === 'fulfilled') alphaSignals.value = alphaResult.value
      if (peersResult.status === 'fulfilled') peers.value = peersResult.value
    } else if (nextTab === 'flow') {
      capitalFlow.value = await api.stockCapitalFlow(symbol.value, 30, requestedMarket)
    } else if (nextTab === 'book') {
      orderBook.value = await api.stockOrderBook(symbol.value, requestedMarket)
    } else if (nextTab === 'fundamentals') {
      const [value, profit, holders, payout, notices, peer] = await Promise.allSettled([
        api.valuation(symbol.value, requestedMarket), api.stockProfitTrend(symbol.value, requestedMarket), api.stockShareholders(symbol.value, requestedMarket),
        api.stockDividends(symbol.value, requestedMarket), api.stockAnnouncements(symbol.value, requestedMarket), api.stockIndustryComparison(symbol.value, requestedMarket),
      ])
      if (value.status === 'fulfilled') valuation.value = value.value
      if (profit.status === 'fulfilled') profitTrend.value = profit.value
      if (holders.status === 'fulfilled') shareholders.value = holders.value
      if (payout.status === 'fulfilled') dividends.value = payout.value
      if (notices.status === 'fulfilled') announcements.value = notices.value
      if (peer.status === 'fulfilled') industry.value = peer.value
    } else if (nextTab === 'compare') {
      const codes = [...new Set(compareCodes.value.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean))].slice(0, 5)
      if (!codes.includes(symbol.value)) codes.unshift(symbol.value)
      comparison.value = await api.stockCompare(codes.slice(0, 5), period.value, 60, requestedMarket)
      if (!industry.value) industry.value = await api.stockIndustryComparison(symbol.value, requestedMarket)
    }
  } catch (error) {
    tabMessage.value = error instanceof Error ? error.message : '研究模块加载失败'
  } finally {
    tabLoading.value = false
  }
}

async function saveDrawing() {
  const price = Number(drawingPrice.value)
  if (!drawingName.value.trim() || !drawingDate.value || !Number.isFinite(price) || price <= 0) {
    tabMessage.value = '请填写画线名称、日期和有效价格'
    return
  }
  tabLoading.value = true
  try {
    await api.saveStockDrawing(symbol.value, { overlay_name: drawingName.value.trim(), points: [{ date: drawingDate.value, price }], styles: {} }, market.value)
    const response = await api.stockDrawings(symbol.value, market.value)
    drawings.value = list(response, 'drawings')
    drawingDate.value = ''
    drawingPrice.value = ''
    tabMessage.value = '画线已保存'
  } catch (error) {
    tabMessage.value = error instanceof Error ? error.message : '画线保存失败'
  } finally {
    tabLoading.value = false
  }
}

async function removeDrawing(id: unknown) {
  if (id === null || id === undefined) return
  tabLoading.value = true
  try {
    await api.deleteStockDrawing(String(id), market.value)
    drawings.value = drawings.value.filter((item) => String(item.id) !== String(id))
  } catch (error) {
    tabMessage.value = error instanceof Error ? error.message : '画线删除失败'
  } finally {
    tabLoading.value = false
  }
}

async function clearDrawings() {
  tabLoading.value = true
  try {
    await api.deleteAllStockDrawings(symbol.value, market.value)
    drawings.value = []
    tabMessage.value = '画线已清空'
  } catch (error) {
    tabMessage.value = error instanceof Error ? error.message : '画线清空失败'
  } finally {
    tabLoading.value = false
  }
}

async function analyzeReport(row: Row) {
  if (!row.title) return
  reportAnalyzing.value = true
  reportAnalysis.value = null
  try {
    reportAnalysis.value = await api.analyzeReport({ title: row.title, content: row.summary || '', stock_code: symbol.value, stock_name: quote.value?.name || '' }, market.value)
  } catch (error) {
    tabMessage.value = error instanceof Error ? error.message : 'AI 解读失败'
  } finally {
    reportAnalyzing.value = false
  }
}

watch(() => [route.params.market, route.params.symbol], () => { void load() }, { immediate: true })
watch(period, () => { void loadKline() })
</script>

<template>
  <section>
    <div class="page-head research-head">
      <div>
        <div class="small"><RouterLink to="/app/decision" class="muted"><ArrowLeft :size="14" />返回决策中心</RouterLink></div>
        <h1>{{ quote?.name || symbol }} <span class="muted">{{ symbol }}</span></h1>
        <p>研究工作区保留来源、时间和覆盖状态；手动研究不会改变策略版本、自动推送资格或下一次 Worker 任务。</p>
      </div>
      <div class="form-actions"><RouterLink class="button ghost" :to="`/app/research/${market}/${encodeURIComponent(symbol)}`"><ArrowLeft :size="15" />回到研究首页</RouterLink><button class="button" :disabled="loading" type="button" @click="load"><RefreshCw :size="16" />刷新</button></div>
    </div>

    <div v-if="message" class="error-box" role="alert">{{ message }}</div>
    <div v-if="loading && !quote && !data" class="empty">读取 {{ symbol }} 的研究输入…</div>
      <template v-else>
      <section class="summary-strip">
        <div v-for="item in quoteMetrics" :key="item[0]" class="summary-item"><span>{{ item[0] }}</span><strong :class="item[0] === '涨跌幅' ? actionClass(quote?.change_pct) : ''">{{ item[0] === '涨跌幅' ? signed(quote?.change_pct, '%') : numberOrDash(item[1]) }}</strong><small>{{ quote?.data_date || sourceDate }}</small></div>
      </section>

      <section class="panel research-source-panel">
        <div class="panel-body"><div class="data-source"><span class="tag" :class="stale ? 'warn' : 'good'">{{ stale ? '降级/手动研究' : '来源可用' }}</span><span>市场：{{ data?.market?.label || market }}</span><span>来源：{{ sourceLabel }}</span><span>最新数据：{{ sourceDate }}</span><span>刷新：{{ updatedAt || '—' }}</span><span>自动推送：{{ data?.market?.automatic_push ? '按资格开放' : '关闭' }}</span></div></div>
      </section>
      <section v-if="!canLoadLegacyResearch" class="panel research-capability-panel">
        <div class="panel-body capability-state"><span class="tag warn">能力阻断</span><strong>{{ market === 'CN' ? '研究能力未确认' : '当前市场仅保留受控研究入口' }}</strong><span>{{ capabilityMessage }}</span></div>
      </section>

      <nav class="workspace-tabs" aria-label="研究模块"><button v-for="item in tabs" :key="item.key" type="button" :disabled="!canLoadLegacyResearch && item.key !== 'overview'" :class="{ active: tab === item.key }" @click="loadTab(item.key)">{{ item.label }}</button></nav>
      <div v-if="tabMessage" class="error-box research-message" role="alert">{{ tabMessage }}</div>
      <div v-if="tabLoading" class="empty">正在读取 {{ tabs.find((item) => item.key === tab)?.label }}…</div>

      <template v-else-if="tab === 'overview'">
        <section class="section-grid two research-grid">
          <section class="panel"><div class="panel-head"><div><h2>收盘价走势</h2><p>{{ period }} · {{ bars.length }} 根有效 K 线 · 末值 {{ latest?.date || '—' }}</p></div><div class="compact-controls"><select v-model="period" class="field-select" aria-label="K线周期"><option value="daily">日线</option><option value="weekly">周线</option><option value="monthly">月线</option><option value="60m">60 分钟</option><option value="30m">30 分钟</option><option value="15m">15 分钟</option><option value="5m">5 分钟</option><option value="1m">1 分钟</option></select><select v-model="count" class="field-select" aria-label="K线数量"><option :value="60">60</option><option :value="120">120</option><option :value="240">240</option></select></div></div><div class="panel-body chart-panel"><div v-if="!linePath" class="empty">暂无可绘制的收盘价，不能用 0 填充图表。</div><template v-else><svg class="price-chart" viewBox="0 0 760 245" role="img" aria-label="收盘价走势"><line x1="18" y1="226" x2="742" y2="226" class="chart-axis" /><line x1="18" y1="30" x2="742" y2="30" class="chart-grid" /><path :d="linePath" class="chart-line" /><circle v-for="point in chartPoints.filter((_, index) => index === chartPoints.length - 1)" :key="point.x" :cx="point.x" :cy="point.y" r="4" class="chart-dot" /></svg><div class="chart-labels"><span>{{ bars[0]?.date || '—' }}</span><strong>{{ numberOrDash(latest?.close) }}</strong><span>{{ latest?.date || '—' }}</span></div><div class="volume-strip" aria-label="成交量"><span v-for="bar in volumeBars" :key="bar.key" :class="bar.positive ? 'up' : 'down'" :style="{ height: `${bar.height}px` }" /></div></template></div></section>
          <section class="panel"><div class="panel-head"><div><h2>决策输入摘要</h2><p>这部分与确定性决策输入保持只读隔离。</p></div><BarChart3 :size="19" class="faint" /></div><div class="panel-body"><div class="check-list"><div class="check-row"><div class="check-copy"><strong>区间变化</strong><span>当前返回区间的首末有效收盘价</span></div><span class="tag" :class="totalChange != null && totalChange >= 0 ? 'good' : 'bad'">{{ totalChange == null ? '—' : signed(totalChange, '%') }}</span></div><div class="check-row"><div class="check-copy"><strong>输入覆盖</strong><span>{{ bars.length }} 根有效 K 线；缺失值不补 0</span></div><span class="tag" :class="bars.length ? 'good' : 'bad'">{{ bars.length ? '可读' : '缺失' }}</span></div><div class="check-row"><div class="check-copy"><strong>来源状态</strong><span>{{ kline?.degraded_reason || data?.market?.fallback_reason || '未发现额外降级说明' }}</span></div><span class="tag" :class="stale ? 'warn' : 'good'">{{ stale ? '需复核' : '正常' }}</span></div></div><RouterLink class="button primary" :to="{ path: '/app/decision', query: { symbol, market, source: 'research' } }">查看决策中心 <ChevronRight :size="15" /></RouterLink></div></section>
        </section>
        <section class="panel indicator-panel"><div class="panel-head"><div><h2>技术指标</h2><p>按当前 K 线在浏览器内确定性计算，样本不足时明确显示缺失。</p></div><select v-model="indicator" class="field-select" aria-label="技术指标"><option value="MA">均线 MA</option><option value="BOLL">布林带 BOLL</option><option value="MACD">MACD</option><option value="KDJ">KDJ</option><option value="RSI">RSI</option><option value="WR">WR</option><option value="OBV">OBV</option></select></div><div class="panel-body"><div v-if="!bars.length || !hasIndicatorValue" class="empty">当前数据不足以计算 {{ indicator }}。</div><template v-else><div class="metric-grid"><div v-for="item in indicatorRows" :key="item.label" class="metric-cell"><span>{{ item.label }}</span><strong>{{ numberOrDash(item.value, 4) }}</strong></div></div><div class="table-scroll indicator-history"><table class="decision-table"><thead><tr><th>日期</th><th v-for="item in indicatorRows" :key="item.label">{{ item.label }}</th></tr></thead><tbody><tr v-for="row in indicatorHistory.slice().reverse()" :key="row.date"><td>{{ row.date }}</td><td v-for="item in indicatorRows" :key="item.label">{{ numberOrDash(row[item.label], 4) }}</td></tr></tbody></table></div></template></div></section>
        <section class="panel"><div class="panel-head"><div><h2>最近行情</h2><p>表格保留原始日期和来源语义，适合在移动端横向查看。</p></div></div><div class="panel-body"><div v-if="!bars.length" class="empty"><strong>暂无本地数据</strong><span>当前数据源未返回该标的行情，不能据此生成自动动作。</span></div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>涨跌</th><th>成交量</th></tr></thead><tbody><tr v-for="bar in bars.slice().reverse()" :key="bar.date"><td>{{ bar.date }}</td><td>{{ numberOrDash(bar.open) }}</td><td>{{ numberOrDash(bar.high) }}</td><td>{{ numberOrDash(bar.low) }}</td><td>{{ numberOrDash(bar.close) }}</td><td :class="actionClass(bar.change_pct ?? Number(bar.close) - Number(bar.open))">{{ bar.change_pct == null ? '—' : signed(bar.change_pct, '%') }}</td><td>{{ numberOrDash(bar.volume, 0) }}</td></tr></tbody></table></div></div></section>
      </template>

      <template v-else-if="tab === 'intraday'">
        <section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>今日分时</h2><p>完成状态和时间由行情服务返回；空数据不绘制虚假曲线。</p></div></div><div class="panel-body"><div v-if="!list(timeline, 'trends').length" class="empty">当前没有分时数据。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>成交价</th><th>均价</th><th>成交量</th><th>成交额</th></tr></thead><tbody><tr v-for="row in list(timeline, 'trends').slice().reverse()" :key="row.time"><td>{{ row.time }}</td><td>{{ numberOrDash(row.close) }}</td><td>{{ numberOrDash(row.avg_price) }}</td><td>{{ numberOrDash(row.volume, 0) }}</td><td>{{ numberOrDash(row.amount, 0) }}</td></tr></tbody></table></div></div></section><section class="panel"><div class="panel-head"><div><h2>多日分时上下文</h2><p>辅助观察最近 {{ list(timelineMulti, 'days').length }} 个交易日的开收区间。</p></div></div><div class="panel-body"><div v-if="!list(timelineMulti, 'days').length" class="empty">暂无多日分时。</div><div v-else class="check-list"><div v-for="row in list(timelineMulti, 'days')" :key="row.date" class="check-row"><div class="check-copy"><strong>{{ row.date }}</strong><span>开 {{ numberOrDash(row.open ?? row.bars?.[0]?.open) }} · 收 {{ numberOrDash(row.close ?? row.bars?.[row.bars?.length - 1]?.close) }}</span></div><span class="tag">{{ row.bars?.length || 1 }} 个点</span></div></div></div></section></section>
      </template>

      <template v-else-if="tab === 'context'"><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>多周期共振</h2><p>日线、周线、月线来自后端同一行情输入；这只是研究上下文。</p></div><span v-if="multiTimeframe" class="tag" :class="trendClass(multiTimeframe.resonance)">{{ multiTimeframe.resonance_label || '多空分歧' }} · {{ numberOrDash(multiTimeframe.strength, 0) }}/100</span></div><div class="panel-body"><div v-if="!multiTimeframe || !multiTimeframe.success" class="empty">暂无多周期共振数据。</div><div v-else class="timeframe-grid"><div v-for="row in timeframeRows" :key="row.key" class="timeframe-row"><div><strong>{{ row.label }}</strong><span :class="trendClass(row.trend)">{{ trendLabel(row.trend) }}</span></div><span class="tag">强度 {{ numberOrDash(row.strength, 0) }}/100</span><p>{{ signalText(row.signals) }}</p></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>新闻与情绪</h2><p>新闻作为证据上下文展示，不直接改变确定性动作。</p></div><div class="head-actions"><span v-if="news?.evidence_snapshot_id" class="tag">证据快照 {{ String(news.evidence_snapshot_id).slice(0, 12) }}</span><span v-if="news?.sentiment" class="tag" :class="trendClass(Number(news.sentiment.sentiment_score) >= 0.1 ? 'bullish' : Number(news.sentiment.sentiment_score) <= -0.1 ? 'bearish' : 'neutral')">{{ sentimentLabel(news.sentiment.sentiment_score) }} {{ numberOrDash(news.sentiment.sentiment_score, 2) }}</span></div></div><div class="panel-body"><div v-if="!news || !newsRows.length" class="empty">暂无个股新闻。</div><div v-else class="check-list"><a v-for="row in newsRows.slice(0, 15)" :key="row.id || row.title || row.time" class="check-row link-row" :href="row.url || row.link || undefined" target="_blank" rel="noopener noreferrer"><div class="check-copy"><strong>{{ row.title || '个股新闻' }}</strong><span>{{ row.source || '新闻' }} · {{ row.time || row.date || row.publish_time || '时间未知' }}<template v-if="row.sentiment != null"> · 情绪 {{ numberOrDash(row.sentiment, 2) }}</template></span></div><ExternalLink :size="15" /></a></div></div></section></section></template>

      <template v-else-if="tab === 'advanced'"><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>筹码分布</h2><p>后端基于历史成交量估算，缺失时不补成真实持仓。</p></div></div><div class="panel-body"><div v-if="!chips || !chipRows.length" class="empty">暂无筹码分布数据。</div><template v-else><div class="metric-grid"><div class="metric-cell"><span>获利比例</span><strong>{{ numberOrDash(chips.profit_ratio) }}%</strong></div><div class="metric-cell"><span>平均成本</span><strong>{{ numberOrDash(chips.avg_cost) }}</strong></div><div class="metric-cell"><span>90% 集中区间</span><strong>{{ chips.concentration_90?.[0] ?? '—' }} ~ {{ chips.concentration_90?.[1] ?? '—' }}</strong></div></div><div class="table-scroll analysis-table"><table class="decision-table"><thead><tr><th>价格</th><th>筹码占比</th></tr></thead><tbody><tr v-for="row in chipRows.slice().reverse().slice(0, 30)" :key="row.price"><td>{{ numberOrDash(row.price) }}</td><td>{{ numberOrDash(row.pct) }}%</td></tr></tbody></table></div></template></div></section><section class="panel"><div class="panel-head"><div><h2>北向资金</h2><p>持股记录仅作为资金证据，不直接触发策略动作。</p></div></div><div class="panel-body"><div v-if="!northbound || !northboundRows.length" class="empty">暂无北向资金记录。</div><template v-else><div class="metric-grid"><div class="metric-cell"><span>最新持股</span><strong>{{ numberOrDash(northbound.latest?.hold_shares, 0) }}</strong></div><div class="metric-cell"><span>流通股占比</span><strong>{{ numberOrDash(northbound.latest?.hold_ratio, 2) }}%</strong></div><div class="metric-cell"><span>A 股占比</span><strong>{{ numberOrDash(northbound.latest?.a_ratio, 2) }}%</strong></div></div><div class="table-scroll analysis-table"><table class="decision-table"><thead><tr><th>日期</th><th>持股数</th><th>流通占比</th><th>变动股数</th></tr></thead><tbody><tr v-for="row in northboundRows.slice(0, 20)" :key="row.date"><td>{{ row.date }}</td><td>{{ numberOrDash(row.hold_shares, 0) }}</td><td>{{ numberOrDash(row.hold_ratio, 2) }}%</td><td :class="actionClass(row.change_shares)">{{ signed(row.change_shares) }}</td></tr></tbody></table></div></template></div></section></section><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>龙虎榜</h2><p>上榜后收益是历史描述，不是未来承诺。</p></div><span v-if="dragonTiger?.summary" class="tag">{{ dragonTiger.summary.total_listings || 0 }} 次</span></div><div class="panel-body"><div v-if="!dragonTiger || !dragonRows.length" class="empty">暂无龙虎榜记录。</div><template v-else><div class="metric-grid"><div class="metric-cell"><span>净买入合计</span><strong :class="actionClass(dragonTiger.summary?.total_net_amount)">{{ signed(dragonTiger.summary?.total_net_amount) }}</strong></div><div class="metric-cell"><span>上榜后 5 日均收益</span><strong :class="actionClass(dragonTiger.summary?.avg_return_5d)">{{ signed(dragonTiger.summary?.avg_return_5d, '%') }}</strong></div></div><div class="table-scroll analysis-table"><table class="decision-table"><thead><tr><th>日期</th><th>涨跌</th><th>净额</th><th>原因</th></tr></thead><tbody><tr v-for="row in dragonRows.slice(0, 12)" :key="row.date"><td>{{ row.date }}</td><td :class="actionClass(row.change_rate)">{{ signed(row.change_rate, '%') }}</td><td :class="actionClass(row.net_amount)">{{ signed(row.net_amount) }}</td><td>{{ row.reasons?.join('、') || row.reason || '—' }}</td></tr></tbody></table></div></template></div></section><section class="panel"><div class="panel-head"><div><h2>Alpha 信号</h2><p>保留信号日期、类型和来源；不会由研究页晋级策略。</p></div></div><div class="panel-body"><div v-if="!alphaSignals || !alphaSignalRows.length" class="empty">暂无 Alpha 信号。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>类型</th><th>价格</th><th>因子 / 策略</th></tr></thead><tbody><tr v-for="row in alphaSignalRows.slice().reverse().slice(0, 20)" :key="`${row.date || row.time}-${row.type}-${row.price}`"><td>{{ row.date || row.time || '—' }}</td><td :class="actionClass(row.type === 'buy' ? 1 : row.type === 'sell' ? -1 : 0)">{{ row.type === 'buy' ? '买入' : row.type === 'sell' ? '卖出' : row.type || '—' }}</td><td>{{ numberOrDash(row.price) }}</td><td>{{ row.factor || row.strategy || '—' }}</td></tr></tbody></table></div></div></section></section><section class="panel"><div class="panel-head"><div><h2>研究报告</h2><p>研报内容是外部证据；AI 解读只在点击后运行，不改变确定性决策。</p></div><span v-if="reports?.total != null" class="tag">{{ reports.total }} 篇</span></div><div class="panel-body"><div v-if="!reports || !reportRows.length" class="empty">暂无研究报告。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>标题</th><th>机构</th><th>评级</th><th>操作</th></tr></thead><tbody><tr v-for="row in reportRows" :key="`${row.date}-${row.title}`"><td>{{ row.date || '—' }}</td><td><a v-if="row.url" class="link-row" :href="row.url" target="_blank" rel="noopener noreferrer">{{ row.title || '研究报告' }} <ExternalLink :size="13" /></a><span v-else>{{ row.title || '研究报告' }}</span></td><td>{{ row.org || '—' }}</td><td>{{ row.rating || '—' }}</td><td><button class="button" type="button" :disabled="reportAnalyzing" @click="analyzeReport(row)"><MessageSquareText :size="14" />AI 解读</button></td></tr></tbody></table></div><div v-if="reportAnalyzing" class="empty">AI 解读运行中…</div><div v-if="reportAnalysis" class="result-code report-analysis-result">{{ reportAnalysis.analysis || reportAnalysis.error || '暂无解读结果' }}</div></div></section><section class="panel"><div class="panel-head"><div><h2>估值同行</h2><p>{{ peers?.industry || '行业' }} · PEG 和增速覆盖不足时保留空值。</p></div></div><div class="panel-body"><div v-if="!peers || !peerRows.length" class="empty">暂无估值同行数据。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>代码</th><th>名称</th><th>PEG</th><th>增速</th><th>空间</th><th>分层</th></tr></thead><tbody><tr v-for="row in peerRows" :key="row.code"><td>{{ row.code }}</td><td>{{ row.name || '—' }}</td><td>{{ numberOrDash(row.peg_next_year) }}</td><td>{{ numberOrDash(row.growth_next_year_pct) }}%</td><td>{{ numberOrDash(row.upside_pct) }}%</td><td>{{ row.valuation_bucket || '—' }}</td></tr></tbody></table></div></div></section></template>

      <template v-else-if="tab === 'flow'"><section class="panel"><div class="panel-head"><div><h2>资金流向</h2><p>单位和分级字段沿用行情服务返回；正负号只反映净流入方向。</p></div></div><div class="panel-body"><div v-if="!list(capitalFlow, 'flow').length" class="empty">暂无资金流数据。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>主力净流入</th><th>小单</th><th>中单</th><th>大单</th><th>超大单</th></tr></thead><tbody><tr v-for="row in list(capitalFlow, 'flow').slice().reverse()" :key="row.date"><td>{{ row.date }}</td><td :class="actionClass(row.main_net)">{{ signed(row.main_net) }}</td><td :class="actionClass(row.small_net)">{{ signed(row.small_net) }}</td><td :class="actionClass(row.medium_net)">{{ signed(row.medium_net) }}</td><td :class="actionClass(row.big_net)">{{ signed(row.big_net) }}</td><td :class="actionClass(row.super_net)">{{ signed(row.super_net) }}</td></tr></tbody></table></div></div></section></template>

      <template v-else-if="tab === 'book'"><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>卖盘五档</h2><p>0 价位表示 provider 没有返回有效盘口。</p></div></div><div class="panel-body"><div class="book-list"><div v-for="(row, index) in list(orderBook, 'asks').slice().reverse()" :key="`ask-${index}`" class="book-row"><span>卖{{ 5 - index }}</span><strong>{{ numberOrDash(row.price) }}</strong><span>{{ numberOrDash(row.volume, 0) }}</span></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>买盘五档</h2><p>盘口只用于研究展示，不会触发订单。</p></div></div><div class="panel-body"><div class="book-list"><div v-for="(row, index) in list(orderBook, 'bids')" :key="`bid-${index}`" class="book-row"><span>买{{ index + 1 }}</span><strong>{{ numberOrDash(row.price) }}</strong><span>{{ numberOrDash(row.volume, 0) }}</span></div></div></div></section></section></template>

      <template v-else-if="tab === 'fundamentals'"><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>财务与估值</h2><p>空值代表当前覆盖不足，不代表 0。</p></div></div><div class="panel-body"><div class="metric-grid"><div v-for="row in fundamentalRows" :key="row[0]" class="metric-cell"><span>{{ row[0] }}</span><strong>{{ numberOrDash(row[1]) }}</strong></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>季度利润趋势</h2><p>近几个报告期，单位由后端转换为亿元。</p></div></div><div class="panel-body"><div v-if="!list(profitTrend, 'trends').length" class="empty">暂无利润趋势。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>报告期</th><th>营业收入</th><th>净利润</th></tr></thead><tbody><tr v-for="row in list(profitTrend, 'trends').slice().reverse()" :key="row.date"><td>{{ row.date }}</td><td>{{ numberOrDash(row.revenue) }}</td><td>{{ numberOrDash(row.net_profit) }}</td></tr></tbody></table></div></div></section></div><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>十大流通股东</h2></div></div><div class="panel-body"><div v-if="!list(shareholders, 'shareholders').length" class="empty">暂无股东记录。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>截止日期</th><th>股东</th><th>持股(万股)</th><th>占比</th></tr></thead><tbody><tr v-for="row in list(shareholders, 'shareholders')" :key="`${row.date}-${row.name}`"><td>{{ row.date }}</td><td>{{ row.name }}</td><td>{{ numberOrDash(row.shares) }}</td><td>{{ numberOrDash(row.ratio) }}%</td></tr></tbody></table></div></div></section><section class="panel"><div class="panel-head"><div><h2>最近公告</h2></div></div><div class="panel-body"><div v-if="!list(announcements, 'announcements').length" class="empty">暂无公告。</div><div v-else class="check-list"><a v-for="row in list(announcements, 'announcements')" :key="`${row.date}-${row.title}`" class="check-row link-row" :href="row.url" target="_blank" rel="noopener noreferrer"><div class="check-copy"><strong>{{ row.title }}</strong><span>{{ row.date }} · {{ row.type || '公告' }}</span></div><ExternalLink :size="15" /></a></div></div></section></div></template>

      <template v-else-if="tab === 'compare'"><section class="panel"><div class="panel-head"><div><h2>同行业比较</h2><p>{{ industry?.industry || '行业' }} · 同行指标来自当前 provider。</p></div><button class="button" type="button" :disabled="tabLoading" @click="loadTab('compare')"><RefreshCw :size="15" />刷新</button></div><div class="panel-body"><div v-if="!list(industry, 'stocks').length" class="empty">暂无同行业成分数据。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>代码</th><th>名称</th><th>价格</th><th>涨跌幅</th><th>PE</th><th>PB</th><th>ROE</th></tr></thead><tbody><tr v-for="row in list(industry, 'stocks')" :key="row.code"><td>{{ row.code }}</td><td>{{ row.name }}</td><td>{{ numberOrDash(row.price) }}</td><td :class="actionClass(row.change_pct)">{{ signed(row.change_pct, '%') }}</td><td>{{ numberOrDash(row.pe_ratio) }}</td><td>{{ numberOrDash(row.pb_ratio) }}</td><td>{{ numberOrDash(row.roe) }}</td></tr></tbody></table></div><div class="field-grid compare-form"><div class="field"><label for="compare-codes">多股比较代码</label><input id="compare-codes" v-model="compareCodes" class="field-input" placeholder="用逗号分隔，最多 5 只" /></div><button class="button primary compare-button" type="button" @click="loadTab('compare')">更新归一化比较</button></div><div v-if="compareSeries.length" class="compare-list"><div v-for="[code, series] in compareSeries" :key="code" class="compare-row"><strong>{{ code }} <small>{{ series.name || '' }}</small></strong><span>{{ series.data?.[0]?.value ?? '—' }} → {{ series.data?.[series.data.length - 1]?.value ?? '—' }}</span><span>{{ series.data?.length || 0 }} 点</span></div></div></div></section></template>

      <template v-else-if="tab === 'drawings'"><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>保存画线</h2><p>使用真实日期和价格保存到当前标的；这不是交易指令。</p></div><Bookmark :size="19" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="drawing-name">名称</label><input id="drawing-name" v-model="drawingName" class="field-input" /></div><div class="field"><label for="drawing-date">日期</label><input id="drawing-date" v-model="drawingDate" class="field-input" type="date" /></div><div class="field"><label for="drawing-price">价格</label><input id="drawing-price" v-model="drawingPrice" class="field-input" inputmode="decimal" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="tabLoading" @click="saveDrawing"><Save :size="15" />保存画线</button><button class="button danger" type="button" :disabled="tabLoading || !drawings.length" @click="clearDrawings"><Trash2 :size="15" />清空画线</button></div></div></section><section class="panel"><div class="panel-head"><div><h2>已保存画线</h2><p>按标的隔离，删除只影响画线记录。</p></div></div><div class="panel-body"><div v-if="!drawings.length" class="empty">暂无画线。</div><div v-else class="check-list"><div v-for="row in drawings" :key="row.id" class="check-row"><div class="check-copy"><strong>{{ row.overlay_name || row.name || '未命名画线' }}</strong><span>{{ JSON.stringify(row.points || []) }}</span></div><button class="icon-button" type="button" title="删除画线" aria-label="删除画线" @click="removeDrawing(row.id)"><Trash2 :size="15" /></button></div></div></div></section></section></template>
    </template>
  </section>
</template>
