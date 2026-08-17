<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Ban, BarChart3, Check, CircleAlert, Download, Pause, Play, RefreshCw, RotateCcw, Save, ShieldAlert, ShieldCheck, Square, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'

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
const saving = ref(false)
const message = ref('')
const startReview = ref(false)
const resetReview = ref(false)
const pendingCancel = ref('')
const pendingClose = ref('')
const closeVolume = ref(0)
const orderReview = ref<Row | null>(null)
const stopDrafts = ref<Record<string, { stop_loss_price: number | null; take_profit_price: number | null }>>({})
const startForm = ref({ strategy: 'dual_ma', codes: '000001', interval: 30, cash: 50000, enable_risk: true })
const orderForm = ref({ code: '', direction: 'buy', order_type: 'market', price: null as number | null, volume: 100, strategy_name: 'manual', signal_reason: '人工确认的模拟盘订单' })
const riskForm = ref({ max_position_pct: 0.2, max_positions: 10, max_drawdown: 0.1, max_daily_loss: 0.03 })

const running = computed(() => Boolean(status.value?.running))
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

function statusClass(value: unknown) {
  const text = String(value || '').toLowerCase()
  return ['filled', 'completed', 'success', 'running'].some((item) => text.includes(item)) ? 'good' : ['cancel', 'error', 'failed', 'rejected'].some((item) => text.includes(item)) ? 'bad' : 'warn'
}

async function load() {
  loading.value = true
  message.value = ''
  const results = await Promise.allSettled([
    api.paperStatus(), api.paperPositions(), api.paperOrders(), api.paperRiskEvents(), api.paperRiskRules(), api.paperPerformance(), api.paperDailyPerformance(), api.paperTrades(), api.paperTradeStats(), api.strategies(),
  ])
  const value = <T>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
  status.value = value<Row>(0)
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
  if (results.filter((item) => item.status === 'rejected').length > 0) message.value = '部分模拟盘数据暂不可用；页面保留已返回内容。'
  loading.value = false
}

async function startPaper() {
  saving.value = true
  try {
    await api.startPaper({ ...startForm.value, codes: startForm.value.codes.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean) })
    message.value = '模拟盘已启动；这是本地模拟引擎，不是 Broker 连接'
    startReview.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘启动失败'
  } finally {
    saving.value = false
  }
}

async function stopPaper() {
  saving.value = true
  try {
    await api.stopPaper()
    message.value = '模拟盘已停止'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘停止失败'
  } finally {
    saving.value = false
  }
}

async function resetPaper() {
  if (!resetReview.value) {
    resetReview.value = true
    return
  }
  saving.value = true
  try {
    await api.resetPaper()
    message.value = '模拟盘状态已重置；历史订单数据库不被伪造清空'
    resetReview.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘重置失败'
  } finally {
    saving.value = false
  }
}

function reviewOrder() {
  if (!orderForm.value.code.trim() || orderForm.value.volume < 100 || orderForm.value.volume % 100 !== 0 || (orderForm.value.order_type !== 'market' && !(Number(orderForm.value.price) > 0))) {
    message.value = '请填写代码、100 的整数倍数量；非市价单必须填写价格'
    return
  }
  orderReview.value = { ...orderForm.value }
}

async function submitOrder() {
  if (!orderReview.value) return
  saving.value = true
  try {
    await api.createPaperOrder(orderReview.value)
    message.value = '模拟盘订单已创建，等待撮合'
    orderReview.value = null
    orderForm.value = { ...orderForm.value, code: '', price: null }
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘订单创建失败'
  } finally {
    saving.value = false
  }
}

async function cancelOrder(order: Row) {
  if (pendingCancel.value !== String(order.order_id || order.id)) {
    pendingCancel.value = String(order.order_id || order.id)
    return
  }
  saving.value = true
  try {
    await api.cancelPaperOrder(pendingCancel.value)
    message.value = '模拟盘挂单已撤销'
    pendingCancel.value = ''
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '撤销模拟盘订单失败'
  } finally {
    saving.value = false
  }
}

async function savePositionRisk(code: string) {
  saving.value = true
  try {
    await api.updatePaperPositionRisk(code, stopDrafts.value[code] || {})
    message.value = `${code} 的止损止盈已更新`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '止损止盈更新失败'
  } finally {
    saving.value = false
  }
}

