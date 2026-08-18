<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Activity, BarChart3, CircleAlert, Clock3, Database, ExternalLink, Newspaper, RefreshCw, Search, Sparkles } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import AsyncState from '../components/base/AsyncState.vue'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import DetailDrawer from '../components/base/DetailDrawer.vue'
import { useAppStore } from '../stores/app'

type Row = Record<string, any>

const breadth = ref<Row | null>(null)
const providerSnapshot = ref<Row | null>(null)
const sectors = ref<Row[]>([])
const heatmap = ref<Row[]>([])
const hotspots = ref<Row[]>([])
const news = ref<Row[]>([])
const signals = ref<Row[]>([])
const selectedHeatmapItem = ref<Row | null>(null)

type IntelState = 'loading' | 'available' | 'partial' | 'unavailable'
type SectionState = { state: IntelState; source: string; freshness: string; generatedAt: string; reason: string; stale: boolean }
const sectionStates = ref<Record<string, SectionState>>({})
const sectionNames: Record<string, string> = { breadth: '市场广度', sectors: '板块', heatmap: '热力图', hotspots: '热点', news: '新闻', signals: '信号' }
const query = ref('')
const queryResult = ref<Row | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const queryLoading = ref(false)
const message = ref('')
const app = useAppStore()
const selectedMarket = computed(() => String(app.market || 'CN').toUpperCase())
const marketNames: Record<string, string> = { CN: 'A 股', HK: '港股', US: '美股', JP: '日股', KR: '韩股', TW: '台股' }
const selectedMarketLabel = computed(() => marketNames[selectedMarket.value] || selectedMarket.value)
const iwencaiSupported = computed(() => selectedMarket.value === 'CN')
const snapshotAvailable = computed(() => Boolean(providerSnapshot.value?.available || providerSnapshot.value?.success))
const snapshotSource = computed(() => String(providerSnapshot.value?.source || providerSnapshot.value?.provider || '—'))
const snapshotCoverage = computed(() => providerSnapshot.value?.coverage_pct == null ? '—' : `${providerSnapshot.value.coverage_pct}%`)
const providerIndex = computed<Row | null>(() => {
  const index = providerSnapshot.value?.index
  if (!index || typeof index !== 'object' || Array.isArray(index)) return null
  return (index as Row).index && typeof (index as Row).index === 'object' ? (index as Row).index as Row : index as Row
})

function snapshotPart(key: string): Row | null {
  const part = providerSnapshot.value?.[key]
  return part && typeof part === 'object' && !Array.isArray(part) ? part as Row : null
}

function snapshotItems(key: string, keys: string[]) {
  const part = providerSnapshot.value?.[key]
  return list(part, keys)
}

function researchTag(key: string) {
  const state = sectionStates.value[key]?.state
  return state === 'available' ? '代理覆盖' : snapshotAvailable.value ? '手动研究' : '未接入'
}

function responseState(payload: Row | null, rejected: boolean, hasItems: boolean): SectionState {
  const stale = Boolean(payload?.stale)
  const source = String(payload?.source || payload?.provider || '未返回')
  const generatedAt = String(payload?.generated_at || payload?.as_of || payload?.updated_at || '—')
  const reason = String(payload?.error || payload?.stale_reason || payload?.reason || '')
  if (rejected) return { state: 'unavailable', source, freshness: '请求失败', generatedAt, reason: reason || '请求失败', stale }
  if (!payload || payload.success === false || payload.data_state === 'not_integrated') return { state: 'unavailable', source, freshness: '未接入', generatedAt, reason: reason || '该市场暂无市场级自动数据', stale }
  if (payload.data_state === 'manual_research' && !hasItems) return { state: 'partial', source, freshness: stale ? '可能过期' : '代理快照', generatedAt, reason: reason || 'provider 仅返回手动研究代理覆盖，尚无该区块的市场级数据', stale }
  if (payload.partial === true || Array.isArray(payload.partial_errors) && payload.partial_errors.length > 0) return { state: 'partial', source, freshness: stale ? '可能过期' : '部分可用', generatedAt, reason: reason || String(payload.partial_errors?.join?.('；') || ''), stale }
  return { state: hasItems || Object.keys(payload).length > 0 ? 'available' : 'partial', source, freshness: stale ? '可能过期' : '已读取', generatedAt, reason, stale }
}

