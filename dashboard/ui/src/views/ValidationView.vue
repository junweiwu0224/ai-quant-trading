<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { BarChart3, CheckCircle2, CircleAlert, Download, Play, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api/client'
import { useResearchContextStore } from '../stores/researchContext'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import AsyncState from '../components/base/AsyncState.vue'

type Row = Record<string, any>
type Workspace = 'backtest' | 'robustness' | 'analysis' | 'portfolio'

const contextStore = useResearchContextStore()
const route = useRoute()
const contextInstrument = computed(() => contextStore.hasInstrument ? `${contextStore.context.market} / ${contextStore.context.symbol}` : '')
const hasResearchContext = computed(() => contextStore.hasInstrument)

const workspace = ref<Workspace>('backtest')
const portfolios = ref<Row[]>([])
const selected = ref<Row | null>(null)
const strategies = ref<Row[]>([])
const benchmarks = ref<Row[]>([])
const validation = ref<Row | null>(null)
const eligibility = ref<Row | null>(null)
const backtest = ref<Row | null>(null)
const monthly = ref<Row[]>([])
const drawdown = ref<Row[]>([])
const robustness = ref<Row | null>(null)
const comparison = ref<Row[]>([])
const analysis = ref<Record<string, Row | null>>({})
const loading = ref(false)
const refreshing = ref(false)
const message = ref('')
const noticeState = ref<'success' | 'partial' | 'error' | ''>('')
const form = ref({
  strategy: '', codes: '', start_date: '2023-01-01', end_date: '2024-12-31',
  initial_cash: 1000000, commission_rate: 0.0003, stamp_tax_rate: 0.001, slippage: 0.002,
  benchmark: '', period: 'daily', enable_risk: false,
})
const trainRatio = ref(0.7)
const simulations = ref(1000)
const compareSelection = ref<string[]>([])

const canPreviewPaper = computed(() => Boolean(backtest.value && contextStore.hasInstrument && contextStore.context.eligibility?.eligible === true))
const tabs: Array<{ key: Workspace; label: string }> = [
  { key: 'backtest', label: '回测工作流' }, { key: 'robustness', label: '样本外与 Monte Carlo' },
  { key: 'analysis', label: '收益、交易与成本' }, { key: 'portfolio', label: '组合资格' },
]
const codes = computed(() => [...new Set(form.value.codes.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean))])
const requestBody = computed(() => ({ ...form.value, codes: codes.value }))
function queryValue(key: string): string {
  const value = route.query[key]
  return Array.isArray(value) ? String(value[0] || '').trim() : String(value || '').trim()
}

function hydrateInstrumentFromRoute() {
  const market = queryValue('market').toUpperCase()
  const symbol = queryValue('symbol')
  if (market && symbol) contextStore.setInstrument({ market, symbol })
  const strategy = queryValue('strategyId') || queryValue('strategy')
  if (strategy) contextStore.setStrategy(strategy)
}

const equityPoints = computed(() => {
  const curve = Array.isArray(backtest.value?.equity_curve) ? backtest.value.equity_curve : []
  if (!curve.length) return []
  const values = curve.map((item: Row) => Number(item.equity)).filter((item: number) => Number.isFinite(item))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const spread = max - min || Math.max(max * 0.01, 1)
  return curve.map((item: Row, index: number) => ({
    x: 18 + index / Math.max(1, curve.length - 1) * 724,
    y: 224 - (Number(item.equity) - min) / spread * 192,
  }))
})
function chartCoordinate(value: number): string {
  return Number.isFinite(value) ? (Math.round(value * 10) / 10).toString() : '0'
}

