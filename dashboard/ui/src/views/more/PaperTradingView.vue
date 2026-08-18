<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RouterLink } from 'vue-router'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseInput from '../../components/base/BaseInput.vue'
import BrokerDisableGuard from '../../components/guards/BrokerDisableGuard.vue'
import { TrendingUp, RefreshCw, TrendingDown } from 'lucide-vue-next'
import { getPaperAccount, getPaperHoldings, getPaperTrades, createPaperTrade } from '../../api/paper'
import type { PaperAccount, PaperHolding, PaperTrade } from '../../api/paper'
import { LIVE_TRADING_ENABLED } from '../../config/features'
import { useResearchContextStore } from '../../stores/researchContext'

const title = '模拟盘交易'
const description = '完整的模拟交易环境，用于验证策略和训练交易技能'

const contextStore = useResearchContextStore()
const hasResearchContext = computed(() => contextStore.hasInstrument)
const contextInstrument = computed(() => hasResearchContext.value ? `${contextStore.context.market} / ${contextStore.context.symbol}` : '')

// State
const loading = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const account = ref<PaperAccount | null>(null)
const holdings = ref<PaperHolding[]>([])
const trades = ref<PaperTrade[]>([])

// LIVE TRADING DISABLED
const isLiveTradingDisabled = computed(() => !LIVE_TRADING_ENABLED)

// Trade form
  const tradeForm = ref({
  symbol: contextStore.context.symbol || '',
  action: 'buy' as 'buy' | 'sell',
  shares: 100
})

// Computed
const profitColor = computed(() => {
  if (!account.value || account.value.profit_loss == null) return ''
  return account.value.profit_loss >= 0 ? 'profit' : 'loss'
})

