<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AsyncState from '../components/base/AsyncState.vue'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import BaseTabs from '../components/base/BaseTabs.vue'
import type { Tab } from '../components/base/BaseTabs.vue'
import KLineChart from '../components/research/KLineChart.vue'
import TechnicalIndicators from '../components/research/TechnicalIndicators.vue'
import EvidenceChain from '../components/research/EvidenceChain.vue'
import DecisionCard from '../components/research/DecisionCard.vue'
import BacktestDraft from '../components/research/BacktestDraft.vue'
import DataQualityBadge from '../components/market/DataQualityBadge.vue'
import { getEvidence, getKLineData, getTechnicalIndicators, type SourceState } from '../api/research'
import type { Evidence, KLineBar, TechnicalIndicators as IndicatorData } from '../api/types'
import { useResearchContextStore } from '../stores/researchContext'
import { useWorkspaceQuery } from '../composables/useWorkspaceQuery'
import { useAppStore } from '../stores/app'
import type { MarketCode } from '../api/types'

const route = useRoute()
const contextStore = useResearchContextStore()
const { state: workspaceQuery, update: updateWorkspaceQuery } = useWorkspaceQuery()
const appStore = useAppStore()
const symbol = computed(() => String(route.params.symbol || '').trim())
const market = computed(() => String(route.params.market || 'CN').toUpperCase())
const requestKey = computed(() => `${market.value}:${symbol.value}`)
const bars = ref<KLineBar[]>([])
const indicators = ref<IndicatorData>({})
const evidence = ref<Evidence[]>([])
const sources = ref<SourceState[]>([])
const evidenceSnapshotId = ref('')
const klineState = ref<'loading' | 'available' | 'partial' | 'unavailable'>('loading')
const indicatorState = ref<'loading' | 'available' | 'partial' | 'unavailable'>('loading')
const evidenceState = ref<'loading' | 'available' | 'partial' | 'unavailable'>('loading')
const klineSource = ref('')
const klineAsOf = ref('')
const klineError = ref('')
const klineCoverage = ref<number | undefined>(undefined)
const indicatorError = ref('')
const evidenceError = ref('')
const loading = ref(false)
let controller: AbortController | null = null
let activeKey = ''

const tabs: Tab[] = [
  { id: 'kline-tech', label: 'K线与技术' }, { id: 'evidence', label: '证据与决策' }, { id: 'backtest', label: '回测草案' },
]
const activeTab = ref('kline-tech')

watch(() => workspaceQuery.value.tab, (tab) => {
  if (tab && tabs.some((item) => item.id === tab)) activeTab.value = tab
}, { immediate: true })

watch(activeTab, (tab) => updateWorkspaceQuery({ tab }))

