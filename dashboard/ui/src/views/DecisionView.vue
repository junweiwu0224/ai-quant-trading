<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Activity,
  ArrowRight,
  BellRing,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Database,
  Eye,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Star,
  Trash2,
} from 'lucide-vue-next'
import { api } from '../api/client'
import type { DecisionMatrix, WatchlistItem } from '../types'
import { useAppStore } from '../stores/app'
import { useResearchContextStore } from '../stores/researchContext'

type AnyRecord = Record<string, any>
type OpportunityScope = 'signal' | 'watchlist'

const app = useAppStore()
const researchContext = useResearchContextStore()
const portfolios = ref<AnyRecord[]>([])
const selected = ref<AnyRecord | null>(null)
const result = ref<AnyRecord | null>(null)
const watchlist = ref<WatchlistItem[]>([])
const radar = ref<AnyRecord | null>(null)
const signalMatrix = ref<DecisionMatrix | null>(null)
const watchlistMatrix = ref<DecisionMatrix | null>(null)
const marketCapabilities = ref<AnyRecord[]>([])
const alertHistory = ref<AnyRecord[]>([])
const alertLoaded = ref(false)
const busy = ref(false)
const researchBusy = ref(false)
const message = ref('')
const researchError = ref('')
const symbol = ref('')
const showCreate = ref(false)
const createName = ref('我的决策组合')
const opportunityScope = ref<OpportunityScope>('signal')
const watchlistActionCode = ref('')
let loadSequence = 0

const radarBoards = [
  { key: 'top_gainers', label: '涨幅榜', icon: '↑' },
  { key: 'top_losers', label: '跌幅榜', icon: '↓' },
  { key: 'top_amplitude', label: '振幅榜', icon: '↕' },
  { key: 'top_turnover', label: '换手榜', icon: '↗' },
]

function settledValue<T>(entry: PromiseSettledResult<T>): T | null {
  return entry.status === 'fulfilled' ? entry.value : null
}

function plainCode(value: unknown): string {
  return String(value || '').trim().toUpperCase().replace(/^(SH|SZ|BJ|HK|US|JP|KR|TW)[.]?/, '').replace(/[.]HK$/, '')
}

function numberOrDash(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number)
    ? number.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })
    : '—'
}

function percentOrDash(value: unknown): string {
  const formatted = numberOrDash(value, 2)
  return formatted === '—' ? formatted : `${formatted}%`
}

function timeOrDash(value: unknown): string {
  if (!value) return '—'
  return String(value).replace('T', ' ').replace('Z', '')
}

function actionLabel(action: unknown): string {
  return ({
    buy_candidate: '买入候选',
    watch: '关注',
    hold: '观望',
    reduce_candidate: '减仓候选',
    major_risk: '重大风险',
    stale: '数据过期',
    decision_invalid: '不可判断',
  } as Record<string, string>)[String(action || '')] || String(action || '—')
}