async function closePosition(position: Row) {
  if (pendingClose.value !== String(position.code)) {
    pendingClose.value = String(position.code)
    closeVolume.value = Number(position.volume || 0)
    return
  }
  if (!closeVolume.value || closeVolume.value > Number(position.volume) || closeVolume.value % 100 !== 0) {
    message.value = '平仓数量必须是不超过持仓的 100 的整数倍'
    return
  }
  saving.value = true
  try {
    await api.closePaperPosition(String(position.code), closeVolume.value)
    message.value = `已创建 ${position.code} 的模拟盘平仓订单`
    pendingClose.value = ''
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘平仓失败'
  } finally {
    saving.value = false
  }
}

async function saveRiskRules() {
  saving.value = true
  try {
    await api.put('/api/paper/risk/rules', riskForm.value)
    message.value = '模拟盘风控规则已更新'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模拟盘风控规则更新失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><RouterLink to="/app/more" class="muted small"><ArrowLeft :size="14" />返回更多工具</RouterLink><h1>模拟盘与风控执行</h1><p>完整恢复旧模拟盘工作流。所有写操作明确标注为模拟盘并需要人工确认；此页不会调用 Broker 或真实下单接口。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button></div>
    <div v-if="message" class="error-box" role="status"><CircleAlert :size="16" />{{ message }}</div>
    <section class="panel paper-control-panel"><div class="panel-head"><div><h2>模拟盘控制</h2><p>启动会恢复或创建本地模拟状态；重置前请确认当前状态不再需要。</p></div><span class="tag" :class="running ? 'good' : 'warn'">{{ running ? '运行中' : '未运行' }}</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="paper-strategy">策略</label><select id="paper-strategy" v-model="startForm.strategy" :disabled="running"><option v-for="strategy in strategyOptions" :key="String(strategy.name)" :value="strategy.name">{{ strategy.label || strategy.name }}</option></select></div><div class="field"><label for="paper-codes">股票代码</label><input id="paper-codes" v-model="startForm.codes" :disabled="running" placeholder="000001,600519" /></div><div class="field"><label for="paper-interval">轮询秒数</label><input id="paper-interval" v-model.number="startForm.interval" type="number" min="5" :disabled="running" /></div><div class="field"><label for="paper-cash">初始资金</label><input id="paper-cash" v-model.number="startForm.cash" type="number" min="1" :disabled="running" /></div></div><label class="check-control"><input v-model="startForm.enable_risk" type="checkbox" :disabled="running" />启动风控规则</label><div class="form-actions"><button v-if="!running" class="button primary" type="button" :disabled="saving" @click="startReview = !startReview"><Play :size="15" />准备启动模拟盘</button><button v-else class="button" type="button" :disabled="saving" @click="stopPaper"><Pause :size="15" />停止模拟盘</button><button class="button danger" type="button" :disabled="saving" @click="resetPaper"><RotateCcw :size="15" />{{ resetReview ? '再次确认重置' : '重置状态' }}</button><button v-if="resetReview" class="button ghost" type="button" @click="resetReview = false"><X :size="15" />取消</button></div><div v-if="startReview" class="inline-confirm"><span>确认以 {{ startForm.strategy }} 运行 {{ startForm.codes }} 的本地模拟盘？不会连接真实账户。</span><button class="button primary" type="button" :disabled="saving" @click="startPaper"><Check :size="15" />确认启动</button><button class="button ghost" type="button" @click="startReview = false">取消</button></div></div></section>
    <div class="summary-strip"><div class="summary-item"><span>运行状态</span><strong>{{ running ? '运行中' : '未运行' }}</strong><small>{{ status?.config?.strategy || status?.strategy || '—' }}</small></div><div class="summary-item"><span>总权益</span><strong>{{ number(status?.equity ?? performance?.total_equity) }}</strong><small>本地模拟快照</small></div><div class="summary-item"><span>持仓</span><strong>{{ positions.length }}</strong><small>{{ number(status?.cash) }} 可用现金</small></div><div class="summary-item"><span>交易</span><strong>{{ tradeStats?.total_trades ?? status?.trade_count ?? '—' }}</strong><small>当前历史范围</small></div></div>
    <nav class="workspace-tabs" aria-label="模拟盘工作区"><button type="button" :class="{ active: tab === 'orders' }" @click="tab = 'orders'"><Play :size="15" />订单</button><button type="button" :class="{ active: tab === 'positions' }" @click="tab = 'positions'"><ShieldCheck :size="15" />持仓</button><button type="button" :class="{ active: tab === 'performance' }" @click="tab = 'performance'"><BarChart3 :size="15" />绩效</button><button type="button" :class="{ active: tab === 'risk' }" @click="tab = 'risk'"><ShieldAlert :size="15" />风控</button></nav>

    <template v-if="tab === 'orders'"><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>创建模拟盘订单</h2><p>订单只写入 `/api/paper/orders`；提交前先显示完整预览。</p></div><ShieldCheck :size="18" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="paper-order-code">股票代码</label><input id="paper-order-code" v-model="orderForm.code" placeholder="600519" /></div><div class="field"><label for="paper-order-direction">方向</label><select id="paper-order-direction" v-model="orderForm.direction"><option value="buy">买入</option><option value="sell">卖出</option></select></div><div class="field"><label for="paper-order-type">类型</label><select id="paper-order-type" v-model="orderForm.order_type"><option value="market">市价</option><option value="limit">限价</option><option value="stop_loss">止损</option><option value="take_profit">止盈</option></select></div><div class="field"><label for="paper-order-price">价格</label><input id="paper-order-price" v-model.number="orderForm.price" type="number" min="0" step="0.001" :disabled="orderForm.order_type === 'market'" /></div><div class="field"><label for="paper-order-volume">数量</label><input id="paper-order-volume" v-model.number="orderForm.volume" type="number" min="100" step="100" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="saving" @click="reviewOrder"><Play :size="15" />生成订单预览</button></div><div v-if="orderReview" class="inline-confirm"><span>{{ orderReview.direction === 'buy' ? '买入' : '卖出' }} {{ orderReview.code }} {{ orderReview.volume }} 股 · {{ orderReview.order_type }} {{ orderReview.price || '市价' }}</span><button class="button primary" type="button" :disabled="saving" @click="submitOrder"><Check :size="15" />确认写入模拟盘</button><button class="button ghost" type="button" @click="orderReview = null">取消</button></div></div></section><section class="panel"><div class="panel-head"><div><h2>待处理订单</h2><p>撤单需要再次确认；订单状态以模拟盘服务返回为准。</p></div><span class="tag">{{ orders.length }} 条</span></div><div class="panel-body"><div v-if="!orders.length" class="empty">暂无待处理订单。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>标的</th><th>方向</th><th>类型</th><th>数量</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="order in orders" :key="order.order_id || order.id"><td class="symbol">{{ order.code }}</td><td :class="order.direction === 'buy' ? 'good' : 'bad'">{{ order.direction === 'buy' ? '买入' : '卖出' }}</td><td>{{ order.order_type || '—' }}</td><td>{{ order.volume }}</td><td><span class="tag" :class="statusClass(order.status)">{{ order.status || 'pending' }}</span></td><td><button class="button danger compact-button" type="button" :disabled="saving" @click="cancelOrder(order)"><Ban :size="14" />{{ pendingCancel === String(order.order_id || order.id) ? '再次确认' : '撤销' }}</button><button v-if="pendingCancel === String(order.order_id || order.id)" class="button ghost compact-button" type="button" @click="pendingCancel = ''">取消</button></td></tr></tbody></table></div></div></section></div></template>

    <template v-else-if="tab === 'positions'"><section class="panel"><div class="panel-head"><div><h2>模拟盘持仓</h2><p>止损、止盈和平仓都只创建模拟盘动作，且会保留失败提示。</p></div><span class="tag">{{ positions.length }} 个标的</span></div><div class="panel-body"><div v-if="!positions.length" class="empty">暂无模拟盘持仓。</div><div v-else class="table-scroll"><table class="decision-table paper-position-table"><thead><tr><th>标的</th><th>数量</th><th>成本 / 现价</th><th>市值</th><th>盈亏</th><th>止损 / 止盈</th><th>操作</th></tr></thead><tbody><tr v-for="position in positions" :key="position.code"><td class="symbol">{{ position.code }}</td><td>{{ position.volume }}</td><td>{{ number(position.avg_price) }} / {{ number(position.current_price) }}</td><td>{{ number(position.market_value) }}</td><td :class="Number(position.unrealized_pnl) >= 0 ? 'good' : 'bad'">{{ number(position.unrealized_pnl) }}<small>{{ percent(position.unrealized_pnl_pct) }}</small></td><td><div class="mini-fields"><input v-model.number="stopDrafts[position.code].stop_loss_price" type="number" step="0.01" placeholder="止损" /><input v-model.number="stopDrafts[position.code].take_profit_price" type="number" step="0.01" placeholder="止盈" /></div><button class="button ghost compact-button" type="button" :disabled="saving" @click="savePositionRisk(position.code)"><Save :size="13" />保存</button></td><td><button class="button danger compact-button" type="button" :disabled="saving" @click="closePosition(position)"><Square :size="13" />{{ pendingClose === String(position.code) ? '再次确认平仓' : '平仓' }}</button><div v-if="pendingClose === String(position.code)" class="inline-close"><input v-model.number="closeVolume" type="number" min="100" step="100" :max="position.volume" aria-label="平仓数量" /><button class="button ghost compact-button" type="button" @click="pendingClose = ''">取消</button></div></td></tr></tbody></table></div></div></section></template>

    <template v-else-if="tab === 'performance'"><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>绩效指标</h2><p>没有历史数据时显示为空，不把 0 当作“已运行”。</p></div><Download :size="18" class="faint" /></div><div class="panel-body"><div class="metric-grid"><div v-for="row in metricRows" :key="String(row[0])" class="metric-cell"><span>{{ row[0] }}</span><strong>{{ row[0] === '胜率' || row[0] === '最大回撤' || row[0] === '总收益' ? percent(row[1]) : number(row[1]) }}</strong></div></div><div class="form-actions"><a class="button ghost" href="/api/paper/trades-v2/export?format=csv" download><Download :size="15" />导出 CSV</a><a class="button ghost" href="/api/paper/trades-v2/export?format=json" download><Download :size="15" />导出 JSON</a></div></div></section><section class="panel"><div class="panel-head"><div><h2>每日绩效</h2><p>最近 60 天的权益和回撤记录。</p></div></div><div class="panel-body"><div v-if="!dailyPerformance.length" class="empty">暂无每日绩效。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>日期</th><th>权益</th><th>日收益</th><th>累计收益</th><th>回撤</th></tr></thead><tbody><tr v-for="row in dailyPerformance.slice(-30).reverse()" :key="row.date"><td>{{ row.date }}</td><td>{{ number(row.total_equity) }}</td><td :class="Number(row.daily_return) >= 0 ? 'good' : 'bad'">{{ percent(row.daily_return) }}</td><td>{{ percent(row.cumulative_return) }}</td><td class="bad">{{ percent(row.max_drawdown) }}</td></tr></tbody></table></div></div></section></div><section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>交易历史</h2><p>成交记录可按后端返回的策略和信号原因追溯。</p></div></div><div class="panel-body"><div v-if="!trades.length" class="empty">暂无成交历史。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>标的</th><th>方向</th><th>价格 / 数量</th><th>盈亏</th><th>策略</th></tr></thead><tbody><tr v-for="trade in trades" :key="trade.trade_id || trade.order_id"><td>{{ trade.created_at || '—' }}</td><td class="symbol">{{ trade.code }}</td><td>{{ trade.direction === 'buy' ? '买入' : '卖出' }}</td><td>{{ number(trade.price) }} / {{ trade.volume }}</td><td :class="Number(trade.profit) >= 0 ? 'good' : 'bad'">{{ number(trade.profit) }}</td><td>{{ trade.strategy_name || '—' }}</td></tr></tbody></table></div></div></section></template>

    <template v-else><div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>风控规则</h2><p>修改只影响模拟盘风控管理器，不改变确定性决策引擎。</p></div><ShieldAlert :size="18" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label>单票上限</label><input v-model.number="riskForm.max_position_pct" type="number" min="0" max="1" step="0.01" /></div><div class="field"><label>最大持仓数</label><input v-model.number="riskForm.max_positions" type="number" min="1" /></div><div class="field"><label>最大回撤</label><input v-model.number="riskForm.max_drawdown" type="number" min="0" max="1" step="0.01" /></div><div class="field"><label>单日最大损失</label><input v-model.number="riskForm.max_daily_loss" type="number" min="0" max="1" step="0.01" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="saving" @click="saveRiskRules"><Save :size="15" />保存风控规则</button></div><pre class="result-code" style="margin-top:16px">{{ JSON.stringify(riskRules, null, 2) }}</pre></div></section><section class="panel"><div class="panel-head"><div><h2>风险事件</h2><p>止损、仓位、回撤和数据问题都保留为事件。</p></div><span class="tag">{{ riskEvents.length }} 条</span></div><div class="panel-body"><div v-if="!riskEvents.length" class="empty">暂无风控事件。</div><div v-else class="check-list"><div v-for="(event, index) in riskEvents" :key="String(event.id || index)" class="check-row"><div class="check-copy"><strong>{{ event.event_type || event.type || '风险事件' }}</strong><span>{{ event.message || event.reason || event.created_at || '—' }}</span></div><span class="tag warn">记录</span></div></div></div></section></div></template>
  </section>
</template>
