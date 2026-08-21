<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, BarChart3, Play, RefreshCw, ShieldAlert } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import BrokerDisableGuard from '../components/guards/BrokerDisableGuard.vue'
import PaperContextPanel from '../components/paper/PaperContextPanel.vue'
import PaperControlPanel from '../components/paper/PaperControlPanel.vue'
import PaperOrderPanel from '../components/paper/PaperOrderPanel.vue'
import PaperPositionPanel from '../components/paper/PaperPositionPanel.vue'
import PaperPerformancePanel from '../components/paper/PaperPerformancePanel.vue'
import PaperRiskPanel from '../components/paper/PaperRiskPanel.vue'
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
const saving = ref(false)
const v2Context = useV2ContextStore()

const running = computed(() => Boolean(status.value?.running))
const runningStateKnown = computed(() => statusAvailable.value && typeof status.value?.running === 'boolean')
const reconciliationRequired = computed(() => Boolean(status.value?.reconciliation_status || status.value?.reconciliation_required || status.value?.recovery_status))
const statusAvailable = computed(() => Boolean(status.value))
const canOperate = computed(() => statusAvailable.value && runningStateKnown.value && !reconciliationRequired.value && v2Context.controlsBlocked !== true)
const initialLoading = computed(() => loading.value && !hasLoaded.value)

function payloadData(value: any): any { return value?.data ?? value }

async function load() {
  loading.value = true
  const results = await Promise.allSettled([
    api.paperStatus(), api.paperPositions(), api.paperRisk(),
    api.paperRiskRules(), api.paperDailyPerformance?.() ?? Promise.resolve({} as any),
    api.paperPerformance?.() ?? Promise.resolve({} as any),
    api.paperTradeStats?.() ?? Promise.resolve({} as any),
    api.paperTrades?.() ?? Promise.resolve({} as any),
    api.paperStrategies?.() ?? Promise.resolve({} as any),
  ])
  status.value = payloadData(results[0]) || {}
  positions.value = Array.isArray(payloadData(results[1])) ? payloadData(results[1]) : []
  riskEvents.value = Array.isArray(payloadData(results[2])) ? payloadData(results[2]) : []
  riskRules.value = payloadData(results[3]) || {}
  dailyPerformance.value = Array.isArray(payloadData(results[4])) ? payloadData(results[4]) : []
  performance.value = payloadData(results[5]) || null
  tradeStats.value = payloadData(results[6]) || null
  trades.value = Array.isArray(payloadData(results[7])) ? payloadData(results[7]) : []
  orders.value = trades.value
  strategies.value = Array.isArray(payloadData(results[8])) ? payloadData(results[8]) : []
  hasLoaded.value = true
  loading.value = false
  if (v2Context.status === 'idle') v2Context.load()
}

onMounted(load)
watch(() => tab.value, () => { if (!hasLoaded.value) load() })
</script>

<template>
  <BrokerDisableGuard />
  <section>
    <div class="page-head">
      <div>
        <RouterLink to="/app/portfolio-risk" class="muted small"><ArrowLeft :size="14" />组合工作区</RouterLink>
        <h1>模拟盘与风控执行</h1>
        <p>paper 环境的状态与操作工作区。页面不会把 legacy 返回值解释为 V2 ExecutionRun。</p>
      </div>
      <button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="15" />刷新</button>
    </div>

    <div v-if="initialLoading" class="loading-box" role="status" aria-live="polite">正在读取 paper 状态与持仓…</div>

    <template v-if="hasLoaded">
      <PaperContextPanel :status="status" :loading="loading" />

      <PaperControlPanel
        :status="status" :loading="loading" :can-operate="canOperate"
        :running-state-known="runningStateKnown" :running="running" :strategies="strategies"
        @refresh="load"
      />

      <div class="summary-strip">
        <div class="summary-item"><span>Paper 运行状态</span><strong>{{ running ? '运行中' : '已停止' }}</strong></div>
        <div class="summary-item"><span>总权益</span><strong>{{ status?.equity ?? performance?.total_equity ?? '—' }}</strong></div>
        <div class="summary-item"><span>持仓</span><strong>{{ positions.length }}</strong><small>{{ status?.cash ?? '—' }} 可用现金</small></div>
        <div class="summary-item"><span>交易</span><strong>{{ tradeStats?.total_trades ?? status?.trade_count ?? '—' }}</strong></div>
      </div>

      <nav class="workspace-tabs" role="tablist" aria-label="模拟盘工作区">
        <button role="tab" :aria-selected="tab === 'orders'" :tabindex="tab === 'orders' ? 0 : -1" :class="{ active: tab === 'orders' }" @click="tab = 'orders'"><Play :size="15" />订单</button>
        <button role="tab" :aria-selected="tab === 'positions'" :tabindex="tab === 'positions' ? 0 : -1" :class="{ active: tab === 'positions' }" @click="tab = 'positions'"><BarChart3 :size="15" />持仓</button>
        <button role="tab" :aria-selected="tab === 'performance'" :tabindex="tab === 'performance' ? 0 : -1" :class="{ active: tab === 'performance' }" @click="tab = 'performance'"><BarChart3 :size="15" />绩效</button>
        <button role="tab" :aria-selected="tab === 'risk'" :tabindex="tab === 'risk' ? 0 : -1" :class="{ active: tab === 'risk' }" @click="tab = 'risk'"><ShieldAlert :size="15" />风控</button>
      </nav>

      <PaperOrderPanel v-if="tab === 'orders'" :orders="orders" :can-operate="canOperate" :saving="saving" @refresh="load" @update:saving="(v: boolean) => saving = v" />
      <PaperPositionPanel v-else-if="tab === 'positions'" :positions="positions" :can-operate="canOperate" :saving="saving" @refresh="load" @update:saving="(v: boolean) => saving = v" />
      <PaperPerformancePanel v-else-if="tab === 'performance'" :status="status" :performance="performance" :trade-stats="tradeStats" :daily-performance="dailyPerformance" />
      <PaperRiskPanel v-else :status="status" :risk-events="riskEvents" :risk-rules="riskRules" :can-operate="canOperate" :saving="saving" @refresh="load" @update:saving="(v: boolean) => saving = v" />
    </template>
  </section>
</template>

<style scoped>
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.page-head h1 { font-size: 20px; margin: 6px 0 4px; }
.page-head p { color: var(--ink-soft); font-size: 13px; }
.loading-box { padding: 40px; text-align: center; color: var(--ink-soft); }
.summary-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
.summary-item { padding: 12px 16px; border: 1px solid var(--line); border-radius: 8px; }
.summary-item span { display: block; font-size: 12px; color: var(--ink-soft); margin-bottom: 4px; }
.summary-item strong { font-size: 18px; }
.summary-item small { display: block; font-size: 11px; color: var(--ink-faint); margin-top: 2px; }
.workspace-tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.workspace-tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 10px 16px; border: none; background: none; color: var(--ink-soft); cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; }
.workspace-tabs button.active { color: var(--ink); border-bottom-color: var(--accent); }
</style>