function isCurrent(key: string) { return key === activeKey && key === requestKey.value }
async function loadResearch() {
  const key = requestKey.value
  if (!symbol.value) return
  controller?.abort()
  controller = new AbortController()
  activeKey = key
  loading.value = true
  contextStore.setFreshness('delayed', klineSource.value || null)
  // 切换标的时保留旧内容，避免动态研究桌突然闪空；各模块用 loading 状态覆盖刷新过程。
  evidenceSnapshotId.value = ''
  klineState.value = 'loading'
  indicatorState.value = 'loading'
  evidenceState.value = 'loading'
  klineError.value = ''
  klineCoverage.value = undefined
  indicatorError.value = ''
  evidenceError.value = ''
  contextStore.setInstrument({ market: market.value, symbol: symbol.value })
  appStore.setMarket(market.value as MarketCode)

  const [klineResult, indicatorResult, evidenceResult] = await Promise.allSettled([
    getKLineData(market.value as any, symbol.value, 'daily', 120, controller.signal),
    getTechnicalIndicators(market.value as any, symbol.value, controller.signal),
    getEvidence(market.value as any, symbol.value, controller.signal),
  ])
  if (!isCurrent(key)) return
  if (klineResult.status === 'fulfilled') {
    bars.value = klineResult.value.bars
    klineSource.value = klineResult.value.source || 'stock_detail'
    klineAsOf.value = klineResult.value.asOf || bars.value.at(-1)?.date || ''
    klineError.value = klineResult.value.error || ''
    klineCoverage.value = klineResult.value.coveragePct
    klineState.value = bars.value.length ? (bars.value.length < 30 ? 'partial' : 'available') : 'unavailable'
  } else if (klineResult.reason?.name !== 'AbortError') {
    klineError.value = klineResult.reason instanceof Error ? klineResult.reason.message : 'K线数据加载失败'
    klineState.value = 'unavailable'
  }
  if (indicatorResult.status === 'fulfilled') {
    indicators.value = indicatorResult.value
    indicatorState.value = Object.keys(indicators.value).length ? 'available' : 'partial'
  } else if (indicatorResult.reason?.name !== 'AbortError') {
    indicatorError.value = indicatorResult.reason instanceof Error ? indicatorResult.reason.message : '技术指标加载失败'
    indicatorState.value = 'unavailable'
  }
  if (evidenceResult.status === 'fulfilled') {
    evidence.value = evidenceResult.value.evidence
    sources.value = evidenceResult.value.sources
    evidenceSnapshotId.value = evidenceResult.value.evidence_snapshot_id || ''
    evidenceState.value = evidence.value.length ? 'available' : sources.value.some((item) => item.status === 'available') ? 'partial' : 'unavailable'
    evidenceError.value = sources.value.filter((item) => item.error).map((item) => item.error).join('；')
  } else if (evidenceResult.reason?.name !== 'AbortError') {
    evidenceError.value = evidenceResult.reason instanceof Error ? evidenceResult.reason.message : '证据加载失败'
    evidenceState.value = 'unavailable'
  }
  loading.value = false
  const state = [klineState.value, indicatorState.value, evidenceState.value]
  contextStore.setFreshness(state.includes('available') ? 'live' : state.includes('partial') ? 'delayed' : 'unavailable', klineSource.value || null)
  contextStore.setResearchSnapshot({
    market: market.value,
    symbol: symbol.value,
    klineState: klineState.value,
    indicatorState: indicatorState.value,
    evidenceState: evidenceState.value,
    evidenceSnapshotId: evidenceSnapshotId.value,
  })
}

watch(requestKey, () => { void loadResearch() }, { immediate: true })
onMounted(() => contextStore.setInstrument({ market: market.value, symbol: symbol.value }))
onUnmounted(() => controller?.abort())
</script>

<template>
  <section class="research-view">
    <div class="research-breadcrumb"><RouterLink to="/app/decision">决策中心</RouterLink><span>/</span><strong>{{ market }} / {{ symbol }}</strong></div><div v-if="evidenceSnapshotId" class="research-evidence-meta">新闻与情绪 · 证据快照 {{ evidenceSnapshotId }}</div>
    <div class="research-header"><div><h1 class="research-title">单股研究</h1><p class="research-subtitle">先看事实，再看证据；当前页面不生成未经接口确认的交易结论。</p></div><div class="research-meta"><span class="meta-badge">{{ market }}</span><span class="meta-symbol">{{ symbol }}</span><DataQualityBadge :market="market" :symbol="symbol" :research-state="klineState" :research-source="klineSource" :research-as-of="klineAsOf" :research-error="klineError" :research-coverage="klineCoverage" /></div></div>
    <div class="research-actions"><div class="research-live-state"><RefreshIndicator :state="loading ? 'refreshing' : contextStore.context.freshness || 'unavailable'" :as-of="klineAsOf" /><span class="status-copy">{{ loading ? `保留上一次数据，正在更新 ${market} / ${symbol}` : '数据来源和时间显示在各模块内' }}</span></div><RouterLink class="button primary" :to="`/app/validation?market=${market}&symbol=${encodeURIComponent(symbol)}`">进入验证并继承当前股票</RouterLink></div>
    <AsyncState v-if="!loading && klineState === 'unavailable' && indicatorState === 'unavailable' && evidenceState === 'unavailable'" state="error" title="研究数据暂不可用" message="未用默认值填充当前页面；可以稍后重试。" @retry="loadResearch" />
    <div class="mobile-task-bar"><RouterLink class="button primary" :to="`/app/validation?market=${market}&symbol=${encodeURIComponent(symbol)}`">进入验证</RouterLink><RouterLink class="button ghost" to="/app/decision">回到决策</RouterLink></div>
    <BaseTabs v-model="activeTab" :tabs="tabs" size="md" class="research-tabs">
      <div v-if="activeTab === 'kline-tech'" class="tab-content"><div class="research-layout"><KLineChart :market="market" :symbol="symbol" :bars="bars" :state="klineState" :source="klineSource" :as-of="klineAsOf" :error="klineError" /><TechnicalIndicators :market="market" :symbol="symbol" :indicators="indicators" :state="indicatorState" :error="indicatorError" /></div></div>
      <div v-else-if="activeTab === 'evidence'" class="tab-content"><div class="evidence-layout"><EvidenceChain :market="market" :symbol="symbol" :evidence="evidence" :sources="sources" :state="evidenceState" /><DecisionCard :market="market" :symbol="symbol" :state="evidenceState" :error="evidenceError" /><span v-if="evidenceSnapshotId" class="research-evidence-meta">新闻与情绪 · 证据快照 {{ evidenceSnapshotId }}</span></div></div>
      <div v-else-if="activeTab === 'backtest'" class="tab-content"><BacktestDraft :market="market" :symbol="symbol" /></div>
    </BaseTabs>
  </section>