const decisions = computed(() => result.value?.decisions || [])
const readyCount = computed(() => decisions.value.filter((item: AnyRecord) => item.valid).length)
const riskCount = computed(() => decisions.value.filter((item: AnyRecord) => item.action === 'major_risk').length)
const activeMatrix = computed(() => opportunityScope.value === 'signal' ? signalMatrix.value : watchlistMatrix.value)
const matrixItems = computed<AnyRecord[]>(() => (activeMatrix.value?.items || []) as AnyRecord[])
const matrixSummary = computed<AnyRecord>(() => (activeMatrix.value?.summary || {}) as AnyRecord)
const currentCapability = computed<AnyRecord | null>(() => marketCapabilities.value.find((item) => String(item.market || item.code || '').toUpperCase() === app.market) || null)
const currentMarketIsManualOnly = computed(() => !currentCapability.value?.automatic_push_supported && !currentCapability.value?.automatic_push)
const matrixNeedsManualReview = computed(() => {
  const coverage = Number(matrixSummary.value.signal_coverage_pct)
  return Boolean(
    matrixSummary.value.used_fallback
    || matrixSummary.value.signal_quality?.confidence === 'unverified'
    || matrixSummary.value.signal_status === 'unavailable'
    || !Number.isFinite(coverage)
    || coverage < 80
    || matrixItems.value.some((item) => item.stale),
  )
})
const matrixTrustClass = computed(() => {
  if (!activeMatrix.value) return 'trust-loading'
  if (matrixSummary.value.used_fallback) return 'trust-fallback'
  if (matrixNeedsManualReview.value) return 'trust-review'
  return 'trust-real'
})
const matrixTrustLabel = computed(() => ({
  'trust-loading': '等待加载',
  'trust-fallback': '降级预览',
  'trust-review': '需复核',
  'trust-real': '真实合成',
} as Record<string, string>)[matrixTrustClass.value])
const matrixTrustText = computed(() => {
  if (!activeMatrix.value) return '研究池尚未返回，缺失数据不会被替换成 0。'
  if (matrixSummary.value.used_fallback) return `当前使用默认候选池：${matrixSummary.value.fallback_reason || '原始范围为空'}。先补齐真实范围再做策略判断。`
  if (matrixNeedsManualReview.value) return '数据覆盖或新鲜度不足，当前列表只用于研究优先级排序；它不是确定性决策分，也不具备自动推送资格。'
  return matrixSummary.value.signal_quality?.message || matrixSummary.value.valuation_error || '结果由当前行情、估值和信号快照合成。'
})
const capabilityMessage = computed(() => {
  if (!currentCapability.value) return '市场能力清单尚未返回，自动推送保持关闭。'
  if (currentCapability.value.automatic_push || currentCapability.value.automatic_push_supported) return '已声明推送形状，但仍必须通过 provider 健康、验证、完整覆盖和目标测试。'
  return currentCapability.value.fallback_reason || currentCapability.value.reason || '当前市场仅支持受控手动研究，自动推送不可用。'
})
const alertCountLabel = computed(() => alertLoaded.value ? String(alertHistory.value.length) : '—')

function researchPath(code: unknown): string {
  const normalized = plainCode(code)
  return normalized ? `/app/research/${app.market}/${encodeURIComponent(normalized)}` : '/app/research'
}

function selectResearch(code: unknown, name?: unknown) {
  const normalized = plainCode(code)
  if (normalized) researchContext.setInstrument({ market: app.market, symbol: normalized, name: name ? String(name) : undefined })
}
function inWatchlist(code: unknown): boolean {
  const normalized = plainCode(code)
  return Boolean(normalized && watchlist.value.some((item) => plainCode(item.code) === normalized))
}
function researchPriority(item: AnyRecord): string {
  if (item.stale || item.coverage_pct == null || Number(item.coverage_pct) < 80) return '先补数据'
  return item.matrix_rank ? `P${item.matrix_rank}` : '待复核'
}

async function loadResearch(requestedMarket: string, sequence: number) {
  researchBusy.value = true
  researchError.value = ''
  try {
    const results = await Promise.allSettled([
      api.watchlist(),
      requestedMarket === 'CN' ? api.marketRadar() : Promise.resolve(null),
      requestedMarket === 'CN' ? api.decisionMatrix('signal') : Promise.resolve(null),
      requestedMarket === 'CN' ? api.decisionMatrix('watchlist') : Promise.resolve(null),
      api.alertHistory(),
      api.decisionMarkets(),
    ])
    if (sequence !== loadSequence || requestedMarket !== app.market) return

    const watchlistResponse = settledValue(results[0])
    const radarResponse = settledValue(results[1])
    const signalResponse = settledValue(results[2])
    const watchlistMatrixResponse = settledValue(results[3])
    const alertsResponse = settledValue(results[4]) as AnyRecord | null
    const capabilityResponse = settledValue(results[5]) as { items?: AnyRecord[] } | null

    watchlist.value = Array.isArray(watchlistResponse) ? watchlistResponse : []
    app.watchlist.splice(0, app.watchlist.length, ...watchlist.value)
    radar.value = radarResponse as AnyRecord | null
    signalMatrix.value = signalResponse as DecisionMatrix | null
    watchlistMatrix.value = watchlistMatrixResponse as DecisionMatrix | null
    alertHistory.value = Array.isArray(alertsResponse?.alerts) ? alertsResponse.alerts : []
    alertLoaded.value = results[4].status === 'fulfilled'
    marketCapabilities.value = Array.isArray(capabilityResponse?.items) ? capabilityResponse.items : []

    const failed = results.filter((entry, index) => entry.status === 'rejected' && index !== 1 && index !== 2 && index !== 3).length
    const marketDataFailed = requestedMarket === 'CN' && [results[1], results[2], results[3]].some((entry) => entry.status === 'rejected')
    if (failed || marketDataFailed) researchError.value = '部分研究数据暂不可用；当前页面保留可验证的已返回内容。'
  } finally {
    if (sequence === loadSequence) researchBusy.value = false
  }
}

