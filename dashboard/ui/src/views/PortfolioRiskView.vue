<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Check, Download, RefreshCw, Save, ShieldAlert, Square, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import AsyncState from '../components/base/AsyncState.vue'

type Row = Record<string, any>

const snapshot = ref<Row | null>(null)
const risk = ref<Row | null>(null)
const distribution = ref<Row[]>([])
const trades = ref<Row[]>([])
const loading = ref(false)
const refreshing = ref(false)
const saving = ref(false)
const message = ref('')
const pendingClose = ref('')
const closeVolume = ref(0)
const closeAllReview = ref(false)
const stopDrafts = ref<Record<string, { stop_loss_price: number | null; take_profit_price: number | null }>>({})

const positions = computed<Row[]>(() => Array.isArray(snapshot.value?.positions) ? snapshot.value.positions : [])
const totalPnl = computed(() => positions.value.reduce((sum, item) => sum + Number(item.pnl ?? item.unrealized_pnl ?? 0), 0))

function number(value: unknown, digits = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

async function load() {
  loading.value = true
  refreshing.value = snapshot.value !== null
  message.value = ''
  const results = await Promise.allSettled([
    api.portfolioSnapshot(), api.portfolioRisk(), api.portfolioIndustryDistribution(), api.portfolioTrades(),
  ])
  const value = <T>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
  snapshot.value = value<Row>(0)
  risk.value = value<Row>(1)
  const distributionPayload = value<any>(2)
  const tradePayload = value<Row>(3)
  distribution.value = Array.isArray(distributionPayload) ? distributionPayload : []
  trades.value = Array.isArray(tradePayload) ? tradePayload : Array.isArray(tradePayload?.trades) ? tradePayload.trades : []
  for (const position of positions.value) {
    stopDrafts.value[position.code] = { stop_loss_price: position.stop_loss_price || null, take_profit_price: position.take_profit_price || null }
  }
  if (results.every((item) => item.status === 'rejected')) message.value = '组合数据暂不可用；页面保留空状态。'
  else if (results.some((item) => item.status === 'rejected')) message.value = '部分组合数据暂不可用；已返回区块仍可查看。'
  loading.value = false
  refreshing.value = false
}

async function saveStopLoss(position: Row) {
  saving.value = true
  try {
    await api.updatePortfolioStopLoss({ code: position.code, ...(stopDrafts.value[position.code] || {}) })
    message.value = `${position.code} 的止损止盈已保存`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '止损止盈保存失败'
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
  const volume = Number(closeVolume.value || 0)
  if (volume <= 0 || volume > Number(position.volume) || volume % 100 !== 0) {
    message.value = '平仓数量必须是不超过持仓的 100 的整数倍'
    return
  }
  saving.value = true
  try {
    await api.closePortfolioPosition({ code: position.code, volume })
    message.value = `已创建 ${position.code} 的模拟盘平仓订单`
    pendingClose.value = ''
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '平仓失败'
  } finally {
    saving.value = false
  }
}

async function closeAll() {
  if (!closeAllReview.value) {
    closeAllReview.value = true
    return
  }
  saving.value = true
  try {
    await api.closeAllPortfolioPositions({})
    message.value = '已创建全部持仓的模拟盘平仓订单'
    closeAllReview.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '批量平仓失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><span class="eyebrow">SIMULATION / RISK CONTROL</span><h1>持仓、绩效与风控</h1><p>这里的写操作只进入本地模拟盘适配器，所有平仓和风控变更都先经过明确确认；真实 Broker 仍然没有入口。</p></div><div class="head-actions"><RefreshIndicator :state="refreshing ? 'refreshing' : snapshot ? 'live' : 'unavailable'" :label="refreshing ? '保留快照，正在刷新' : '模拟盘快照'" /><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button><button class="button danger" type="button" :disabled="saving || !positions.length" @click="closeAll"><Square :size="15" />{{ closeAllReview ? '再次确认全部平仓' : '全部平仓' }}</button><button v-if="closeAllReview" class="button ghost" type="button" @click="closeAllReview = false"><X :size="15" />取消</button></div></div>
    <AsyncState v-if="!loading && !snapshot && !positions.length" state="empty" title="暂无模拟盘持仓快照" message="加载不到组合数据时不会使用默认值；可以刷新或先建立模拟盘记录。" @retry="load" />
    <AsyncState v-if="message" state="error" :message="message" @retry="load" />
    <div v-if="positions.length" class="mobile-task-bar"><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="14" />刷新快照</button><button class="button danger" type="button" :disabled="saving" @click="closeAll"><Square :size="14" />{{ closeAllReview ? '确认全部平仓' : '全部平仓' }}</button></div>
    <div class="summary-strip"><div class="summary-item"><span>总权益</span><strong>{{ number(snapshot?.total_equity) }}</strong><small>当前模拟盘快照</small></div><div class="summary-item"><span>持仓市值</span><strong>{{ number(snapshot?.market_value) }}</strong><small>{{ positions.length }} 个标的</small></div><div class="summary-item"><span>组合盈亏</span><strong :class="totalPnl >= 0 ? 'good' : 'bad'">{{ number(totalPnl) }}</strong><small>由当前持仓返回值合计</small></div><div class="summary-item"><span>最大回撤</span><strong class="bad">{{ number(risk?.max_drawdown ?? snapshot?.max_drawdown) }}</strong><small>风险指标不是交易指令</small></div></div>
    <div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>持仓快照</h2><p>行情、成本、盈亏和仓位由模拟盘适配器返回。</p></div><ShieldAlert :size="18" class="faint" /></div><div class="panel-body"><div v-if="!positions.length" class="empty">暂无持仓快照。</div><div v-else class="table-scroll"><table class="decision-table portfolio-position-table"><thead><tr><th>标的</th><th>数量</th><th>现价 / 市值</th><th>盈亏</th><th>止损 / 止盈</th><th>操作</th></tr></thead><tbody><tr v-for="position in positions" :key="position.code"><td class="symbol">{{ position.code }}<small>{{ position.name || position.industry || '—' }}</small></td><td>{{ position.volume }}</td><td>{{ number(position.current_price) }}<small>{{ number(position.market_value) }}</small></td><td :class="Number(position.pnl ?? position.unrealized_pnl) >= 0 ? 'good' : 'bad'">{{ number(position.pnl ?? position.unrealized_pnl) }}<small>{{ number(position.pnl_pct, 2) }}</small></td><td><div class="mini-fields"><input v-model.number="stopDrafts[position.code].stop_loss_price" type="number" step="0.01" placeholder="止损" /><input v-model.number="stopDrafts[position.code].take_profit_price" type="number" step="0.01" placeholder="止盈" /></div><button class="button ghost compact-button" type="button" :disabled="saving" @click="saveStopLoss(position)"><Save :size="13" />保存</button></td><td><button class="button danger compact-button" type="button" :disabled="saving" @click="closePosition(position)"><Square :size="13" />{{ pendingClose === String(position.code) ? '再次确认' : '平仓' }}</button><div v-if="pendingClose === String(position.code)" class="inline-close"><input v-model.number="closeVolume" type="number" min="100" step="100" :max="position.volume" aria-label="平仓数量" /><button class="button ghost compact-button" type="button" @click="pendingClose = ''">取消</button></div></td></tr></tbody></table></div></div></section><section class="panel"><div class="panel-head"><div><h2>行业分布</h2><p>集中度用于风险核验，不代替风控规则。</p></div></div><div class="panel-body"><div v-if="!distribution.length" class="empty">暂无行业分布。</div><div v-else class="check-list"><div v-for="item in distribution" :key="item.industry || item.name" class="check-row"><div class="check-copy"><strong>{{ item.industry || item.name || '未知行业' }}</strong><span>{{ item.count ?? item.position_count ?? '—' }} 个标的</span></div><span class="tag">{{ number(item.value ?? item.market_value) }}</span></div></div></div></section></div>
    <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>风险指标与交易历史</h2><p>导出内容只来自模拟盘数据，不包含真实账户。</p></div><div class="head-actions"><a class="button ghost" href="/api/portfolio/export?format=csv" download><Download :size="15" />导出 CSV</a><a class="button ghost" href="/api/portfolio/export?format=json" download><Download :size="15" />导出 JSON</a></div></div><div class="panel-body"><div v-if="risk" class="metric-grid"><div v-for="(value, key) in risk" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ typeof value === 'number' ? number(value) : String(value ?? '—') }}</strong></div></div><div v-else class="empty">暂无风险指标。</div><div v-if="trades.length" class="table-scroll" style="margin-top:18px"><table class="decision-table"><thead><tr><th>时间</th><th>标的</th><th>方向</th><th>价格 / 数量</th><th>盈亏</th></tr></thead><tbody><tr v-for="(trade, index) in trades.slice(0, 50)" :key="trade.trade_id || trade.id || index"><td>{{ trade.created_at || trade.time || '—' }}</td><td class="symbol">{{ trade.code || '—' }}</td><td>{{ trade.direction || '—' }}</td><td>{{ number(trade.price) }} / {{ trade.volume ?? '—' }}</td><td :class="Number(trade.profit) >= 0 ? 'good' : 'bad'">{{ number(trade.profit) }}</td></tr></tbody></table></div><div v-else class="empty" style="margin-top:18px">暂无交易历史。</div></div></section>
  </section>
</template>
