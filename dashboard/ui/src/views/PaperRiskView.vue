<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Ban, BarChart3, Check, CircleAlert, Download, Pause, Play, RefreshCw, RotateCcw, Save, ShieldAlert, ShieldCheck, Square, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import BrokerDisableGuard from '../components/guards/BrokerDisableGuard.vue'
import { useV2ContextStore } from '../stores/v2Context'

type Row = Record<string, any>
type PaperTab = 'orders' | 'positions' | 'performance' | 'risk'

const tab = ref<PaperTab>('orders')
const status = ref<Row | null>(null)
const positions = ref<Row[]>([])
const orders = ref<Row[]>([])
const trades = ref<Row[]>([])
const performance = ref<Row | null>(null)
const tradeStats = ref<Row | null>(null)
const dailyPerformance = ref<Row[]>([])
const riskEvents = ref<Row[]>([])
const riskRules = ref<Row>({})
const strategies = ref<Row[]>([])
const loading = ref(false)
const hasLoaded = ref(false)
const statusAvailable = ref(false)
const statusError = ref('')
const loadError = ref('')
const saving = ref(false)
const actionFeedback = ref('')
const actionError = ref('')
const startReview = ref(false)
const resetReview = ref(false)
const pendingCancel = ref('')
const pendingClose = ref('')
const closeVolume = ref(0)
const orderReview = ref<Row | null>(null)
const stopDrafts = ref<Record<string, { stop_loss_price: number | null; take_profit_price: number | null }>>({})
const startForm = ref({ strategy: 'dual_ma', codes: '000001', interval: 30, cash: 50000, enable_risk: true })
const orderForm = ref({ code: '', direction: 'buy', order_type: 'market', price: null as number | null, volume: 100, strategy_name: 'manual', signal_reason: '人工确认的模拟盘订单' })
const v2Context = useV2ContextStore()
const riskForm = ref({ max_position_pct: 0.2, max_positions: 10, max_drawdown: 0.1, max_daily_loss: 0.03 })

const running = computed(() => Boolean(status.value?.running))
const runningStateKnown = computed(() => statusAvailable.value && typeof status.value?.running === 'boolean')
const reconciliationRequired = computed(() => Boolean(status.value?.reconciliation_required || status.value?.reconciliationRequired || status.value?.reconciliations?.length || ['reconciling', 'reconciliation_blocked', 'halted', 'halt_requested', 'blocked', 'failed'].includes(String(status.value?.status || '').toLowerCase())))
const canOperate = computed(() => statusAvailable.value && runningStateKnown.value && !reconciliationRequired.value && !v2Context.controlsBlocked)

const initialLoading = computed(() => loading.value && !hasLoaded.value)
const statusDisplay = computed(() => {
  if (!statusAvailable.value) return '状态不可确认'
  if (!runningStateKnown.value) return '状态未提供'
  return running.value ? '运行中' : '未运行'
})
const executionRunId = computed(() => status.value?.execution_run_id ?? status.value?.executionRunId ?? status.value?.config?.execution_run_id ?? null)
const accountId = computed(() => status.value?.account_id ?? status.value?.accountId ?? status.value?.account?.id ?? status.value?.config?.account_id ?? null)
const accountLabel = computed(() => status.value?.account?.name ?? status.value?.account_name ?? status.value?.config?.account_name ?? null)
const finalRiskStatus = computed(() => status.value?.final_risk_status ?? status.value?.risk_status ?? status.value?.risk?.final_status ?? null)
const reconciliationStatus = computed(() => status.value?.reconciliation_status ?? status.value?.reconciliation?.status ?? null)
const recoveryStatus = computed(() => status.value?.recovery_status ?? status.value?.recovery?.status ?? null)
const workerStatus = computed(() => status.value?.worker_status ?? status.value?.worker?.status ?? null)
const compatibilityMode = computed(() => !executionRunId.value)
const strategyOptions = computed(() => strategies.value.length ? strategies.value : [{ name: 'dual_ma', label: '双均线' }])
const metricRows = computed(() => {
  const item = performance.value || tradeStats.value || {}
  return [['总权益', item.total_equity ?? status.value?.equity], ['总收益', item.total_return], ['最大回撤', item.max_drawdown], ['夏普', item.sharpe_ratio], ['胜率', item.win_rate], ['交易次数', item.total_trades ?? tradeStats.value?.total_trades]]
})