const equityPath = computed(() => equityPoints.value.map((point, index) => `${index ? 'L' : 'M'} ${chartCoordinate(point.x)} ${chartCoordinate(point.y)}`).join(' '))
const drawdownPoints = computed(() => {
  const rows = drawdown.value.filter((item) => Number.isFinite(Number(item.drawdown_pct)))
  if (!rows.length) return []
  const maxDepth = Math.max(...rows.map((item) => Math.abs(Number(item.drawdown_pct))), 0.01)
  return rows.map((item, index) => ({
    x: 18 + index / Math.max(1, rows.length - 1) * 724,
    y: 30 + Math.abs(Number(item.drawdown_pct)) / maxDepth * 192,
  }))
})
const drawdownPath = computed(() => drawdownPoints.value.map((point, index) => `${index ? 'L' : 'M'} ${chartCoordinate(point.x)} ${chartCoordinate(point.y)}`).join(' '))
const latestMetric = computed(() => {
  const item = backtest.value || {}
  return [
    ['总收益', percent(item.total_return)], ['年化收益', percent(item.annual_return)], ['最大回撤', percent(item.max_drawdown)],
    ['夏普', value(item.sharpe_ratio)], ['胜率', percent(item.win_rate)], ['交易次数', value(item.total_trades, 0)],
  ]
})

function value(item: unknown, digits = 2) {
  if (item === null || item === undefined || item === '' || !Number.isFinite(Number(item))) return '—'
  return Number(item).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}
function percent(item: unknown) {
  if (item === null || item === undefined || !Number.isFinite(Number(item))) return '—'
  return `${(Number(item) * 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })}%`
}
function signedPercent(item: unknown) {
  if (item === null || item === undefined || !Number.isFinite(Number(item))) return '—'
  const number = Number(item) * 100
  const formatted = number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })
  return `${number > 0 ? '+' : ''}${formatted}%`
}
function resultClass(item: unknown) {
  return Number(item) >= 0 ? 'good' : 'bad'
}
function list(valueItem: unknown, key?: string): Row[] {
  if (Array.isArray(valueItem)) return valueItem
  if (valueItem && typeof valueItem === 'object' && key && Array.isArray((valueItem as Row)[key])) return (valueItem as Row)[key]
  return []
}
function bodyError(payload: Row | null) {
  return payload?.error ? String(payload.error) : ''
}
function clearNotice() {
  message.value = ''
  noticeState.value = ''
}
function setNotice(state: 'success' | 'partial' | 'error', valueItem: unknown, fallback: string) {
  noticeState.value = state
  message.value = valueItem instanceof Error ? valueItem.message : String(valueItem || fallback)
}