function stateLabel(key: string) {
  const state = sectionStates.value[key]?.state
  return state === 'loading' ? '加载中' : state === 'available' ? '已读取' : state === 'partial' ? '部分可用' : '不可用'
}

function stateClass(key: string) {
  return sectionStates.value[key]?.state || 'unavailable'
}

function stateDetail(key: string) {
  const item = sectionStates.value[key]
  if (!item) return '等待'
  return `${item.source} · ${item.freshness}${item.generatedAt !== '—' ? ` · ${item.generatedAt}` : ''}`
}

function list(payload: any, keys: string[]) {
  if (Array.isArray(payload)) return payload
  for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key]
  return []
}

function number(value: unknown, digits = 0) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function percent(value: unknown) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return `${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })}%`
}

function changeClass(value: unknown) {
  const numberValue = Number(value)
  return numberValue > 0 ? 'good' : numberValue < 0 ? 'bad' : 'muted'
}

function heatColor(value: unknown) {
  const numberValue = Math.max(-5, Math.min(5, Number(value) || 0))
  const intensity = Math.abs(numberValue) / 5
  if (numberValue > 0) return `color-mix(in srgb, var(--up) ${Math.round(18 + intensity * 42)}%, var(--surface))`
  if (numberValue < 0) return `color-mix(in srgb, var(--down) ${Math.round(18 + intensity * 42)}%, var(--surface))`
  return 'var(--surface-muted)'
}

const breadthUnavailable = computed(() => !breadth.value || breadth.value.success === false || breadth.value.data_state === 'not_integrated')
const breadthTotal = computed(() => breadthUnavailable.value ? (providerSnapshot.value?.universe?.total ?? null) : Number(breadth.value?.total_stocks ?? breadth.value?.total ?? providerSnapshot.value?.universe?.total ?? 0))
const breadthLabel = computed(() => {
  if (breadthUnavailable.value) return '等待数据'
  const up = Number(breadth.value?.up_count ?? 0)
  const down = Number(breadth.value?.down_count ?? 0)
  if (up > down * 1.2) return '偏强'
  if (down > up * 1.2) return '偏弱'
  return '分化'
})

let loadSequence = 0
let loadController: AbortController | null = null
let querySequence = 0
let queryController: AbortController | null = null