</template>

<style scoped>
.research-view { padding:var(--spacing-lg); max-width:1400px; margin:0 auto; }
.research-breadcrumb { display:flex; gap:var(--spacing-sm); color:var(--color-ink-soft); font-size:var(--font-size-sm); margin-bottom:var(--spacing-md); }
.research-breadcrumb a { color:var(--color-accent); text-decoration:none; }
.research-header { display:flex; justify-content:space-between; align-items:center; gap:var(--spacing-lg); margin-bottom:var(--spacing-md); padding-bottom:var(--spacing-lg); border-bottom:2px solid var(--color-line); }
.research-title { margin:0; font-size:var(--font-size-3xl); color:var(--color-ink); }
.research-subtitle { margin:var(--spacing-xs) 0 0; color:var(--color-ink-soft); }
.research-meta { display:flex; align-items:center; gap:var(--spacing-sm); }
.meta-badge { padding:var(--spacing-xs) var(--spacing-md); background:var(--color-accent-pale); color:var(--color-accent); border-radius:var(--radius-md); }
.meta-symbol { font:var(--font-size-xl) var(--font-family-mono); font-weight:var(--font-weight-bold); color:var(--color-ink); }
.research-actions { display:flex; align-items:center; justify-content:space-between; gap:var(--spacing-md); margin-bottom:var(--spacing-lg); }
.research-live-state { display:flex; align-items:center; gap:var(--spacing-sm); min-width:0; flex-wrap:wrap; }
.status-copy { color:var(--color-ink-soft); font-size:var(--font-size-sm); }
.tab-content { animation:fadeIn var(--duration-slow) var(--ease-smooth); }
@keyframes fadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
.research-layout,.evidence-layout { display:flex; flex-direction:column; gap:var(--spacing-lg); min-width:0; }
.backtest-layout { display:grid; grid-template-columns:minmax(0, 3fr) minmax(0, 2fr); gap:var(--spacing-lg); align-items:start; min-width:0; }
.backtest-layout > * { min-width:0; }
@media (max-width: 768px) { .research-view { padding:var(--spacing-md); } .research-header { flex-direction:column; align-items:flex-start; } .research-meta,.research-actions { width:100%; } .research-actions { flex-direction:column; align-items:stretch; } .backtest-layout { grid-template-columns:1fr; } .research-title { font-size:var(--font-size-2xl); } }
@media (max-width: 480px) { .research-view { padding:var(--spacing-sm); } .research-breadcrumb { flex-wrap:wrap; } .research-title { font-size:var(--font-size-xl); } .meta-symbol { font-size:var(--font-size-lg); } }
</style>