function payloadData(value: any): any {
  return value?.data ?? value
}

function number(value: unknown, digits = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function percent(value: unknown) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  const numeric = Number(value)
  const percentage = Math.abs(numeric) <= 1 ? numeric * 100 : numeric
  return `${percentage.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })}%`
}

function stateLabel(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback
  const labels: Record<string, string> = {
    ready: '就绪', running: '运行中', paused: '已暂停', stopping: '停止请求中', halted: '已停止', blocked: '已阻断', passed: '通过', failed: '失败', pending: '等待中', reconciling: '对账中', completed: '已完成', recovered: '已恢复', unavailable: '不可用',
  }
  const key = String(value).toLowerCase()
  return labels[key] || String(value)
}

function stateTone(value: unknown) {
  const text = String(value || '').toLowerCase()
  return ['ready', 'running', 'passed', 'completed', 'recovered', 'success'].some((item) => text.includes(item)) ? 'good' : ['failed', 'blocked', 'error', 'halted'].some((item) => text.includes(item)) ? 'bad' : 'warn'
}

function strategyContext() {
  return status.value?.config?.strategy || status.value?.strategy || '未提供'
}

function statusClass(value: unknown) {
  return stateTone(value)
}

function requireOperableStatus() {
  if (canOperate.value) return true
  actionError.value = '当前 paper 运行状态不可确认，已禁用此操作；请刷新状态后重试。'
  return false
}

function setPendingFeedback(text: string) {
  actionError.value = ''
  actionFeedback.value = text
}

async function load() {
  loading.value = true
  const results = await Promise.allSettled([
    api.paperStatus(), api.paperPositions(), api.paperOrders(), api.paperRiskEvents(), api.paperRiskRules(), api.paperPerformance(), api.paperDailyPerformance(), api.paperTrades(), api.paperTradeStats(), api.strategies(),
  ])
  const statusResult = results[0]
  const rawStatus = statusResult.status === 'fulfilled' ? statusResult.value as Row : null
  const statusPayload = statusResult.status === 'fulfilled' ? payloadData(rawStatus) : null
  if (statusResult.status === 'fulfilled' && rawStatus?.success !== false && statusPayload && typeof statusPayload === 'object' && !Array.isArray(statusPayload)) {
    status.value = statusPayload as Row
    statusAvailable.value = true
    statusError.value = ''
  } else {
    statusAvailable.value = false
    statusError.value = 'paper 运行状态暂不可确认；已保留最后一次有效状态，依赖状态的操作已禁用。'
  }
  const currentContext = v2Context.context
  void v2Context.load(currentContext ? currentContext.account_id : String(statusPayload?.account_id || 'paper-default'), currentContext ? currentContext.workspace_id : String(statusPayload?.workspace_id || 'default'))


  const value = <T>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
  const positionPayload = payloadData(value<Row>(1))
  const orderPayload = payloadData(value<Row>(2))
  const eventPayload = payloadData(value<Row>(3))
  const rulesPayload = payloadData(value<Row>(4))
  const performancePayload = payloadData(value<Row>(5))
  const dailyPayload = payloadData(value<Row>(6))
  const tradePayload = payloadData(value<Row>(7))
  const statsPayload = payloadData(value<Row>(8))
  positions.value = Array.isArray(positionPayload) ? positionPayload : Array.isArray(positionPayload?.positions) ? positionPayload.positions : []
  orders.value = Array.isArray(orderPayload) ? orderPayload : Array.isArray(orderPayload?.items) ? orderPayload.items : []
  riskEvents.value = Array.isArray(eventPayload) ? eventPayload : []
  riskRules.value = rulesPayload && typeof rulesPayload === 'object' ? rulesPayload : {}
  performance.value = performancePayload && typeof performancePayload === 'object' ? performancePayload : null
  dailyPerformance.value = Array.isArray(dailyPayload) ? dailyPayload : []
  trades.value = Array.isArray(tradePayload) ? tradePayload : Array.isArray(tradePayload?.items) ? tradePayload.items : []
  tradeStats.value = statsPayload && typeof statsPayload === 'object' ? statsPayload : null
  const strategyPayload = value<Row[]>(9)
  strategies.value = Array.isArray(strategyPayload) ? strategyPayload as Row[] : []
  if (riskRules.value && Object.keys(riskRules.value).length) {
    riskForm.value = { ...riskForm.value, ...riskRules.value }
  }
  for (const position of positions.value) {
    stopDrafts.value[position.code] = { stop_loss_price: position.stop_loss_price ?? null, take_profit_price: position.take_profit_price ?? null }
  }
  const rejected = results.filter((item) => item.status === 'rejected').length
  loadError.value = rejected > 0 ? '部分模拟盘数据暂不可用；页面保留已返回内容。' : ''
  hasLoaded.value = true
  loading.value = false
}