async function load() {
  const sequence = ++loadSequence
  loadController?.abort()
  loadController = new AbortController()
  loading.value = true
  refreshing.value = providerSnapshot.value !== null || sectors.value.length > 0 || signals.value.length > 0
  message.value = ''
  // 保留已读取内容，刷新期间由 RefreshIndicator 告知状态。
  sectionStates.value = Object.fromEntries(Object.keys(sectionNames).map((key) => [key, { ...(sectionStates.value[key] || {}), state: 'loading', source: sectionStates.value[key]?.source || '读取中', freshness: '加载中', generatedAt: sectionStates.value[key]?.generatedAt || '—', reason: '', stale: Boolean(sectionStates.value[key]?.stale) }])) as Record<string, SectionState>
  const market = selectedMarket.value
  const results = await Promise.allSettled([
    api.marketBreadth(market, loadController.signal), api.marketSectors(true, market, loadController.signal), api.marketHeatmap(true, market, loadController.signal), api.marketHotspot(market, loadController.signal), api.marketNews(market, loadController.signal), api.signalTop(20, market, loadController.signal), api.marketSnapshot(market, loadController.signal),
  ])
  if (sequence !== loadSequence || market !== selectedMarket.value) return
  const value = <T>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
  const nextBreadth = value<Row>(0)
  const sectorResponse = value<Row>(1)
  const heatmapResponse = value<Row>(2)
  const hotspotResponse = value<Row>(3)
  const newsResponse = value<Row>(4)
  const signalResponse = value<Row>(5)
  const snapshotResponse = value<Row>(6)
  if (snapshotResponse) providerSnapshot.value = snapshotResponse
  const providerBreadth = snapshotPart('breadth')
  const providerSectors = snapshotItems('sectors', ['sectors', 'items'])
  const providerHeatmap = snapshotItems('heatmap', ['heatmap', 'sectors', 'items'])
  const providerHotspots = snapshotItems('hotspots', ['hotspots', 'concepts', 'items'])
  const providerNews = snapshotItems('news', ['news', 'items', 'articles'])
  const providerSignals = snapshotItems('signals', ['signals', 'items', 'data'])
  if (nextBreadth && nextBreadth.success !== false && nextBreadth.data_state !== 'not_integrated') breadth.value = nextBreadth
  if (sectorResponse) sectors.value = list(sectorResponse, ['sectors', 'items'])
  if (heatmapResponse) heatmap.value = list(heatmapResponse, ['sectors', 'items'])
  if (hotspotResponse) hotspots.value = list(hotspotResponse, ['hot_concepts', 'hot_industries', 'concepts', 'industries', 'hotspots', 'items']).slice(0, 12)
  if (newsResponse) news.value = list(newsResponse, ['news', 'items', 'articles']).slice(0, 16)
  if (signalResponse) signals.value = list(signalResponse, ['signals', 'predictions', 'items', 'data']).slice(0, 20)
  if (providerBreadth?.available && (!nextBreadth || nextBreadth.success === false || nextBreadth.data_state === 'not_integrated')) breadth.value = { ...providerBreadth, ...(providerSnapshot.value || {}) }
  if (providerSectors.length && (!sectorResponse || sectorResponse.success === false || sectorResponse.data_state === 'not_integrated')) sectors.value = providerSectors
  if (providerHeatmap.length && (!heatmapResponse || heatmapResponse.success === false || heatmapResponse.data_state === 'not_integrated')) heatmap.value = providerHeatmap
  if (providerSectors.length && !heatmap.value.length && (!heatmapResponse || heatmapResponse.success === false || heatmapResponse.data_state === 'not_integrated')) heatmap.value = providerSectors
  if (providerHotspots.length && (!hotspotResponse || hotspotResponse.success === false || hotspotResponse.data_state === 'not_integrated')) hotspots.value = providerHotspots.slice(0, 12)
  if (providerNews.length && (!newsResponse || newsResponse.success === false || newsResponse.data_state === 'not_integrated')) news.value = providerNews.slice(0, 16)
  if (providerSignals.length && (!signalResponse || signalResponse.success === false || signalResponse.data_state === 'not_integrated')) signals.value = providerSignals.slice(0, 20)
  const payloads: Array<[string, Row | null, boolean, boolean]> = [
    ['breadth', breadth.value || snapshotResponse, results[0].status === 'rejected' && !snapshotAvailable.value, Boolean(breadth.value) || snapshotAvailable.value],
    ['sectors', sectorResponse?.success === false ? (providerSectors.length ? snapshotResponse : sectorResponse) : sectorResponse, results[1].status === 'rejected' && !snapshotAvailable.value, sectors.value.length > 0],
    ['heatmap', heatmapResponse?.success === false ? ((providerHeatmap.length || providerSectors.length) ? snapshotResponse : heatmapResponse) : heatmapResponse, results[2].status === 'rejected' && !snapshotAvailable.value, heatmap.value.length > 0],
    ['hotspots', hotspotResponse?.success === false ? (providerHotspots.length ? snapshotResponse : hotspotResponse) : hotspotResponse, results[3].status === 'rejected' && !snapshotAvailable.value, hotspots.value.length > 0],
    ['news', newsResponse?.success === false ? (providerNews.length ? snapshotResponse : newsResponse) : newsResponse, results[4].status === 'rejected' && !snapshotAvailable.value, news.value.length > 0],
    ['signals', signalResponse?.success === false ? (providerSignals.length ? snapshotResponse : signalResponse) : signalResponse, results[5].status === 'rejected' && !snapshotAvailable.value, signals.value.length > 0],
  ]
  sectionStates.value = Object.fromEntries(payloads.map(([key, payload, rejected, hasItems]) => [key, responseState(payload, rejected, hasItems)]))
  const notices = payloads.filter(([, payload, rejected]) => rejected || payload?.success === false || payload?.data_state === 'not_integrated')
  if (notices.length === payloads.length) message.value = `${selectedMarketLabel.value} 当前保留手动标的研究；市场级数据源尚未具备自动接入资格。`
  else if (results.every((item) => item.status === 'rejected')) message.value = '情报数据暂不可用；页面保留空状态，不用默认值伪造市场判断。'
  else if (notices.length || payloads.some(([, payload]) => payload?.partial === true)) message.value = '部分情报源暂不可用；每个区块显示自己的来源、时效和状态。'
  if (sequence === loadSequence) {
    loading.value = false
    refreshing.value = false
  }
}