async function load() {
  if (!hasResearchContext.value) {
    strategies.value = await api.backtestStrategies()
    benchmarks.value = await api.backtestBenchmarks()
    form.value.strategy = ''
    form.value.codes = ''
    return
  }

  form.value.codes = contextStore.context.symbol || ''
  form.value.strategy = contextStore.context.strategy || ''
  if (contextStore.context.backtestRequest) {
    Object.assign(form.value, contextStore.context.backtestRequest)
  }
  loading.value = true
  refreshing.value = Boolean(backtest.value || validation.value || robustness.value)
  clearNotice()
  try {
    const [portfolioResponse, strategyResponse, benchmarkResponse] = await Promise.all([
      api.get<{ items: Row[] }>('/api/decisions/portfolios'), api.backtestStrategies(), api.backtestBenchmarks(),
    ])
    portfolios.value = portfolioResponse.items || []
    strategies.value = strategyResponse
    benchmarks.value = benchmarkResponse
    if (!form.value.strategy && strategyResponse[0]) form.value.strategy = String(strategyResponse[0].name)
    selected.value = portfolios.value[0] || null
    compareSelection.value = strategyResponse.slice(0, 3).map((item) => String(item.name || '')).filter(Boolean)
    if (selected.value) await checkPortfolio()
  } catch (error) {
    setNotice('error', error, '验证数据加载失败')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function checkPortfolio() {
  if (!selected.value) return
  loading.value = true
  clearNotice()
  try {
    const queued = await api.post<{ command_id: string }>(`/api/decisions/portfolios/${selected.value.id}/validate`, {})
    const command = await api.waitDecisionCommand<Row>(queued.command_id)
    validation.value = command.result?.validation || null
    eligibility.value = command.result?.eligibility || null
    contextStore.setEligibility(eligibility.value)
    if (command.status === 'rejected') setNotice('error', command.result?.eligibility?.reasons?.join('、'), '资格检查被 Worker 拒绝')
  } catch (error) {
    setNotice('error', error, '资格检查失败')
  } finally {
    loading.value = false
  }
}

async function previewPortfolio() {
  if (!selected.value) return
  loading.value = true
  clearNotice()
  try {
    const queued = await api.post<{ command_id: string }>(`/api/decisions/portfolios/${selected.value.id}/preview`, {})
    const command = await api.waitDecisionCommand<Row>(queued.command_id)
    eligibility.value = command.result?.eligibility || null
    contextStore.setEligibility(eligibility.value)
    if (command.status !== 'completed') {
      setNotice('error', command.result?.eligibility?.reasons?.join('、'), '真实预览未完成')
      return
    }
    setNotice('success', '', '真实预览已冻结；决策中心可查看本次输入和报告。')
  } catch (error) {
    setNotice('error', error, '预览失败')
  } finally {
    loading.value = false
  }
}

async function runBacktest() {
  if (!hasResearchContext.value) { setNotice('error', '', '请先从决策中心选择研究对象'); return }
  if (!codes.value.length) { setNotice('error', '', '至少填写一个股票代码'); return }
  loading.value = true
  clearNotice()
  try {
    backtest.value = await api.backtestRun(requestBody.value)
    if (bodyError(backtest.value)) { setNotice('error', bodyError(backtest.value), '回测失败'); return }
    contextStore.setStrategy(form.value.strategy)
    contextStore.setBacktest(requestBody.value, backtest.value)
    workspace.value = 'backtest'
    const [monthlyResult, drawdownResult] = await Promise.allSettled([api.backtestMonthlyReturns(requestBody.value), api.backtestDrawdown(requestBody.value)])
    if (monthlyResult.status === 'fulfilled') monthly.value = monthlyResult.value
    if (drawdownResult.status === 'fulfilled') drawdown.value = drawdownResult.value
    await loadAnalysis()
  } catch (error) {
    setNotice('error', error, '回测失败')
  } finally {
    loading.value = false
  }
}
async function runRobustness() {
  if (!hasResearchContext.value) {
    setNotice('error', '', '请先从决策中心选择研究对象，再进行回测和稳健性验证')
    return
  }
  loading.value = true
  clearNotice()
  try {
    const common = { strategy: form.value.strategy, codes: codes.value, initial_cash: form.value.initial_cash, commission_rate: form.value.commission_rate, stamp_tax_rate: form.value.stamp_tax_rate, slippage: form.value.slippage, enable_risk: form.value.enable_risk }
    const [oosResult, mcResult] = await Promise.allSettled([
      api.backtestOutOfSample({ ...common, full_start_date: form.value.start_date, full_end_date: form.value.end_date, train_ratio: trainRatio.value, benchmark: form.value.benchmark }),
      api.backtestMonteCarlo({ ...common, start_date: form.value.start_date, end_date: form.value.end_date, simulations: simulations.value }),
    ])
    robustness.value = { out_of_sample: oosResult.status === 'fulfilled' ? oosResult.value : { error: '样本外请求失败' }, monte_carlo: mcResult.status === 'fulfilled' ? mcResult.value : { error: 'Monte Carlo 请求失败' } }
    workspace.value = 'robustness'
    if (oosResult.status === 'rejected' || mcResult.status === 'rejected') setNotice('partial', '', '稳健性结果部分可用；缺失部分已在结果区标明。')
  } catch (error) {
    setNotice('error', error, '稳健性验证失败')
  } finally {
    loading.value = false
  }
}
async function runComparison() {
  if (!hasResearchContext.value) {
    setNotice('error', '', '请先从决策中心选择研究对象，再进行策略比较')
    return
  }
  loading.value = true
  clearNotice()
  try {
    comparison.value = await api.backtestCompare({ strategies: compareSelection.value, codes: codes.value, start_date: form.value.start_date, end_date: form.value.end_date, initial_cash: form.value.initial_cash })
    workspace.value = 'analysis'
  } catch (error) {
    setNotice('error', error, '策略比较失败')
  } finally {
    loading.value = false
  }
}

async function loadAnalysis() {
  const names = ['returns', 'trades', 'weekday', 'turnover', 'holding-period', 'attribution']
  const responses = await Promise.allSettled(names.map((name) => api.backtestAnalysis(name, requestBody.value)))
  names.forEach((name, index) => { analysis.value[name] = responses[index].status === 'fulfilled' ? responses[index].value : null })
}

async function downloadPdf() {
  try {
    const response = await fetch('/api/backtest/report/pdf', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', Accept: 'application/pdf' }, body: JSON.stringify(requestBody.value) })
    if (!response.ok) throw new Error(`报告生成失败（${response.status}）`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `backtest-${form.value.strategy}-${form.value.start_date}-${form.value.end_date}.pdf`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    setNotice('error', error, 'PDF 导出失败')
  }
}

watch(() => [route.query.market, route.query.symbol, route.query.strategyId, route.query.strategy], () => {
  hydrateInstrumentFromRoute()
}, { immediate: true })

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><span class="eyebrow">VALIDATION / TRACEABLE RESULT</span><h1>验证与回测</h1><p>回测结果、样本外、Monte Carlo 和组合资格分开呈现；任何研究结果都不会直接变成订单或自动推送资格。</p></div><div class="head-actions"><RefreshIndicator :state="refreshing ? 'refreshing' : backtest || validation ? 'live' : 'unavailable'" :label="refreshing ? '保留结果，正在刷新' : '验证工作区'" /><button class="button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button></div></div>
    <AsyncState v-if="!hasResearchContext" state="empty" title="先选择研究对象" message="从决策中心或单股研究进入，系统会自动继承当前 market、symbol 和研究上下文。" />
    <template v-else>
    <div v-if="contextInstrument" class="data-source context-source"><strong>当前研究对象：{{ contextInstrument }}</strong><span>{{ contextStore.context.name || '未命名标的' }}</span></div>
    <AsyncState
      v-if="message"
      :state="noticeState || 'error'"
      :title="noticeState === 'success' ? '操作完成' : noticeState === 'partial' ? '部分可用' : '验证失败'"
      :message="message"
      @retry="load"
    />
    <div v-if="hasResearchContext && backtest" class="data-source validation-next-step"><span>回测结果已写入当前研究对象</span><RouterLink v-if="canPreviewPaper" class="button primary" :to="`/app/paper?market=${contextStore.context.market}&symbol=${encodeURIComponent(contextStore.context.symbol || '')}`">进入模拟盘预览</RouterLink><span v-else>完成资格检查后才可进入模拟盘预览</span></div>
    <section class="panel validation-form"><div class="panel-head"><div><h2>回测参数</h2><p>请求体与旧 /api/backtest/run 兼容，成本和周期显式记录。</p></div><span class="tag warn">研究操作</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="validation-strategy">策略</label><select id="validation-strategy" v-model="form.strategy" class="field-select"><option v-for="item in strategies" :key="String(item.name)" :value="String(item.name)">{{ item.label || item.name }}{{ item.legacy_alias_for ? '（兼容别名）' : '' }}</option></select></div><div class="field"><label for="validation-codes">标的代码</label><input id="validation-codes" v-model="form.codes" class="field-input" placeholder="000001,600519" /></div><div class="field"><label for="validation-start">开始日期</label><input id="validation-start" v-model="form.start_date" class="field-input" type="date" /></div><div class="field"><label for="validation-end">结束日期</label><input id="validation-end" v-model="form.end_date" class="field-input" type="date" /></div><div class="field"><label for="validation-cash">初始资金</label><input id="validation-cash" v-model.number="form.initial_cash" class="field-input" type="number" min="1" /></div><div class="field"><label for="validation-period">周期</label><select id="validation-period" v-model="form.period" class="field-select"><option value="daily">日线</option><option value="1m">1 分钟</option><option value="5m">5 分钟</option><option value="15m">15 分钟</option><option value="30m">30 分钟</option><option value="60m">60 分钟</option></select></div></div><details class="validation-advanced"><summary>高级设置 <span>基准、成本、样本外、Monte Carlo 与风控</span></summary><div class="field-grid"><div class="field"><label for="validation-benchmark">基准</label><select id="validation-benchmark" v-model="form.benchmark" class="field-select"><option value="">不设置基准</option><option v-for="item in benchmarks" :key="String(item.code)" :value="String(item.code)">{{ item.name }} · {{ item.code }}</option></select></div><div class="field"><label for="validation-commission">佣金率</label><input id="validation-commission" v-model.number="form.commission_rate" class="field-input" type="number" min="0" step="0.0001" /></div><div class="field"><label for="validation-tax">印花税率</label><input id="validation-tax" v-model.number="form.stamp_tax_rate" class="field-input" type="number" min="0" step="0.0001" /></div><div class="field"><label for="validation-slippage">滑点</label><input id="validation-slippage" v-model.number="form.slippage" class="field-input" type="number" min="0" step="0.0001" /></div><div class="field"><label for="validation-train-ratio">样本外训练比例</label><input id="validation-train-ratio" v-model.number="trainRatio" class="field-input" type="number" min="0.5" max="0.95" step="0.05" /></div><div class="field"><label for="validation-simulations">Monte Carlo 次数</label><input id="validation-simulations" v-model.number="simulations" class="field-input" type="number" min="100" max="10000" step="100" /></div></div><label class="check-control"><input v-model="form.enable_risk" type="checkbox" />启用回测风控</label></details><div class="form-actions"><button class="button primary" :disabled="loading" @click="runBacktest"><Play :size="15" />运行回测</button><button class="button" :disabled="loading" @click="runRobustness"><ShieldCheck :size="15" />运行稳健性验证</button><button class="button ghost" :disabled="loading" @click="downloadPdf"><Download :size="15" />导出 PDF</button></div></div></section>

    <nav class="workspace-tabs" aria-label="验证工作区"><button v-for="item in tabs" :key="item.key" type="button" :class="{ active: workspace === item.key }" @click="workspace = item.key">{{ item.label }}</button></nav>

    <template v-if="workspace === 'backtest'">
      <section v-if="backtest" class="summary-strip"><div v-for="item in latestMetric" :key="item[0]" class="summary-item"><span>{{ item[0] }}</span><strong :class="['总收益', '年化收益', '胜率'].includes(String(item[0])) ? resultClass(backtest?.total_return) : ''">{{ item[1] }}</strong><small>{{ backtest?.start_date || form.start_date }} → {{ backtest?.end_date || form.end_date }}</small></div></section>
      <section v-if="backtest" class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>权益曲线</h2><p>{{ equityPoints.length }} 个有效点 · 初始资金 {{ value(backtest.initial_cash, 0) }}</p></div><BarChart3 :size="19" class="faint" /></div><div class="panel-body chart-panel"><div v-if="!equityPath" class="empty">无权益曲线，不能生成图表。</div><template v-else><svg class="price-chart" viewBox="0 0 760 240" role="img" aria-label="回测权益曲线"><line x1="18" y1="224" x2="742" y2="224" class="chart-axis" /><path :d="equityPath" class="chart-line chart-line-secondary" /></svg><div class="chart-labels"><span>{{ backtest.equity_curve?.[0]?.date || '—' }}</span><strong>{{ value(backtest.final_equity, 2) }}</strong><span>{{ backtest.equity_curve?.[backtest.equity_curve.length - 1]?.date || '—' }}</span></div></template></div></section><section class="panel"><div class="panel-head"><div><h2>交易明细</h2><p>买卖方向、价格和数量从同一回测结果读取。</p></div></div><div class="panel-body"><div v-if="!list(backtest, 'trades').length" class="empty">暂无交易。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>代码</th><th>方向</th><th>价格</th><th>数量</th><th>入场价</th></tr></thead><tbody><tr v-for="row in list(backtest, 'trades').slice().reverse().slice(0, 30)" :key="`${row.datetime}-${row.code}-${row.price}`"><td>{{ row.datetime || '—' }}</td><td>{{ row.code }}</td><td :class="row.direction === 'long' ? 'good' : 'bad'">{{ row.direction === 'long' ? '买入' : '卖出' }}</td><td>{{ value(row.price) }}</td><td>{{ value(row.volume, 0) }}</td><td>{{ value(row.entry_price) }}</td></tr></tbody></table></div></div></section></section>
      <section v-if="backtest" class="section-grid two validation-secondary-results"><section class="panel"><div class="panel-head"><div><h2>月度收益</h2><p>按回测权益曲线计算，百分比为小数收益转换。</p></div></div><div class="panel-body"><div v-if="!monthly.length" class="empty">暂无月度收益数据。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>月份</th><th>收益</th><th>方向</th></tr></thead><tbody><tr v-for="row in monthly" :key="`${row.year}-${row.month}`"><td>{{ row.year }}-{{ String(row.month).padStart(2, '0') }}</td><td :class="resultClass(row.return_pct)">{{ percent(row.return_pct) }}</td><td>{{ Number(row.return_pct) >= 0 ? '增长' : '回撤' }}</td></tr></tbody></table></div></div></section><section class="panel"><div class="panel-head"><div><h2>回撤曲线</h2><p>{{ drawdown.length }} 个有效点 · 越接近 0 越好。</p></div></div><div class="panel-body chart-panel"><div v-if="!drawdownPath" class="empty">暂无回撤数据。</div><template v-else><svg class="price-chart drawdown-chart" viewBox="0 0 760 240" role="img" aria-label="回测回撤曲线"><line x1="18" y1="30" x2="742" y2="30" class="chart-axis" /><path :d="drawdownPath" class="chart-line chart-line-risk" /></svg><div class="chart-labels"><span>{{ drawdown[0]?.date || '—' }}</span><strong>{{ percent(Math.min(...drawdown.map((item) => Number(item.drawdown_pct)))) }}</strong><span>{{ drawdown[drawdown.length - 1]?.date || '—' }}</span></div></template></div></section></section>
      <section v-else class="empty">先运行一次回测，再查看权益曲线和交易明细。</section>
    </template>

    <template v-else-if="workspace === 'robustness'">
      <section v-if="!robustness" class="empty">运行稳健性验证后显示样本内/样本外和模拟分布。</section><section v-else class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>样本内 / 样本外</h2><p>训练比例 {{ value(robustness.out_of_sample?.comparison?.train_ratio * 100, 0) }}% · 过拟合风险需要结合数据量判断。</p></div><span class="tag" :class="robustness.out_of_sample?.comparison?.overfit_risk === 'low' ? 'good' : 'warn'">{{ robustness.out_of_sample?.comparison?.overfit_risk || '—' }}</span></div><div class="panel-body"><div v-if="robustness.out_of_sample?.error" class="error-box">{{ robustness.out_of_sample.error }}</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>指标</th><th>样本内</th><th>样本外</th><th>衰减</th></tr></thead><tbody><tr v-for="item in [['收益', 'total_return'], ['年化', 'annual_return'], ['最大回撤', 'max_drawdown'], ['夏普', 'sharpe_ratio'], ['胜率', 'win_rate'], ['交易数', 'total_trades']]" :key="item[1]"><td>{{ item[0] }}</td><td>{{ item[1].includes('return') || item[1] === 'max_drawdown' || item[1] === 'win_rate' ? percent(robustness.out_of_sample?.in_sample?.[item[1]]) : value(robustness.out_of_sample?.in_sample?.[item[1]]) }}</td><td>{{ item[1].includes('return') || item[1] === 'max_drawdown' || item[1] === 'win_rate' ? percent(robustness.out_of_sample?.out_of_sample?.[item[1]]) : value(robustness.out_of_sample?.out_of_sample?.[item[1]]) }}</td><td>{{ item[1] === 'sharpe_ratio' ? value(robustness.out_of_sample?.comparison?.sharpe_decay) : '—' }}</td></tr></tbody></table></div></div></section><section class="panel"><div class="panel-head"><div><h2>Monte Carlo</h2><p>对交易序列做重排模拟，不能替代样本外验证。</p></div></div><div class="panel-body"><div v-if="robustness.monte_carlo?.error" class="error-box">{{ robustness.monte_carlo.error }}</div><div v-else class="metric-grid"><div v-for="(item, key) in robustness.monte_carlo" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ typeof item === 'number' ? value(item) : String(item ?? '—') }}</strong></div></div></div></section></section>
    </template>

    <template v-else-if="workspace === 'analysis'">
      <section class="panel"><div class="panel-head"><div><h2>策略比较</h2><p>多策略结果只用于研究，不改变当前组合版本。</p></div><button class="button" :disabled="loading" @click="runComparison"><Play :size="15" />比较</button></div><div class="panel-body"><div class="data-source strategy-picker"><label v-for="item in strategies" :key="String(item.name)"><input v-model="compareSelection" type="checkbox" :value="String(item.name)" />{{ item.label || item.name }}</label></div><div v-if="comparison.length" class="table-scroll"><table class="decision-table"><thead><tr><th>策略</th><th>总收益</th><th>最大回撤</th><th>夏普</th><th>曲线点数</th></tr></thead><tbody><tr v-for="row in comparison" :key="row.strategy"><td>{{ row.strategy }}</td><td :class="resultClass(row.total_return)">{{ percent(row.total_return) }}</td><td class="bad">{{ percent(row.max_drawdown) }}</td><td>{{ value(row.sharpe_ratio) }}</td><td>{{ row.equity_curve?.length || 0 }}</td></tr></tbody></table></div></div></section><section class="section-grid two analysis-cards"><section v-for="name in ['returns', 'trades', 'turnover', 'weekday', 'holding-period', 'attribution']" :key="name" class="panel"><div class="panel-head"><h2>{{ ({ returns: '收益分布', trades: '交易分布', turnover: '换手与成本', weekday: '星期效应', 'holding-period': '持仓周期', attribution: '绩效归因' } as any)[name] }}</h2></div><div class="panel-body"><div v-if="!analysis[name]" class="empty">先运行回测。</div><div v-else-if="analysis[name]?.error" class="error-box">{{ analysis[name]?.error }}</div><template v-else-if="name === 'holding-period'"><div class="metric-grid"><div v-for="(item, key) in analysis[name]?.summary || {}" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ value(item) }}</strong></div></div><div v-if="analysis[name]?.pnl_by_period?.length" class="table-scroll analysis-table"><table class="decision-table"><thead><tr><th>持仓区间</th><th>笔数</th><th>平均盈亏</th><th>胜率</th></tr></thead><tbody><tr v-for="row in analysis[name].pnl_by_period" :key="row.period"><td>{{ row.period }}</td><td>{{ value(row.count, 0) }}</td><td :class="resultClass(row.avg_pnl)">{{ signedPercent(Number(row.avg_pnl) / 100) }}</td><td>{{ value(row.win_rate, 1) }}%</td></tr></tbody></table></div></template><template v-else-if="name === 'attribution'"><div class="metric-grid"><div v-for="(item, key) in analysis[name]?.summary || {}" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ value(item) }}</strong></div></div><div v-if="analysis[name]?.sectors?.length" class="table-scroll analysis-table"><table class="decision-table"><thead><tr><th>行业</th><th>配置</th><th>选股</th><th>交互</th><th>总贡献</th></tr></thead><tbody><tr v-for="row in analysis[name].sectors" :key="row.sector"><td>{{ row.sector }}</td><td>{{ value(row.allocation_effect) }}</td><td>{{ value(row.selection_effect) }}</td><td>{{ value(row.interaction_effect) }}</td><td :class="resultClass(row.total_effect)">{{ value(row.total_effect) }}</td></tr></tbody></table></div></template><div v-else-if="analysis[name]?.stats || analysis[name]?.summary" class="metric-grid"><div v-for="(item, key) in (analysis[name]?.stats || analysis[name]?.summary || {})" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ typeof item === 'number' ? value(item) : String(item ?? '—') }}</strong></div></div><div v-else class="empty">接口没有返回可展示摘要。</div></div></section></section>
    </template>

    <template v-else>
      <section class="panel"><div class="panel-head"><div><h2>组合自动推送资格</h2><p>资格检查和手动研究分离；缺失数据、验证不足或未测试目标都会阻断自动化。</p></div><span v-if="eligibility" class="tag" :class="eligibility.eligible ? 'good' : 'bad'">{{ eligibility.eligible ? '可评估' : '阻断' }}</span></div><div class="panel-body"><div v-if="!portfolios.length" class="empty">先在决策中心创建组合。</div><template v-else><div class="field"><label for="portfolio-select">组合</label><select id="portfolio-select" v-model="selected" class="field-select" @change="checkPortfolio"><option v-for="item in portfolios" :key="item.id" :value="item">{{ item.name }} · {{ item.market }}</option></select></div><div class="data-source" style="margin-top:14px"><span>当前版本：{{ selected?.version?.version_no || '未建立' }}</span><span>配置 hash：{{ selected?.version?.config_hash?.slice(0, 12) || '—' }}</span></div><div class="form-actions"><button class="button" :disabled="loading || !selected" @click="previewPortfolio"><Play :size="15" />生成真实预览</button><button class="button primary" :disabled="loading || !selected" @click="checkPortfolio"><RefreshCw :size="15" />运行资格检查</button></div></template></div></section><section class="section-grid two" style="margin-top:18px"><section class="panel"><div class="panel-head"><div><h2>历史验证</h2><p>窗口和成本版本必须可追溯。</p></div><span v-if="validation" class="tag" :class="validation.passed ? 'good' : 'bad'">{{ validation.passed ? '通过' : '未通过' }}</span></div><div class="panel-body"><div v-if="!validation" class="empty">等待资格检查。</div><div v-else class="check-list"><div class="check-row"><div class="check-copy"><strong>样本外窗口</strong><span>{{ validation.windows?.length || 0 }} 个独立窗口</span></div><CheckCircle2 v-if="validation.passed" :size="18" class="good" /><CircleAlert v-else :size="18" class="bad" /></div><div class="check-row"><div class="check-copy"><strong>成本模型</strong><span>{{ validation.cost_model_version || '—' }}</span></div><span class="tag warn">需复核</span></div><div v-for="reason in validation.reasons || []" :key="reason" class="check-row"><span>{{ reason }}</span><CircleAlert :size="17" class="bad" /></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>资格阻断原因</h2><p>资格是版本、市场、健康和通知目标的交集。</p></div></div><div class="panel-body"><div v-if="!eligibility" class="empty">等待检查。</div><div v-else class="check-list"><div v-for="(valueItem, key) in eligibility.checks || {}" :key="String(key)" class="check-row"><span>{{ ({ preview_ok: '真实预览', validation_ok: '历史验证', health_ok: '数据健康', adapter_ok: '盘中能力', target_ok: '通知目标' } as any)[key] || key }}</span><span class="tag" :class="valueItem ? 'good' : 'bad'">{{ valueItem ? '通过' : '阻断' }}</span></div><div v-for="reason in eligibility.reasons || []" :key="reason" class="error-box">{{ reason }}</div></div></div></section></section>
    </template>
    </template>
  </section>
</template>

<style scoped>
.validation-advanced { margin-top:16px; border-top:1px solid var(--color-line); }
.validation-advanced summary { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:48px; color:var(--color-ink); font-size:13px; font-weight:650; cursor:pointer; }
.validation-advanced summary span { color:var(--color-ink-faint); font-size:11px; font-weight:400; text-align:right; }
.validation-advanced[open] summary { margin-bottom:14px; }
@media (max-width:767px) {
  .validation-advanced summary { align-items:flex-start; flex-direction:column; justify-content:center; gap:3px; }
  .validation-advanced summary span { text-align:left; }
}
</style>