async function startPaper() {
  if (!requireOperableStatus()) return
  saving.value = true
  try {
    await api.startPaper({ ...startForm.value, codes: startForm.value.codes.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean) })
    setPendingFeedback('已提交 paper 启动请求；等待 worker/模拟引擎状态确认')
    startReview.value = false
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘启动失败'
  } finally {
    saving.value = false
  }
}

async function stopPaper() {
  if (!requireOperableStatus()) return
  saving.value = true
  try {
    await api.stopPaper()
    setPendingFeedback('已提交 paper 停止请求；等待 worker 状态确认')
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘停止失败'
  } finally {
    saving.value = false
  }
}

async function resetPaper() {
  if (!requireOperableStatus()) return
  if (!resetReview.value) {
    resetReview.value = true
    return
  }
  saving.value = true
  try {
    await api.resetPaper()
    setPendingFeedback('已提交 paper 重置请求；等待状态确认，历史订单数据库不被伪造清空')
    resetReview.value = false
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘重置失败'
  } finally {
    saving.value = false
  }
}

function reviewOrder() {
  if (!requireOperableStatus()) return
  if (!orderForm.value.code.trim() || orderForm.value.volume < 100 || orderForm.value.volume % 100 !== 0 || (orderForm.value.order_type !== 'market' && !(Number(orderForm.value.price) > 0))) {
    actionError.value = '请填写代码、100 的整数倍数量；非市价单必须填写价格'
    return
  }
  orderReview.value = { ...orderForm.value }
}

async function submitOrder() {
  if (!orderReview.value || !requireOperableStatus()) return
  saving.value = true
  try {
    await api.createPaperOrder(orderReview.value)
    setPendingFeedback('已提交 paper 订单，等待 worker/撮合状态；不代表已成交')
    orderReview.value = null
    orderForm.value = { ...orderForm.value, code: '', price: null }
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘订单创建失败'
  } finally {
    saving.value = false
  }
}

async function cancelOrder(order: Row) {
  if (!requireOperableStatus()) return
  if (pendingCancel.value !== String(order.order_id || order.id)) {
    pendingCancel.value = String(order.order_id || order.id)
    return
  }
  saving.value = true
  try {
    await api.cancelPaperOrder(pendingCancel.value)
    setPendingFeedback('已提交 paper 撤单请求，等待 worker 状态确认')
    pendingCancel.value = ''
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '撤销模拟盘订单失败'
  } finally {
    saving.value = false
  }
}

async function savePositionRisk(code: string) {
  if (!requireOperableStatus()) return
  saving.value = true
  try {
    await api.updatePaperPositionRisk(code, stopDrafts.value[code] || {})
    setPendingFeedback(`${code} 的止损止盈已提交，等待 worker 状态确认`)
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '止损止盈更新失败'
  } finally {
    saving.value = false
  }
}