async function refreshResearch() {
  const sequence = ++loadSequence
  await loadResearch(app.market, sequence)
}

async function load() {
  const sequence = ++loadSequence
  const requestedMarket = app.market
  busy.value = true
  message.value = ''
  portfolios.value = []
  selected.value = null
  result.value = null
  try {
    const responses = await Promise.allSettled([
      api.get<{ items: AnyRecord[] }>(`/api/decisions/portfolios?market=${encodeURIComponent(requestedMarket)}`),
      loadResearch(requestedMarket, sequence),
    ])
    if (sequence !== loadSequence || requestedMarket !== app.market) return
    const portfolioResponse = settledValue(responses[0]) as { items?: AnyRecord[] } | null
    if (!portfolioResponse) {
      message.value = '策略组合加载失败；研究数据仍可单独查看。'
      return
    }
    portfolios.value = Array.isArray(portfolioResponse.items) ? portfolioResponse.items : []
    selected.value = portfolios.value[0] || null
    if (selected.value) await analyze('preview', sequence)
  } finally {
    if (sequence === loadSequence) busy.value = false
  }
}

async function analyze(kind: 'preview' | 'manual' = 'preview', sequence = loadSequence) {
  if (!selected.value) return
  const requestedMarket = app.market
  busy.value = true
  message.value = ''
  try {
    const endpoint = kind === 'manual' ? 'analyze' : 'preview'
    const queued = await api.post<{ command_id: string }>(`/api/decisions/portfolios/${encodeURIComponent(selected.value.id)}/${endpoint}`, {})
    const command = await api.waitDecisionCommand<AnyRecord>(queued.command_id)
    if (sequence !== loadSequence || requestedMarket !== app.market) return
    if (command.status === 'rejected') {
      const reasons = command.result?.eligibility?.reasons || []
      message.value = reasons.length ? `操作被阻断：${reasons.join('、')}` : '操作被 Worker 拒绝'
      return
    }
    result.value = command.result || null
  } catch (error) {
    if (sequence === loadSequence) message.value = error instanceof Error ? error.message : '分析失败'
  } finally {
    if (sequence === loadSequence) busy.value = false
  }
}

async function createPortfolio() {
  busy.value = true
  message.value = ''
  try {
    const portfolio = await api.post<AnyRecord>('/api/decisions/portfolios', { market: app.market, name: createName.value })
    for (const item of watchlist.value) await api.post(`/api/decisions/portfolios/${portfolio.id}/members`, { symbol: item.code, name: item.name || '' })
    showCreate.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建组合失败'
  } finally {
    busy.value = false
  }
}

async function addSymbol() {
  if (!selected.value || !symbol.value.trim()) return
  try {
    await api.post(`/api/decisions/portfolios/${selected.value.id}/members`, { symbol: symbol.value.trim() })
    symbol.value = ''
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加入组合失败'
  }
}

async function addToWatchlist(code: unknown) {
  const normalized = String(code || '').trim()
  if (!normalized) return
  watchlistActionCode.value = normalized
  try {
    await api.addWatchlist(normalized)
    await refreshResearch()
  } catch (error) {
    researchError.value = error instanceof Error ? error.message : '加入自选失败'
  } finally {
    watchlistActionCode.value = ''
  }
}

async function removeFromWatchlist(code: string) {
  watchlistActionCode.value = code
  try {
    await api.removeWatchlist(code)
    await refreshResearch()
  } catch (error) {
    researchError.value = error instanceof Error ? error.message : '移出自选失败'
  } finally {
    watchlistActionCode.value = ''
  }
}