async function runIwencai() {
  if (!iwencaiSupported.value) {
    queryResult.value = null
    message.value = '问财仅覆盖 A 股；当前市场请进入手动标的研究。'
    return
  }
  if (!query.value.trim()) return
  const sequence = ++querySequence
  queryController?.abort()
  queryController = new AbortController()
  queryLoading.value = true
  message.value = ''
  try {
    const result = await api.iwencai(query.value.trim(), selectedMarket.value, queryController.signal)
    if (sequence === querySequence) queryResult.value = result
  } catch (error) {
    if (sequence === querySequence && !(error instanceof DOMException && error.name === 'AbortError')) message.value = error instanceof Error ? error.message : '问财查询失败'
  } finally {
    if (sequence === querySequence) queryLoading.value = false
  }
}

function itemCode(item: Row) {
  return item.code || item.symbol || item.stock_code || ''
}

function openHeatmapItem(item: Row) {
  selectedHeatmapItem.value = item
}

onMounted(load)
watch(selectedMarket, () => {
  queryResult.value = null
  query.value = ''
  void load()
})
</script>

<template>
  <section>
    <div class="page-head"><div><span class="eyebrow">MARKET CONTEXT / {{ selectedMarket }}</span><h1>市场情报</h1><p>把市场广度、板块轮动、新闻和信号放在同一张研究桌上。每个区块都显示来源、覆盖和是否可能过期。</p></div><div class="head-actions"><RefreshIndicator :state="refreshing ? 'refreshing' : message && !signals.length ? 'stale' : 'live'" :label="refreshing ? '保留内容，正在刷新' : '市场上下文已读取'" /><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新情报</button></div></div>
    <AsyncState v-if="!loading && !refreshing && !signals.length && !sectors.length && !heatmap.length" state="empty" title="当前市场没有可展示的情报结果" message="页面没有使用默认数据；可以切换市场或稍后重试。" @retry="load" />
    <div v-if="selectedMarket !== 'CN'" class="market-boundary" role="status"><Database :size="16" /><span><strong>{{ selectedMarketLabel }}</strong> <template v-if="snapshotAvailable">已读取 provider 代理快照（{{ snapshotSource }}）；当前覆盖 {{ snapshotCoverage }}，仅用于手动研究，未覆盖的区块保持部分可用或未接入状态。</template><template v-else>当前保留 Yahoo 手动标的研究；市场级 provider 快照尚不可用，不会回落到 A 股数据。</template></span><RouterLink class="button ghost compact-button" :to="`/app/research/${selectedMarket}/${({ HK: '00700', US: 'AAPL', JP: '7203', KR: '005930', TW: '2330' } as Record<string, string>)[selectedMarket] || '600519'}`">打开手动研究</RouterLink></div>
    <div v-if="message" class="error-box" role="status"><CircleAlert :size="16" />{{ message }}</div>

    <div class="summary-strip intelligence-summary"><div class="summary-item"><span>市场指数</span><strong>{{ providerIndex?.name || providerIndex?.symbol || '—' }}</strong><small>{{ number(providerIndex?.price, 2) }} · {{ percent(providerIndex?.change_pct) }}</small></div><div class="summary-item"><span>市场状态</span><strong>{{ breadthLabel }}</strong><small>基于 {{ breadthTotal == null ? '—' : number(breadthTotal) }} 个覆盖标的</small></div><div class="summary-item"><span>上涨家数</span><strong class="good">{{ number(breadth?.up_count) }}</strong><small>涨停 {{ number(breadth?.limit_up) }}</small></div><div class="summary-item"><span>下跌家数</span><strong class="bad">{{ number(breadth?.down_count) }}</strong><small>跌停 {{ number(breadth?.limit_down) }}</small></div><div class="summary-item"><span>信号候选</span><strong>{{ signals.length || '—' }}</strong><small>当前返回范围，不代表已验证</small></div></div>

    <div class="section-grid two intelligence-top-grid">
      <section class="panel"><div class="panel-head"><div><h2>市场广度</h2><p>本地覆盖池的涨跌统计；不把不可用数据替换成 0。</p></div><div class="section-status-wrap"><div class="section-status" :class="stateClass('breadth')" :title="stateDetail('breadth')">{{ stateLabel('breadth') }}</div><span class="research-tag" :class="researchTag('breadth') === '代理覆盖' ? 'proxy' : researchTag('breadth') === '手动研究' ? 'manual' : 'unavailable'">{{ researchTag('breadth') }}</span></div><Activity :size="18" class="faint" /></div><div class="panel-body"><div class="breadth-bars"><div><span>上涨</span><i :style="{ width: `${breadthTotal ? Math.min(100, Number(breadth?.up_count || 0) / Math.max(1, breadthTotal) * 100) : 0}%` }" class="bar-up" /><strong>{{ number(breadth?.up_count) }}</strong></div><div><span>下跌</span><i :style="{ width: `${breadthTotal ? Math.min(100, Number(breadth?.down_count || 0) / Math.max(1, breadthTotal) * 100) : 0}%` }" class="bar-down" /><strong>{{ number(breadth?.down_count) }}</strong></div><div><span>平盘</span><i :style="{ width: `${breadthTotal ? Math.min(100, Number(breadth?.flat_count || 0) / Math.max(1, breadthTotal) * 100) : 0}%` }" class="bar-flat" /><strong>{{ number(breadth?.flat_count) }}</strong></div></div><div class="data-source" style="margin-top:16px"><span><Database :size="14" />{{ breadth?.source || '—' }}</span><span><Clock3 :size="14" />{{ breadth?.generated_at || '—' }}</span><span class="tag" :class="breadth?.stale ? 'warn' : breadth ? 'good' : 'warn'">{{ breadth?.stale ? '可能过期' : breadth ? (breadth.success === false ? '未接入' : '已读取') : '等待' }}</span></div></div></section>
      <section v-if="iwencaiSupported" class="panel"><div class="panel-head"><div><h2>问财检索</h2><p>自然语言结果是研究候选，需回到单股研究和验证工作流。</p></div><Search :size="18" class="faint" /></div><div class="panel-body"><div class="inline-search"><input v-model="query" aria-label="问财自然语言查询" placeholder="例如：PE 低于 20 且 ROE 大于 15%" @keydown.enter.prevent="runIwencai" /><button class="button primary" type="button" :disabled="queryLoading || !query.trim()" @click="runIwencai"><Search :size="15" />{{ queryLoading ? '查询中' : '查询' }}</button></div><div v-if="!queryResult" class="empty compact-empty">输入条件开始查询。</div><pre v-else class="result-code compact-result">{{ JSON.stringify(queryResult, null, 2) }}</pre></div></section>
      <section v-else class="panel"><div class="panel-head"><div><h2>跨市场筛选</h2><p>该市场没有问财数据源；保持来源边界，不把 A 股候选混入当前研究。</p></div><Database :size="18" class="faint" /></div><div class="panel-body"><div class="empty manual-filter-state" role="status"><strong>{{ selectedMarketLabel }} 暂无市场级筛选 provider</strong><span>你仍可通过上方入口打开 Yahoo 手动标的研究；结果不会进入确定性决策或自动推送。</span><RouterLink class="button ghost compact-button" :to="`/app/research/${selectedMarket}/${({ HK: '00700', US: 'AAPL', JP: '7203', KR: '005930', TW: '2330' } as Record<string, string>)[selectedMarket] || '600519'}`">打开手动研究</RouterLink></div></div></section>
    </div>

    <div class="section-grid two intelligence-main-grid">
      <section class="panel"><div class="panel-head"><div><h2>板块热力与轮动</h2><p>色块同时显示涨跌数值；来源不可用时不会伪造排名。</p></div><div class="section-status-wrap"><div class="section-status" :class="stateClass('heatmap')" :title="stateDetail('heatmap')">{{ stateLabel('heatmap') }}</div><span class="research-tag" :class="researchTag('heatmap') === '代理覆盖' ? 'proxy' : researchTag('heatmap') === '手动研究' ? 'manual' : 'unavailable'">{{ researchTag('heatmap') }}</span></div><BarChart3 :size="18" class="faint" /></div><div class="panel-body"><div v-if="!heatmap.length && !sectors.length" class="empty">{{ selectedMarket === 'CN' ? '暂无板块数据。' : `${selectedMarketLabel} 尚未接入板块 provider。` }}</div><div v-else class="heatmap-grid"><button v-for="item in heatmap.slice(0, 30)" :key="item.code || item.name" class="heat-cell" type="button" :style="{ background: heatColor(item.change_pct) }" @click="openHeatmapItem(item)"><strong>{{ item.name || '—' }}</strong><span :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</span><small>涨 {{ number(item.up_count) }} · 跌 {{ number(item.down_count) }}</small></button></div><div v-if="sectors.length" class="table-scroll" style="margin-top:18px"><table class="decision-table"><thead><tr><th>板块</th><th>涨跌</th><th>涨/跌</th><th>领涨</th></tr></thead><tbody><tr v-for="item in sectors.slice(0, 12)" :key="`sector-${item.code || item.name}`"><td><strong>{{ item.name || '—' }}</strong></td><td :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</td><td>{{ number(item.up_count) }} / {{ number(item.down_count) }}</td><td>{{ item.leader || '—' }}</td></tr></tbody></table></div></div></section>
      <div class="stack-lg">
        <section class="panel"><div class="panel-head"><div><h2>热点归因</h2><p>热点是研究线索，不是确定性动作。</p></div><div class="section-status-wrap"><div class="section-status" :class="stateClass('hotspots')" :title="stateDetail('hotspots')">{{ stateLabel('hotspots') }}</div><span class="research-tag" :class="researchTag('hotspots') === '代理覆盖' ? 'proxy' : researchTag('hotspots') === '手动研究' ? 'manual' : 'unavailable'">{{ researchTag('hotspots') }}</span></div><Sparkles :size="18" class="faint" /></div><div class="panel-body"><div v-if="!hotspots.length" class="empty">暂无可验证热点。</div><div v-else class="intel-list"><div v-for="(item, index) in hotspots" :key="String(item.id || item.name || index)" class="intel-list-row"><span class="rank-number">{{ index + 1 }}</span><div><strong>{{ item.name || item.title || item.concept || '热点' }}</strong><small>{{ item.reason || item.description || item.leader || '—' }}</small></div><span class="tag" :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</span></div></div></div></section>
        <section class="panel"><div class="panel-head"><div><h2>市场新闻</h2><p>新闻用于情报核验，查看原文前保持来源可见。</p></div><div class="section-status-wrap"><div class="section-status" :class="stateClass('news')" :title="stateDetail('news')">{{ stateLabel('news') }}</div><span class="research-tag" :class="researchTag('news') === '代理覆盖' ? 'proxy' : researchTag('news') === '手动研究' ? 'manual' : 'unavailable'">{{ researchTag('news') }}</span></div><Newspaper :size="18" class="faint" /></div><div class="panel-body"><div v-if="!news.length" class="empty">暂无市场新闻。</div><div v-else class="news-list"><article v-for="(item, index) in news" :key="String(item.id || item.url || index)" class="news-row"><div><strong>{{ item.title || item.name || '未命名新闻' }}</strong><small>{{ item.source || item.publisher || '来源未返回' }} · {{ item.published_at || item.time || item.created_at || '—' }}</small></div><a v-if="item.url || item.link" :href="item.url || item.link" target="_blank" rel="noopener noreferrer" class="icon-button compact-icon" title="打开原文" aria-label="打开新闻原文"><ExternalLink :size="14" /></a></article></div></div></section>
      </div>
    </div>

    <DetailDrawer :open="Boolean(selectedHeatmapItem)" :title="selectedHeatmapItem?.name || '板块详情'" eyebrow="MARKET MAP / SELECTED" @close="selectedHeatmapItem = null"><div v-if="selectedHeatmapItem" class="heatmap-detail"><div class="detail-metric"><span>涨跌幅</span><strong :class="changeClass(selectedHeatmapItem.change_pct)">{{ percent(selectedHeatmapItem.change_pct) }}</strong></div><div class="detail-metric"><span>上涨 / 下跌</span><strong>{{ number(selectedHeatmapItem.up_count) }} / {{ number(selectedHeatmapItem.down_count) }}</strong></div><div class="detail-metric"><span>领涨标的</span><strong>{{ selectedHeatmapItem.leader || selectedHeatmapItem.leader_code || '—' }}</strong></div><p class="muted">热力图是市场上下文，不是自动交易指令。打开领涨标的研究，继续核验证据和数据质量。</p><RouterLink v-if="selectedHeatmapItem.leader_code" class="button primary" :to="`/app/research/${selectedHeatmapItem.market || selectedMarket}/${encodeURIComponent(String(selectedHeatmapItem.leader_code))}`">打开领涨标的研究</RouterLink></div></DetailDrawer>

    <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>AI 信号池</h2><p>候选信号保留质量和验证语义；未验证信号不会自动进入决策或推送资格。</p></div><div class="section-status-wrap"><div class="section-status" :class="stateClass('signals')" :title="stateDetail('signals')">{{ stateLabel('signals') }}</div><span class="research-tag" :class="researchTag('signals') === '代理覆盖' ? 'proxy' : researchTag('signals') === '手动研究' ? 'manual' : 'unavailable'">{{ researchTag('signals') }}</span></div><Sparkles :size="18" class="faint" /></div><div class="panel-body"><div v-if="!signals.length" class="empty">{{ selectedMarket === 'CN' ? '暂无信号候选。' : `${selectedMarketLabel} 尚未接入确定性信号 provider。` }}</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>标的</th><th>分数</th><th>验证</th><th>来源</th><th>研究</th></tr></thead><tbody><tr v-for="(item, index) in signals" :key="String(item.id || itemCode(item) || index)"><td><strong>{{ itemCode(item) || '—' }}</strong><small>{{ item.name || '—' }}</small></td><td>{{ number(item.score ?? item.signal_score, 4) }}</td><td><span class="tag" :class="String(item.validation_status || item.confidence || '').includes('valid') ? 'good' : 'warn'">{{ item.validation_status || item.confidence || '未验证' }}</span></td><td>{{ item.source || item.provider || '—' }}</td><td><RouterLink class="button ghost compact-button" :to="`/app/research/${item.market || selectedMarket}/${encodeURIComponent(String(itemCode(item) || '600519'))}`">打开研究</RouterLink></td></tr></tbody></table></div></div></section>
  </section>