// Methods
async function loadData() {
  if (!hasResearchContext.value) return
  loading.value = true
  error.value = null

  try {
    const [accountData, holdingsData, tradesData] = await Promise.all([
      getPaperAccount(),
      getPaperHoldings(),
      getPaperTrades(10)
    ])

    account.value = accountData
    holdings.value = holdingsData
    trades.value = tradesData
  } catch (err) {
    console.error('Failed to load paper trading data:', err)
    error.value = '加载数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function handleTrade() {
  if (!hasResearchContext.value) return
  error.value = null
  notice.value = null
  const symbol = tradeForm.value.symbol.trim() || contextStore.context.symbol || ''
  if (!symbol) { error.value = '请先选择研究对象'; return }
  if (!Number.isInteger(Number(tradeForm.value.shares)) || Number(tradeForm.value.shares) <= 0) {
    error.value = '交易数量必须是大于 0 的整数'
    return
  }
  submitting.value = true
  try {
    const trade = await createPaperTrade({ symbol, action: tradeForm.value.action, shares: Number(tradeForm.value.shares), strategyName: contextStore.context.strategy || undefined })
    notice.value = `Paper Engine 已接收订单：${trade.symbol}，状态 ${trade.status}`
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模拟订单提交失败'
  } finally {
    submitting.value = false
  }
}

function formatNumber(num: number | undefined): string {
  return typeof num === 'number' && Number.isFinite(num) ? num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'
}

function formatPercent(num: number | undefined): string {
  return typeof num === 'number' && Number.isFinite(num) ? `${num.toFixed(2)}%` : '—'
}

function signedNumber(num: number | undefined): string {
  return num == null || !Number.isFinite(num) ? '—' : `${num >= 0 ? '+' : ''}${formatNumber(num)}`
}

function valueClass(num: number | undefined): string {
  return num == null || !Number.isFinite(num) ? '' : num >= 0 ? 'profit' : 'loss'
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <BrokerDisableGuard />

  <div class="page-container">
    <div v-if="!hasResearchContext" class="panel empty-context-panel"><h2>先选择研究对象</h2><p>模拟盘预览必须继承一项研究对象。请先完成研究或验证，再进入 Paper Engine。</p><RouterLink class="button primary" to="/app/decision">返回决策中心</RouterLink></div>
    <template v-else>
    <div class="data-source context-source"><strong>当前研究对象：{{ contextInstrument }}</strong><span>{{ contextStore.context.name || '未命名标的' }}</span></div>
    <!-- Disclaimer Banner -->
    <div class="disclaimer">
      <strong>模拟交易功能，仅供学习研究，不构成投资建议。</strong>
      所有交易均为虚拟，不涉及真实资金。
    </div>

    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <div class="head-actions">
        <BaseButton
          variant="ghost"
          size="sm"
          :loading="loading"
          @click="loadData"
        >
          <RefreshCw :size="16" />
          刷新
        </BaseButton>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="notice" class="notice-banner" role="status">{{ notice }}</div>

    <!-- Loading State -->
    <div v-if="loading && !account" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="account" class="content-grid">
      <!-- Account Summary -->
      <BaseCard padding="lg" class="account-summary">
        <h2 class="section-title">账户概览</h2>
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-label">初始资金</div>
            <div class="summary-value">¥{{ formatNumber(account.initial_capital) }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">当前总值</div>
            <div class="summary-value">¥{{ formatNumber(account.current_value) }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">盈亏金额</div>
            <div class="summary-value" :class="profitColor">
              {{ signedNumber(account.profit_loss) }}
            </div>
          </div>
          <div class="summary-item">
            <div class="summary-label">收益率</div>
            <div class="summary-value" :class="profitColor">
              {{ account.return_percent == null ? '—' : `${account.return_percent >= 0 ? '+' : ''}${formatPercent(account.return_percent)}` }}
            </div>
          </div>
          <div class="summary-item">
            <div class="summary-label">可用资金</div>
            <div class="summary-value secondary">¥{{ formatNumber(account.cash) }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">持仓市值</div>
            <div class="summary-value secondary">¥{{ formatNumber(account.position_value) }}</div>
          </div>
        </div>
      </BaseCard>

      <!-- Holdings Table -->
      <BaseCard padding="lg" class="holdings-section">
        <h2 class="section-title">当前持仓</h2>
        <div v-if="holdings.length === 0" class="empty-state">
          暂无持仓
        </div>
        <div v-else class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>股票代码</th>
                <th>股票名称</th>
                <th class="align-right">持仓数量</th>
                <th class="align-right">成本价</th>
                <th class="align-right">现价</th>
                <th class="align-right">盈亏金额</th>
                <th class="align-right">盈亏比例</th>
                <th class="align-right">仓位占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="holding in holdings" :key="holding.symbol">
                <td class="code">{{ holding.symbol }}</td>
                <td>{{ holding.name }}</td>
                <td class="align-right">{{ holding.shares }}</td>
                <td class="align-right">{{ formatNumber(holding.cost_basis) }}</td>
                <td class="align-right">{{ formatNumber(holding.current_price) }}</td>
                <td class="align-right" :class="valueClass(holding.profit_loss)">
                  {{ signedNumber(holding.profit_loss) }}
                </td>
                <td class="align-right" :class="valueClass(holding.profit_loss_percent)">
                  {{ signedNumber(holding.profit_loss_percent) }}
                </td>
                <td class="align-right">{{ formatPercent(holding.weight) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </BaseCard>

      <!-- Trade Form -->
      <BaseCard padding="lg" class="trade-form">
        <h2 class="section-title">新建交易</h2>
        <form @submit.prevent="handleTrade">
          <div class="form-row">
            <div class="form-group">
              <label>股票代码</label>
              <BaseInput
                v-model="tradeForm.symbol"
                placeholder="当前研究对象"
                size="md"
              />
            </div>
            <div class="form-group">
              <label>交易方向</label>
              <div class="toggle-group">
                <button
                  type="button"
                  class="toggle-btn"
                  :class="{ active: tradeForm.action === 'buy' }"
                  @click="tradeForm.action = 'buy'"
                >
                  <TrendingUp :size="16" />
                  买入
                </button>
                <button
                  type="button"
                  class="toggle-btn"
                  :class="{ active: tradeForm.action === 'sell' }"
                  @click="tradeForm.action = 'sell'"
                >
                  <TrendingDown :size="16" />
                  卖出
                </button>
              </div>
            </div>
            <div class="form-group">
              <label>数量（股）</label>
              <BaseInput
                v-model="tradeForm.shares"
                type="number"
                placeholder="100"
                size="md"
              />
            </div>
          </div>
          <BaseButton
            type="submit"
            variant="primary"
            size="md"
            :loading="submitting"
            :disabled="submitting"
          >
            {{ submitting ? '提交中…' : '确认提交模拟订单' }}
          </BaseButton>
          <p class="trade-confirmation">执行环境：Paper Engine · 当前策略：{{ contextStore.context.strategy || '手动研究' }} · 价格由后端行情/撮合决定</p>
        </form>
      </BaseCard>

      <!-- Trade History -->
      <BaseCard padding="lg" class="trades-section">
        <h2 class="section-title">交易历史</h2>
        <div v-if="trades.length === 0" class="empty-state">
          暂无交易记录
        </div>
        <div v-else class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>股票代码</th>
                <th>方向</th>
                <th class="align-right">成交价</th>
                <th class="align-right">数量</th>
                <th class="align-right">成交金额</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="trade in trades" :key="trade.id">
                <td class="timestamp">{{ formatDateTime(trade.timestamp) }}</td>
                <td class="code">{{ trade.symbol }}</td>
                <td>
                  <span :class="['action-badge', trade.action]">
                    {{ trade.action === 'buy' ? '买入' : '卖出' }}
                  </span>
                </td>
                <td class="align-right">{{ formatNumber(trade.price) }}</td>
                <td class="align-right">{{ trade.shares }}</td>
                <td class="align-right">{{ formatNumber(trade.total_amount) }}</td>
                <td>
                  <span :class="['status-badge', trade.status]">
                    {{ trade.status === 'completed' ? '已成交' : trade.status === 'pending' ? '待成交' : '失败' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </BaseCard>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      暂无数据
    </div>
    </template>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1400px;
  margin: 0 auto;
}

.disclaimer {
  padding: var(--spacing-md) var(--spacing-lg);
  background-color: var(--color-warn-bg);
  color: var(--color-ink);
  border-left: 3px solid var(--color-warn);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-lg);
  font-size: var(--font-size-sm);
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.page-head h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin-bottom: var(--spacing-xs);
}

.page-head p {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
  margin: 0;
}

.head-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.error-banner {
  padding: var(--spacing-md) var(--spacing-lg);
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
  border-left: 3px solid var(--color-danger);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-lg);
}

.notice-banner {
  padding: var(--spacing-md) var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
  background: var(--color-success-bg);
  color: var(--color-success);
  border-left: 3px solid var(--color-success);
  border-radius: var(--radius-md);
}

.trade-confirmation {
  margin: var(--spacing-sm) 0 0;
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
}
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-line);
  border-top-color: var(--color-accent);
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
  margin-bottom: var(--spacing-md);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.content-grid {
  display: grid;
  gap: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0 0 var(--spacing-lg) 0;
}

/* Account Summary */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--spacing-lg);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.summary-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.summary-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.summary-value.secondary {
  color: var(--color-ink-soft);
}

.summary-value.profit {
  color: var(--color-up);
}

.summary-value.loss {
  color: var(--color-down);
}

/* Tables */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.data-table th {
  text-align: left;
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--color-surface-muted);
  color: var(--color-ink-soft);
  font-weight: var(--font-weight-medium);
  border-bottom: 1px solid var(--color-line);
}

.data-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
  color: var(--color-ink);
}

.data-table tbody tr:hover {
  background-color: var(--color-surface-muted);
}

.data-table .align-right {
  text-align: right;
}

.data-table .code {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
}

.data-table .timestamp {
  color: var(--color-ink-soft);
  font-size: var(--font-size-xs);
}

.data-table .profit {
  color: var(--color-up);
  font-weight: var(--font-weight-medium);
}

.data-table .loss {
  color: var(--color-down);
  font-weight: var(--font-weight-medium);
}

.action-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.action-badge.buy {
  background-color: var(--color-success-bg);
  color: var(--color-up);
}

.action-badge.sell {
  background-color: var(--color-danger-bg);
  color: var(--color-down);
}

.status-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.status-badge.completed {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.pending {
  background-color: var(--color-warn-bg);
  color: var(--color-warn);
}

.status-badge.failed {
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
}

/* Trade Form */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.toggle-group {
  display: flex;
  gap: var(--spacing-sm);
}

.toggle-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  height: var(--touch-target-min);
  padding: 0 var(--spacing-md);
  background-color: var(--color-surface-muted);
  color: var(--color-ink-soft);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.toggle-btn:hover {
  background-color: var(--color-surface-strong);
  border-color: var(--color-ink-faint);
}

.toggle-btn.active {
  background-color: var(--color-accent);
  color: var(--color-surface);
  border-color: var(--color-accent);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-base);
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .page-head {
    flex-direction: column;
    gap: var(--spacing-md);
  }

  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .table-container {
    font-size: var(--font-size-xs);
  }
}
</style>