watch(() => app.market, (nextMarket, previousMarket) => {
  if (nextMarket !== previousMarket) void load()
})
onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div><h1>把自选池变成可追溯决策</h1><p>先选策略组合，再查看冻结输入、策略贡献和数据资格。自动推送资格与手动分析完全分开。</p></div>
      <div class="head-actions"><button class="button" :disabled="busy || researchBusy" @click="load"><RefreshCw :size="16" :class="{ spin: busy || researchBusy }" />刷新</button><button class="button primary" @click="showCreate = true"><Plus :size="16" />从自选池创建组合</button></div>
    </div>
    <div v-if="message" class="error-box" role="alert"><CircleAlert :size="16" />{{ message }}</div>
    <div v-if="researchError" class="error-box decision-research-error" role="status"><Database :size="16" />{{ researchError }}</div>

    <section class="panel decision-capability-panel">
      <div class="panel-body capability-state">
        <span class="tag" :class="currentMarketIsManualOnly ? 'warn' : 'good'">{{ currentMarketIsManualOnly ? '仅手动研究' : '自动推送需再验证' }}</span>
        <strong>{{ app.market }} 市场能力边界</strong>
        <span>{{ capabilityMessage }}</span>
        <small v-if="currentCapability">来源 {{ currentCapability.source || '—' }} · 状态 {{ currentCapability.source_status || '—' }} · 日线 {{ currentCapability.daily_research ? '可用' : '不可用' }}</small>
      </div>
    </section>

    <div class="summary-strip decision-summary-strip">
      <div class="summary-item"><span>当前组合</span><strong>{{ selected?.name || '未选择' }}</strong><small>{{ selected?.members?.length == null ? '—' : `${selected.members.length} 个成员` }}</small></div>
      <div class="summary-item"><span>研究池</span><strong>{{ matrixSummary.total == null ? '—' : matrixSummary.total }}</strong><small>{{ opportunityScope === 'signal' ? 'AI 信号范围' : '当前工作区自选' }}</small></div>
      <div class="summary-item"><span>预警历史</span><strong>{{ alertCountLabel }}</strong><small>最近读取结果</small></div>
      <div class="summary-item"><span>自动推送</span><strong>{{ result?.eligibility?.eligible ? '可申请' : '未达标' }}</strong><small>{{ result?.eligibility?.reasons?.[0] || '等待组合资格检查' }}</small></div>
    </div>

    <div class="section-grid two">
      <div class="stack-lg">
        <section class="panel">
          <div class="panel-head"><div><h2>策略组合</h2><p>同一股票可以属于多个组合，历史运行不会被覆盖。</p></div><span class="tag">{{ app.market }}</span></div>
          <div class="panel-body">
            <div v-if="!portfolios.length" class="empty"><strong>还没有策略组合</strong><span>从当前自选池创建第一份组合，或手动加入成员。</span><div class="form-actions" style="justify-content:center"><button class="button primary" @click="showCreate = true"><Plus :size="16" />创建组合</button><RouterLink class="button ghost" to="/app/research">打开单股研究</RouterLink></div></div>
            <div v-else class="portfolio-list">
              <div v-for="item in portfolios" :key="item.id" class="portfolio-row" :class="{ selected: selected?.id === item.id }">
                <button @click="selected = item; analyze('preview')"><span class="portfolio-name">{{ item.name }}</span><span class="portfolio-meta">{{ item.members?.length || 0 }} 个成员 · 版本 {{ item.version?.version_no || 0 }}</span></button><span class="tag" :class="item.version ? 'good' : 'warn'">{{ item.version ? '已版本化' : '待配置' }}</span><ArrowRight :size="16" class="faint" />
              </div>
            </div>
          </div>
        </section>

        <section v-if="app.market === 'CN'" class="panel">
          <div class="panel-head"><div><h2>市场雷达</h2><p>快路径优先读取本地覆盖池或缓存，来源和过期状态始终可见。</p></div><Activity :size="18" class="faint" /></div>
          <div class="panel-body">
            <div v-if="researchBusy && !radar" class="empty"><RefreshCw :size="16" class="spin" />正在读取市场雷达…</div>
            <div v-else-if="!radar" class="empty"><strong>市场雷达暂无数据</strong><span>当前没有可验证的全市场或本地覆盖结果。</span></div>
            <template v-else>
              <div class="radar-meta data-source"><span><Database :size="14" />{{ radar.source || '—' }}</span><span><Clock3 :size="14" />{{ timeOrDash(radar.generated_at || radar.latest_date) }}</span><span class="tag" :class="radar.source_unavailable ? 'bad' : radar.stale ? 'warn' : 'good'">{{ radar.source_unavailable ? '来源不可用' : radar.stale ? '可能过期' : '已读取' }}</span></div>
              <p class="muted small radar-note">{{ radar.coverage_note || radar.fast_path_note || '—' }}</p>
              <div class="radar-grid">
                <div v-for="board in radarBoards" :key="board.key" class="radar-board"><div class="radar-board-head"><strong>{{ board.icon }} {{ board.label }}</strong><span>{{ radar[board.key]?.length || 0 }} 条</span></div><div v-if="!radar[board.key]?.length" class="empty compact-empty">暂无可验证记录</div><RouterLink v-for="row in (radar[board.key] || []).slice(0, 5)" :key="`${board.key}-${row.code}`" class="radar-row" :to="researchPath(row.code)" @click="selectResearch(row.code, row.name)"><span><strong>{{ row.code || '—' }}</strong><small>{{ row.name || row.industry || '—' }}</small></span><span class="radar-value">{{ row.value == null ? '—' : numberOrDash(row.value) }}</span></RouterLink></div>
              </div>
            </template>
          </div>
        </section>

        <section class="panel opportunity-panel">
          <div class="panel-head"><div><h2>机会池</h2><p>基于 decision matrix 的 signal / watchlist 范围；缺失 provider 不会产生虚假候选。</p></div><Star :size="18" class="faint" /></div>
          <div class="panel-body">
            <div v-if="app.market !== 'CN'" class="capability-state opportunity-capability"><span class="tag warn">{{ currentCapability?.daily_research ? '日线研究可用' : '当前市场待接入' }}</span><strong>{{ app.market }} 市场研究状态</strong><span>{{ capabilityMessage }}</span><RouterLink v-if="currentCapability?.daily_research" class="button ghost compact-button" :to="researchPath(app.market === 'US' ? 'AAPL' : app.market === 'HK' ? '00700' : app.market === 'JP' ? '7203' : app.market === 'KR' ? '005930' : '2330')" @click="selectResearch(app.market === 'US' ? 'AAPL' : app.market === 'HK' ? '00700' : app.market === 'JP' ? '7203' : app.market === 'KR' ? '005930' : '2330')">打开示例研究</RouterLink></div>
            <template v-else>
              <div class="workspace-tabs" role="tablist" aria-label="机会池范围"><button type="button" :class="{ active: opportunityScope === 'signal' }" :aria-selected="opportunityScope === 'signal'" @click="opportunityScope = 'signal'"><Activity :size="15" />AI 信号 Top</button><button type="button" :class="{ active: opportunityScope === 'watchlist' }" :aria-selected="opportunityScope === 'watchlist'" @click="opportunityScope = 'watchlist'"><Star :size="15" />当前自选</button></div>
              <div class="opportunity-trust-panel" :class="matrixTrustClass" role="status"><span class="opportunity-trust-badge">{{ matrixTrustLabel }}</span><span class="opportunity-trust-text">{{ matrixTrustText }}</span><span class="opportunity-trust-meta">覆盖 {{ matrixSummary.signal_coverage_pct == null ? '—' : `${matrixSummary.signal_coverage_pct}%` }} · 生成 {{ timeOrDash(matrixSummary.generated_at) }}</span></div>
              <div v-if="researchBusy && !activeMatrix" class="empty"><RefreshCw :size="16" class="spin" />正在读取机会池…</div>
              <div v-else-if="!activeMatrix" class="empty"><strong>机会池暂未返回</strong><span>刷新后会重新请求当前范围。</span></div>
              <div v-else-if="!matrixItems.length" class="empty"><strong>当前范围没有可验证候选</strong><span>{{ opportunityScope === 'watchlist' ? '先加入自选股，再刷新当前范围。' : '当前没有已返回的 signal 记录。' }}</span></div>
              <div v-else class="table-scroll"><table class="decision-table opportunity-table"><thead><tr><th>标的</th><th>价格</th><th>研究动作</th><th>风险</th><th>数据</th><th>操作</th></tr></thead><tbody><tr v-for="item in matrixItems.slice(0, 12)" :key="String(item.code)"><td><RouterLink class="symbol-link" :to="researchPath(item.code)" @click="selectResearch(item.code, item.name)"><span class="symbol">{{ item.code || '—' }}</span><small>{{ item.name || '—' }}</small></RouterLink></td><td><strong>{{ numberOrDash(item.price) }}</strong><small :class="Number(item.change_pct) >= 0 ? 'good' : 'bad'">{{ percentOrDash(item.change_pct) }}</small></td><td><strong class="action" :class="item.primary_action === '进重点池' ? 'buy_candidate' : item.primary_action === '减仓候选' ? 'reduce_candidate' : 'watch'">{{ item.primary_action || '—' }}</strong><small>研究优先级 {{ researchPriority(item) }}</small></td><td><span class="tag" :class="item.risk_level === '高' ? 'bad' : item.risk_level === '中' ? 'warn' : ''">{{ item.risk_level || '—' }}</span></td><td><span class="tag" :class="item.stale ? 'warn' : item.coverage_pct == null ? '' : 'good'">{{ item.stale ? '可能过期' : item.coverage_pct == null ? '覆盖未知' : `覆盖 ${item.coverage_pct}%` }}</span><small>{{ item.source || item.signal_provider || '—' }}</small></td><td><button v-if="!inWatchlist(item.code)" class="icon-button compact-icon" :disabled="watchlistActionCode === item.code" title="加入自选" aria-label="加入自选" @click="addToWatchlist(item.code)"><Plus :size="15" /></button><span v-else class="tag good"><Star :size="13" />已自选</span></td></tr></tbody></table></div>
            </template>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><div><h2>组合决策</h2><p>首次普通状态只记录不推送；风险和状态变化按规则去重。</p></div><div class="head-actions"><button class="button" :disabled="busy || !selected" @click="analyze('manual')"><Search :size="16" />手动分析</button><RouterLink class="button ghost" to="/app/reports">查看报告</RouterLink></div></div>
          <div class="panel-body">
            <div v-if="!result" class="empty"><strong>选择一个组合开始</strong><span>当前页面不会用空白或 0 分掩盖缺失数据。</span></div>
            <div v-else-if="!decisions.length" class="empty"><strong>组合没有成员</strong><span>添加自选股后才能生成预览。</span></div>
            <div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>标的</th><th>动作</th><th>规则评分</th><th>数据</th><th>原因</th></tr></thead><tbody><tr v-for="item in decisions" :key="item.id"><td><span class="symbol">{{ item.symbol || '—' }}</span></td><td><span class="action" :class="item.action">{{ actionLabel(item.action) }}</span></td><td>{{ numberOrDash(item.score, 1) }}</td><td><span class="tag" :class="item.valid ? 'good' : 'bad'">{{ item.valid ? '有效' : item.stale ? '过期' : '缺失' }}</span></td><td class="muted small">{{ (item.reason_codes || []).join('、') || '—' }}</td></tr></tbody></table></div>
            <div v-if="result?.snapshot" class="data-source decision-source-meta"><span><Database :size="14" />来源 {{ result.snapshot.source || '—' }}</span><span>输入 hash {{ result.snapshot.payload_hash?.slice(0, 12) || '—' }}…</span><span>更新 {{ timeOrDash(result.snapshot.payload?.updated_at || result.snapshot.payload?.captured_at || result.snapshot.created_at) }}</span><span>覆盖 {{ result.snapshot.payload?.coverage_pct == null ? '—' : `${result.snapshot.payload.coverage_pct}%` }}</span><span class="tag" :class="result.snapshot.payload?.stale ? 'warn' : result.snapshot.quality_status === 'ok' ? 'good' : 'bad'">{{ result.snapshot.payload?.stale ? '可能过期' : result.snapshot.quality_status === 'ok' ? '数据有效' : '数据不足' }}</span></div>
          </div>
        </section>
      </div>

      <aside class="stack-lg">
        <section class="panel"><div class="panel-head"><div><h2>自动推送资格</h2><p>资格通过之前，开关不可绕过。</p></div><ShieldAlert :size="18" class="faint" /></div><div class="panel-body"><div v-if="result?.eligibility" class="check-list"><div v-for="(value, key) in result.eligibility.checks" :key="key" class="check-row"><div class="check-copy"><strong>{{ ({ preview_ok: '真实预览', validation_ok: '历史验证', health_ok: '当前健康', adapter_ok: '市场能力', target_ok: '通知目标' } as AnyRecord)[key] || key }}</strong><span>{{ value ? '已满足' : (result.eligibility.reasons?.[0] || '尚未满足') }}</span></div><CheckCircle2 v-if="value" :size="18" class="good" /><CircleAlert v-else :size="18" class="faint" /></div></div><div v-else class="empty">完成一次预览后显示资格检查。</div><div class="form-actions"><RouterLink class="button ghost" to="/app/validation">进入验证</RouterLink><RouterLink class="button ghost" to="/app/notifications">配置通知</RouterLink></div></div></section>

        <section class="panel"><div class="panel-head"><div><h2>当前工作区自选</h2><p>自选写入沿用当前 workspace；移除只影响自选池，不回写历史报告。</p></div><Star :size="18" class="faint" /></div><div class="panel-body"><div v-if="researchBusy && !watchlist.length" class="empty"><RefreshCw :size="16" class="spin" />正在读取自选…</div><div v-else-if="!watchlist.length" class="empty"><strong>当前自选为空</strong><span>可以从机会池加入，或前往单股研究搜索入口。</span></div><div v-else class="watchlist-list"><div v-for="item in watchlist" :key="item.code" class="watchlist-row"><RouterLink :to="researchPath(item.code)" @click="selectResearch(item.code, item.name)"><strong>{{ item.code }}</strong><small>{{ item.name || item.industry || '—' }}</small></RouterLink><span class="watchlist-quote"><strong>{{ numberOrDash(item.price) }}</strong><small :class="Number(item.change_pct) >= 0 ? 'good' : 'bad'">{{ percentOrDash(item.change_pct) }}</small></span><button class="icon-button compact-icon" :disabled="watchlistActionCode === item.code" title="移出自选" aria-label="移出自选" @click="removeFromWatchlist(item.code)"><Trash2 :size="15" /></button></div></div></div></section>

        <section class="panel"><div class="panel-head"><div><h2>预警历史</h2><p>只展示接口返回的触发记录；没有记录不等于当前没有风险。</p></div><BellRing :size="18" class="faint" /></div><div class="panel-body"><div v-if="!alertLoaded" class="empty"><RefreshCw :size="16" class="spin" />正在读取预警历史…</div><div v-else-if="!alertHistory.length" class="empty"><strong>暂无预警历史</strong><span>当前接口没有返回触发记录。</span></div><div v-else class="alert-list"><div v-for="(alert, index) in alertHistory.slice(0, 8)" :key="String(alert.id || index)" class="alert-row"><div><strong>{{ alert.code || alert.name || alert.condition || '预警事件' }}</strong><small>{{ alert.message || alert.condition_label || alert.threshold || '—' }}</small></div><span>{{ timeOrDash(alert.triggered_at || alert.created_at || alert.time) }}</span></div></div></div></section>

        <section class="panel"><div class="panel-head"><div><h2>快速加入组合成员</h2><p>只修改组合成员，不会改写既有运行。</p></div><Eye :size="18" class="faint" /></div><div class="panel-body"><div class="field"><label for="symbol">股票代码</label><input id="symbol" v-model="symbol" placeholder="例如 600519" @keyup.enter="addSymbol" /></div><div class="form-actions"><button class="button" :disabled="!selected || !symbol.trim() || busy" @click="addSymbol"><Plus :size="16" />加入当前组合</button></div><p class="muted small" style="margin:14px 0 0">组合成员变更不会重写既有快照；未接入合格 provider 时不会生成自动信号。</p></div></section>
      </aside>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false"><section class="modal panel"><div class="panel-head"><div><h2>创建策略组合</h2><p>默认导入当前 workspace 的自选股。</p></div><button class="icon-button" title="关闭" aria-label="关闭" @click="showCreate = false">×</button></div><div class="panel-body"><div class="field"><label for="portfolio-name">组合名称</label><input id="portfolio-name" v-model="createName" /></div><div class="form-actions"><button class="button" @click="showCreate = false">取消</button><button class="button primary" :disabled="busy || !createName.trim()" @click="createPortfolio">创建并预览</button></div></div></section></div>
  </section>
</template>