</template>

<style scoped>
.eyebrow { display: block; margin-bottom: 8px; color: var(--color-accent-strong); font-family: var(--font-family-mono); font-size: 11px; letter-spacing: .08em; }

.market-boundary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 18px;
  padding: 11px 13px;
  border: 1px solid color-mix(in srgb, var(--warn) 34%, var(--line));
  border-radius: 8px;
  background: color-mix(in srgb, var(--warn) 8%, var(--surface));
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.5;
}

.market-boundary > svg { flex: 0 0 auto; color: var(--warn); }
.market-boundary > span { flex: 1 1 auto; min-width: 0; }
.market-boundary strong { color: var(--ink); }
.manual-filter-state { display: grid; gap: 8px; justify-items: start; text-align: left; }
.manual-filter-state strong { color: var(--ink); }
.manual-filter-state span { color: var(--ink-soft); }
.section-status { font-size: 11px; padding: 3px 7px; border-radius: 999px; white-space: nowrap; }
.section-status.available { color: var(--up); background: color-mix(in srgb, var(--up) 12%, var(--surface)); }
.section-status.partial, .section-status.loading { color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, var(--surface)); }
.section-status.unavailable { color: var(--down); background: color-mix(in srgb, var(--down) 10%, var(--surface)); }

.section-status-wrap { display: inline-flex; align-items: center; gap: 6px; }
.research-tag { font-size: 10px; padding: 3px 6px; border-radius: 999px; white-space: nowrap; border: 1px solid var(--line); color: var(--ink-soft); background: var(--surface-muted); }
.research-tag.proxy { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 35%, var(--line)); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
.research-tag.manual { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, var(--line)); background: color-mix(in srgb, var(--warn) 10%, var(--surface)); }
.research-tag.unavailable { color: var(--down); border-color: color-mix(in srgb, var(--down) 30%, var(--line)); background: color-mix(in srgb, var(--down) 8%, var(--surface)); }

@media (max-width: 640px) {
  .market-boundary { align-items: flex-start; flex-wrap: wrap; }
  .market-boundary .button { width: 100%; justify-content: center; }
}
</style>