async function closePosition(position: Row) {
  if (!requireOperableStatus()) return
  if (pendingClose.value !== String(position.code)) {
    pendingClose.value = String(position.code)
    closeVolume.value = Number(position.volume || 0)
    return
  }
  if (!closeVolume.value || closeVolume.value > Number(position.volume) || closeVolume.value % 100 !== 0) {
    actionError.value = '平仓数量必须是不超过持仓的 100 的整数倍'
    return
  }
  saving.value = true
  try {
    await api.closePaperPosition(String(position.code), closeVolume.value)
    setPendingFeedback(`已提交 ${position.code} 的 paper 平仓请求，等待 worker/撮合状态`)
    pendingClose.value = ''
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘平仓失败'
  } finally {
    saving.value = false
  }
}

async function saveRiskRules() {
  if (!requireOperableStatus()) return
  saving.value = true
  try {
    await api.put('/api/paper/risk/rules', riskForm.value)
    setPendingFeedback('已提交 paper 风控规则更新，等待 worker 状态确认')
    await load()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟盘风控规则更新失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <BrokerDisableGuard />
  <section>
    <div class="page-head"><div><RouterLink to="/app/portfolio-risk" class="muted small"><ArrowLeft :size="14" />组合工作区</RouterLink><h1>模拟盘与风控执行</h1><p>这里是 paper 环境的状态与操作工作区。旧模拟盘 API 保留兼容；页面不会把 legacy 返回值解释为 V2 ExecutionRun，也不会调用 Broker。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button></div>
    <div v-if="initialLoading" class="info-box" role="status" aria-live="polite">正在加载 paper 状态与数据…</div>
    <div v-if="statusError" class="error-box" role="alert"><CircleAlert :size="16" />{{ statusError }}</div>
    <div v-if="reconciliationRequired" class="error-box" role="alert"><CircleAlert :size="16" />当前 Paper 运行需要先完成对账或恢复确认；所有执行操作已禁用。</div>
    <div v-if="loadError" class="error-box" role="alert"><CircleAlert :size="16" />{{ loadError }}</div>
    <div v-if="actionError" class="error-box" role="alert"><CircleAlert :size="16" />{{ actionError }}</div>
    <div v-if="saving" class="info-box" role="status" aria-live="polite">正在提交 paper 操作，请等待 worker/模拟引擎确认；不代表已成交。</div>
    <div v-if="actionFeedback" class="info-box" role="status" aria-live="polite"><Check :size="16" />{{ actionFeedback }}</div>
    <section class="panel execution-context-panel" aria-labelledby="paper-execution-context-title" :aria-busy="loading"><div class="panel-head"><div><h2 id="paper-execution-context-title">执行上下文与安全边界</h2><p>状态仅来自 `/api/paper/status` 及现有兼容接口；缺少 V2 字段时明确显示未绑定，不填充推测值。</p></div><span class="tag" :class="statusAvailable ? 'good' : 'bad'"><ShieldCheck :size="14" />{{ statusAvailable ? 'Paper 环境' : '状态不可确认' }}</span></div><div class="panel-body"><div class="context-grid"><div class="context-item"><span>环境</span><strong>paper</strong><small>模拟适配器；Live 不可执行</small></div><div class="context-item"><span>运行状态</span><strong>{{ statusDisplay }}</strong><small>{{ statusAvailable ? strategyContext() : '状态不可确认，操作已禁用' }}</small></div><div class="context-item"><span>ExecutionRun</span><strong>{{ executionRunId || '未绑定' }}</strong><small>{{ compatibilityMode ? '兼容模式：legacy status 未提供 V2 run' : '后端返回的运行标识' }}</small></div><div class="context-item"><span>账户</span><strong>{{ accountLabel || accountId || '未绑定' }}</strong><small>{{ accountId ? `账户 ID：${accountId}` : '后端未提供账户上下文' }}</small></div></div><div class="state-list" aria-label="执行状态"><div class="state-row"><span><ShieldAlert :size="15" />最终风控</span><span class="tag" :class="stateTone(finalRiskStatus)">{{ stateLabel(finalRiskStatus, '未提供') }}</span></div><div class="state-row"><span><RefreshCw :size="15" />对账</span><span class="tag" :class="stateTone(reconciliationStatus)">{{ stateLabel(reconciliationStatus, '未提供') }}</span></div><div class="state-row"><span><RotateCcw :size="15" />恢复</span><span class="tag" :class="stateTone(recoveryStatus)">{{ stateLabel(recoveryStatus, '未提供') }}</span></div><div class="state-row"><span><Play :size="15" />Worker</span><span class="tag" :class="stateTone(workerStatus)">{{ stateLabel(workerStatus, '未提供') }}</span></div></div><div class="execution-boundary" role="status"><Ban :size="16" /><span><strong>Live 已禁用</strong>：当前没有 Live permit、Broker 连接或真实执行权。下面的停止、订单、平仓和风控操作都只保留现有 paper API 路径。</span></div></div></section>
    <section class="panel paper-control-panel" :aria-busy="loading"><div class="panel-head"><div><h2>Paper 运行控制</h2><p>启动、停止和重置会提交 legacy paper 命令；点击后仍需等待后端 worker/模拟引擎状态确认。</p></div><span class="tag" :class="runningStateKnown ? (running ? 'good' : 'warn') : 'bad'">{{ statusDisplay }}</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="paper-strategy">策略</label><select id="paper-strategy" v-model="startForm.strategy" :disabled="running || !canOperate"><option v-for="strategy in strategyOptions" :key="String(strategy.name)" :value="strategy.name">{{ strategy.label || strategy.name }}</option></select></div><div class="field"><label for="paper-codes">股票代码</label><input id="paper-codes" v-model="startForm.codes" :disabled="running || !canOperate" placeholder="000001,600519" /></div><div class="field"><label for="paper-interval">轮询秒数</label><input id="paper-interval" v-model.number="startForm.interval" type="number" min="5" :disabled="running || !canOperate" /></div><div class="field"><label for="paper-cash">初始资金</label><input id="paper-cash" v-model.number="startForm.cash" type="number" min="1" :disabled="running || !canOperate" /></div></div><label class="check-control"><input v-model="startForm.enable_risk" type="checkbox" :disabled="running || !canOperate" />启动 legacy paper 风控</label><div class="form-actions"><button v-if="canOperate && !running" class="button primary" type="button" :disabled="saving" @click="startReview = !startReview"><Play :size="15" />提交启动请求</button><button v-else-if="canOperate" class="button" type="button" :disabled="saving" @click="stopPaper"><Pause :size="15" />提交停止请求</button><button v-else class="button" type="button" disabled title="paper 状态不可确认"><CircleAlert :size="15" />状态不可确认</button><button class="button" type="button" disabled title="V2 暂停命令尚未由后端提供"><Pause :size="15" />暂停（未接入）</button><button class="button danger" type="button" :disabled="saving || !canOperate" @click="resetPaper"><RotateCcw :size="15" />{{ resetReview ? '再次确认重置' : '重置状态' }}</button><button v-if="resetReview" class="button ghost" type="button" @click="resetReview = false"><X :size="15" />取消</button></div><div v-if="startReview" class="inline-confirm"><span>确认提交 {{ startForm.strategy }} 的 paper 启动请求？提交后等待 worker/模拟引擎状态，不代表已成交，也不会连接真实账户。</span><button class="button primary" type="button" :disabled="saving || !canOperate" @click="startPaper"><Check :size="15" />确认提交</button><button class="button ghost" type="button" @click="startReview = false">取消</button></div></div></section>
    <div class="summary-strip"><div class="summary-item"><span>Paper 运行状态</span><strong>{{ statusDisplay }}</strong><small>{{ statusAvailable ? strategyContext() : '状态不可确认' }}</small></div><div class="summary-item"><span>总权益</span><strong>{{ number(status?.equity ?? performance?.total_equity) }}</strong><small>legacy paper 快照</small></div><div class="summary-item"><span>持仓</span><strong>{{ positions.length }}</strong><small>{{ number(status?.cash) }} 可用现金</small></div><div class="summary-item"><span>交易</span><strong>{{ tradeStats?.total_trades ?? status?.trade_count ?? '—' }}</strong><small>当前历史范围</small></div></div>
    <nav class="workspace-tabs" role="tablist" aria-label="模拟盘工作区"><button id="paper-tab-orders" role="tab" :aria-selected="tab === 'orders'" :tabindex="tab === 'orders' ? 0 : -1" type="button" :class="{ active: tab === 'orders' }" @click="tab = 'orders'"><Play :size="15" />订单</button><button id="paper-tab-positions" role="tab" :aria-selected="tab === 'positions'" :tabindex="tab === 'positions' ? 0 : -1" type="button" :class="{ active: tab === 'positions' }" @click="tab = 'positions'"><ShieldCheck :size="15" />持仓</button><button id="paper-tab-performance" role="tab" :aria-selected="tab === 'performance'" :tabindex="tab === 'performance' ? 0 : -1" type="button" :class="{ active: tab === 'performance' }" @click="tab = 'performance'"><BarChart3 :size="15" />绩效</button><button id="paper-tab-risk" role="tab" :aria-selected="tab === 'risk'" :tabindex="tab === 'risk' ? 0 : -1" type="button" :class="{ active: tab === 'risk' }" @click="tab = 'risk'"><ShieldAlert :size="15" />风控</button></nav>

    <template v-if="tab === 'orders'"><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>提交 Paper 订单意图</h2><p>订单只写入现有 `/api/paper/orders` 兼容路径；提交后等待 worker/撮合状态，不代表已成交。</p></div><ShieldCheck :size="18" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="paper-order-code">股票代码</label><input id="paper-order-code" v-model="orderForm.code" placeholder="600519" /></div><div class="field"><label for="paper-order-direction">方向</label><select id="paper-order-direction" v-model="orderForm.direction"><option value="buy">买入</option><option value="sell">卖出</option></select></div><div class="field"><label for="paper-order-type">类型</label><select id="paper-order-type" v-model="orderForm.order_type"><option value="market">市价</option><option value="limit">限价</option><option value="stop_loss">止损</option><option value="take_profit">止盈</option></select></div><div class="field"><label for="paper-order-price">价格</label><input id="paper-order-price" v-model.number="orderForm.price" type="number" min="0" step="0.001" :disabled="orderForm.order_type === 'market'" /></div><div class="field"><label for="paper-order-volume">数量</label><input id="paper-order-volume" v-model.number="orderForm.volume" type="number" min="100" step="100" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="saving || !canOperate" @click="reviewOrder"><Play :size="15" />生成提交预览</button></div><div v-if="orderReview" class="inline-confirm"><span>{{ orderReview.direction === 'buy' ? '买入' : '卖出' }} {{ orderReview.code }} {{ orderReview.volume }} 股 · {{ orderReview.order_type }} {{ orderReview.price || '市价' }}</span><button class="button primary" type="button" :disabled="saving || !canOperate" @click="submitOrder"><Check :size="15" />提交并等待 worker</button><button class="button ghost" type="button" @click="orderReview = null">取消</button></div></div></section><section class="panel"><div class="panel-head"><div><h2>待处理订单</h2><p>撤单需要再次确认；订单状态以模拟盘服务返回为准。</p></div><span class="tag">{{ orders.length }} 条</span></div><div class="panel-body"><div v-if="!orders.length" class="empty">暂无待处理订单。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>标的</th><th>方向</th><th>类型</th><th>数量</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="order in orders" :key="order.order_id || order.id"><td class="symbol">{{ order.code }}</td><td :class="order.direction === 'buy' ? 'good' : 'bad'">{{ order.direction === 'buy' ? '买入' : '卖出' }}</td><td>{{ order.order_type || '—' }}</td><td>{{ order.volume }}</td><td><span class="tag" :class="statusClass(order.status)">{{ order.status || 'pending' }}</span></td><td><button class="button danger compact-button" type="button" :disabled="saving || !canOperate" @click="cancelOrder(order)"><Ban :size="14" />{{ pendingCancel === String(order.order_id || order.id) ? '再次确认' : '撤销' }}</button><button v-if="pendingCancel === String(order.order_id || order.id)" class="button ghost compact-button" type="button" @click="pendingCancel = ''">取消</button></td></tr></tbody></table></div></div></section></div></template>

    <template v-else-if="tab === 'positions'"><section class="panel"><div class="panel-head"><div><h2>Paper 持仓与退出</h2><p>止损、止盈和平仓只创建 paper 动作；提交后等待 worker/撮合状态，不代表已成交。</p></div><span class="tag">{{ positions.length }} 个标的</span></div><div class="panel-body"><div v-if="!positions.length" class="empty">暂无模拟盘持仓。</div><div v-else class="table-scroll"><table class="decision-table paper-position-table"><thead><tr><th>标的</th><th>数量</th><th>成本 / 现价</th><th>市值</th><th>盈亏</th><th>止损 / 止盈</th><th>操作</th></tr></thead><tbody><tr v-for="position in positions" :key="position.code"><td class="symbol">{{ position.code }}</td><td>{{ position.volume }}</td><td>{{ number(position.avg_price) }} / {{ number(position.current_price) }}</td><td>{{ number(position.market_value) }}</td><td :class="Number(position.unrealized_pnl) >= 0 ? 'good' : 'bad'">{{ number(position.unrealized_pnl) }}<small>{{ percent(position.unrealized_pnl_pct) }}</small></td><td><div class="mini-fields"><input v-model.number="stopDrafts[position.code].stop_loss_price" type="number" step="0.01" placeholder="止损" /><input v-model.number="stopDrafts[position.code].take_profit_price" type="number" step="0.01" placeholder="止盈" /></div><button class="button ghost compact-button" type="button" :disabled="saving || !canOperate" @click="savePositionRisk(position.code)"><Save :size="13" />保存</button></td><td><button class="button danger compact-button" type="button" :disabled="saving || !canOperate" @click="closePosition(position)"><Square :size="13" />{{ pendingClose === String(position.code) ? '再次确认平仓' : '平仓' }}</button><div v-if="pendingClose === String(position.code)" class="inline-close"><input v-model.number="closeVolume" type="number" min="100" step="100" :max="position.volume" aria-label="平仓数量" /><button class="button ghost compact-button" type="button" @click="pendingClose = ''">取消</button></div></td></tr></tbody></table></div></div></section></template>

    <template v-else-if="tab === 'performance'"><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>绩效指标</h2><p>没有历史数据时显示为空，不把 0 当作“已运行”。</p></div><Download :size="18" class="faint" /></div><div class="panel-body"><div class="metric-grid"><div v-for="row in metricRows" :key="String(row[0])" class="metric-cell"><span>{{ row[0] }}</span><strong>{{ row[0] === '胜率' || row[0] === '最大回撤' || row[0] === '总收益' ? percent(row[1]) : number(row[1]) }}</strong></div></div><div class="form-actions"><a class="button ghost" href="/api/paper/trades-v2/export?format=csv" download><Download :size="15" />导出 CSV</a><a class="button ghost" href="/api/paper/trades-v2/export?format=json" download><Download :size="15" />导出 JSON</a></div></div></section><section class="panel"><div class="panel-head"><div><h2>每日绩效</h2><p>最近 60 天的权益和回撤记录。</p></div></div><div class="panel-body"><div v-if="!dailyPerformance.length" class="empty">暂无每日绩效。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>权益</th><th>日收益</th><th>累计收益</th><th>回撤</th></tr></thead><tbody><tr v-for="row in dailyPerformance.slice(-30).reverse()" :key="row.date"><td>{{ row.date }}</td><td>{{ number(row.total_equity) }}</td><td :class="Number(row.daily_return) >= 0 ? 'good' : 'bad'">{{ percent(row.daily_return) }}</td><td>{{ percent(row.cumulative_return) }}</td><td class="bad">{{ percent(row.max_drawdown) }}</td></tr></tbody></table></div></div></section></div><section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>交易历史</h2><p>成交记录可按后端返回的策略和信号原因追溯。</p></div></div><div class="panel-body"><div v-if="!trades.length" class="empty">暂无成交历史。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>标的</th><th>方向</th><th>价格 / 数量</th><th>盈亏</th><th>策略</th></tr></thead><tbody><tr v-for="trade in trades" :key="trade.trade_id || trade.order_id"><td>{{ trade.created_at || '—' }}</td><td class="symbol">{{ trade.code }}</td><td>{{ trade.direction === 'buy' ? '买入' : '卖出' }}</td><td>{{ number(trade.price) }} / {{ trade.volume }}</td><td :class="Number(trade.profit) >= 0 ? 'good' : 'bad'">{{ number(trade.profit) }}</td><td>{{ trade.strategy_name || '—' }}</td></tr></tbody></table></div></div></section></template>

    <template v-else><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>最终风控状态与规则</h2><p>规则编辑保留 legacy API；最终 RiskGate 状态仅显示后端实际提供的字段，不在前端推断。</p></div><ShieldAlert :size="18" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label>单票上限</label><input v-model.number="riskForm.max_position_pct" type="number" min="0" max="1" step="0.01" /></div><div class="field"><label>最大持仓数</label><input v-model.number="riskForm.max_positions" type="number" min="1" /></div><div class="field"><label>最大回撤</label><input v-model.number="riskForm.max_drawdown" type="number" min="0" max="1" step="0.01" /></div><div class="field"><label>单日最大损失</label><input v-model.number="riskForm.max_daily_loss" type="number" min="0" max="1" step="0.01" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="saving || !canOperate" @click="saveRiskRules"><Save :size="15" />提交风控规则并等待状态</button></div><pre class="result-code" style="margin-top:16px">{{ JSON.stringify(riskRules, null, 2) }}</pre></div></section><section class="panel"><div class="panel-head"><div><h2>对账、恢复与风险事件</h2><p>对账和恢复状态以 status 返回为准；当前 legacy API 未提供时显示未提供。</p></div><span class="tag">{{ riskEvents.length }} 条</span></div><div class="panel-body"><div class="state-list"><div class="state-row"><span><ShieldAlert :size="15" />最终 RiskGate</span><span class="tag" :class="stateTone(finalRiskStatus)">{{ stateLabel(finalRiskStatus, '未提供') }}</span></div><div class="state-row"><span><RefreshCw :size="15" />对账</span><span class="tag" :class="stateTone(reconciliationStatus)">{{ stateLabel(reconciliationStatus, '未提供') }}</span></div><div class="state-row"><span><RotateCcw :size="15" />恢复</span><span class="tag" :class="stateTone(recoveryStatus)">{{ stateLabel(recoveryStatus, '未提供') }}</span></div></div><div v-if="!riskEvents.length" class="empty">暂无风险事件；这不等于风控已通过。</div><div v-else class="check-list"><div v-for="(event, index) in riskEvents" :key="String(event.id || index)" class="check-row"><div class="check-copy"><strong>{{ event.event_type || event.type || '风险事件' }}</strong><span>{{ event.message || event.reason || event.created_at || '—' }}</span></div><span class="tag warn">记录</span></div></div></div></section></div></template>
  </section>
</template>

<style scoped>
.execution-context-panel { margin-bottom: 18px; }
.context-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.context-item { min-width: 0; padding: 12px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface-muted); }
.context-item span, .context-item small { display: block; color: var(--ink-soft); font-size: 12px; }
.context-item strong { display: block; margin: 5px 0; overflow-wrap: anywhere; }
.context-item small { color: var(--ink-faint); line-height: 1.45; }
.state-list { display: grid; gap: 8px; margin-top: 16px; }
.state-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 36px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.state-row > span:first-child { display: inline-flex; align-items: center; gap: 7px; color: var(--ink-soft); font-size: 12px; }
.execution-boundary { display: flex; align-items: flex-start; gap: 8px; margin-top: 16px; padding: 11px 12px; border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line)); background: var(--surface-muted); color: var(--ink-soft); font-size: 12px; line-height: 1.5; }
.execution-boundary svg { flex: 0 0 auto; color: var(--warn); margin-top: 2px; }
.execution-boundary strong { color: var(--ink); }
@media (max-width: 760px) { .context-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .context-grid { grid-template-columns: 1fr; } .state-row { align-items: flex-start; } }
</style>
