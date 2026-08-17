<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import BrokerDisableGuard from '../../components/guards/BrokerDisableGuard.vue'
import { GitBranch, Plus, Clock, AlertCircle, CheckCircle, XCircle, Ban } from 'lucide-vue-next'
import { getConditionalOrders, getOrderHistory, getMonitoringStatus } from '../../api/orders'
import type { ConditionalOrder, OrderExecution, OrderMonitoring } from '../../api/orders'
import { LIVE_TRADING_ENABLED } from '../../config/features'

const title = '条件单'
const description = '智能条件单设置与执行监控（仅模拟）'

const orders = ref<ConditionalOrder[]>([])
const history = ref<OrderExecution[]>([])
const monitoring = ref<OrderMonitoring | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const activeOrders = computed(() => orders.value.filter(o => o.status === 'active'))
const isLiveTradingDisabled = computed(() => !LIVE_TRADING_ENABLED)

const statusVariant = (status: string) => {
  switch (status) {
    case 'active': return 'info'
    case 'triggered': return 'success'
    case 'expired': return 'default'
    case 'cancelled': return 'default'
    case 'error': return 'danger'
    default: return 'default'
  }
}

const statusLabel = (status: string) => {
  const labels: Record<string, string> = {
    active: '监控中',
    triggered: '已触发',
    expired: '已过期',
    cancelled: '已取消',
    error: '错误',
  }
  return labels[status] || status
}

const conditionTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    price: '价格条件',
    time: '时间条件',
    technical: '技术指标',
    composite: '组合条件',
  }
  return labels[type] || type
}

const formatDateTime = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatTimeAgo = (dateStr: string) => {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)

  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

const loadData = async () => {
  loading.value = true
  error.value = null

  try {
    const [ordersData, historyData, monitoringData] = await Promise.all([
      getConditionalOrders(),
      getOrderHistory(),
      getMonitoringStatus(),
    ])

    orders.value = ordersData
    history.value = historyData
    monitoring.value = monitoringData
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载数据失败'
  } finally {
    loading.value = false
  }
}

const handleCreateOrder = () => {
  alert('实盘交易已禁用，无法创建条件单')
}

const handleCancelOrder = (orderId: string) => {
  alert('实盘交易已禁用，无法取消条件单')
}

onMounted(() => {
  loadData()
})</script>

<template>
  <BrokerDisableGuard />

  <div class="page-container">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <GitBranch :size="22" class="faint" />
    </div>

    <!-- Monitoring Status -->
    <BaseCard v-if="monitoring" padding="md" class="monitoring-card">
      <div class="monitoring-status">
        <div class="status-item">
          <Clock :size="20" class="status-icon" />
          <div>
            <div class="status-label">监控状态</div>
            <div class="status-value">
              <BaseTag :variant="monitoring.status === 'running' ? 'success' : 'danger'">
                {{ monitoring.status === 'running' ? '运行中' : '已暂停' }}
              </BaseTag>
            </div>
          </div>
        </div>
        <div class="status-item">
          <div>
            <div class="status-label">活跃订单</div>
            <div class="status-value">{{ monitoring.activeOrders }} 个</div>
          </div>
        </div>
        <div class="status-item">
          <div>
            <div class="status-label">上次检查</div>
            <div class="status-value">{{ formatTimeAgo(monitoring.lastCheckAt) }}</div>
          </div>
        </div>
        <div class="status-item">
          <div>
            <div class="status-label">下次检查</div>
            <div class="status-value">{{ formatTimeAgo(monitoring.nextCheckAt) }}</div>
          </div>
        </div>
      </div>
    </BaseCard>

    <!-- Active Orders -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>条件单列表</h2>
        <BaseButton
          variant="secondary"
          size="sm"
          :disabled="isLiveTradingDisabled"
          @click="handleCreateOrder"
          :title="isLiveTradingDisabled ? '实盘交易已禁用，仅支持模拟交易' : ''"
        >
          <Plus :size="16" />
          创建条件单
        </BaseButton>
      </div>

      <div v-if="loading" class="loading-state">加载中...</div>
      <div v-else-if="error" class="error-state">
        <AlertCircle :size="20" />
        {{ error }}
      </div>
      <div v-else-if="orders.length === 0" class="empty-state">
        暂无条件单
      </div>
      <div v-else class="orders-table">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>条件类型</th>
              <th>触发条件</th>
              <th>动作</th>
              <th>数量</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>最后检查</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td>
                <div class="symbol-cell">
                  <div class="symbol">{{ order.symbol }}</div>
                  <div v-if="order.name" class="name">{{ order.name }}</div>
                </div>
              </td>
              <td>
                <BaseTag size="sm" variant="default">
                  {{ conditionTypeLabel(order.conditionType) }}
                </BaseTag>
              </td>
              <td class="condition-cell">{{ order.condition }}</td>
              <td>
                <BaseTag size="sm" :variant="order.action === 'buy' ? 'success' : 'danger'">
                  {{ order.action === 'buy' ? '买入' : '卖出' }}
                </BaseTag>
              </td>
              <td>{{ order.quantity }}</td>
              <td>
                <BaseTag size="sm" :variant="statusVariant(order.status)">
                  {{ statusLabel(order.status) }}
                </BaseTag>
              </td>
              <td>{{ formatDateTime(order.createdAt) }}</td>
              <td>
                <span v-if="order.lastCheckAt" class="time-ago">
                  {{ formatTimeAgo(order.lastCheckAt) }}
                </span>
                <span v-else class="faint">-</span>
              </td>
              <td>
                <BaseButton
                  v-if="order.status === 'active'"
                  variant="ghost"
                  size="sm"
                  :disabled="isLiveTradingDisabled"
                  @click="handleCancelOrder(order.id)"
                  :title="isLiveTradingDisabled ? '实盘交易已禁用' : '取消订单'"
                >
                  <Ban :size="16" />
                </BaseButton>
                <span v-else class="faint">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseCard>

    <!-- Execution History -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>执行历史</h2>
      </div>

      <div v-if="history.length === 0" class="empty-state">
        暂无执行记录
      </div>
      <div v-else class="history-table">
        <table>
          <thead>
            <tr>
              <th>订单ID</th>
              <th>标的</th>
              <th>动作</th>
              <th>数量</th>
              <th>价格</th>
              <th>执行时间</th>
              <th>状态</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="exec in history" :key="`${exec.orderId}-${exec.executedAt}`">
              <td class="order-id">{{ exec.orderId }}</td>
              <td>{{ exec.symbol }}</td>
              <td>
                <BaseTag size="sm" :variant="exec.action === 'buy' ? 'success' : 'danger'">
                  {{ exec.action === 'buy' ? '买入' : '卖出' }}
                </BaseTag>
              </td>
              <td>{{ exec.quantity }}</td>
              <td class="price">¥{{ exec.price.toFixed(2) }}</td>
              <td>{{ formatDateTime(exec.executedAt) }}</td>
              <td>
                <div class="execution-status">
                  <CheckCircle v-if="exec.success" :size="16" class="success-icon" />
                  <XCircle v-else :size="16" class="error-icon" />
                  <span>{{ exec.success ? '成功' : '失败' }}</span>
                </div>
              </td>
              <td class="message-cell">{{ exec.message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseCard>

    <!-- Warning Banner -->
    <BaseCard v-if="isLiveTradingDisabled" padding="md" class="warning-banner">
      <div class="warning-content">
        <AlertCircle :size="20" />
        <div>
          <strong>实盘交易已禁用</strong>
          <p>本页面展示的是模拟数据，所有交易功能已被禁用。系统不支持真实券商连接和实盘交易。</p>
        </div>
      </div>
    </BaseCard>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1400px;
  margin: 0 auto;
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

.faint {
  color: var(--color-ink-faint);
}

/* Monitoring Status */
.monitoring-card {
  margin-bottom: var(--spacing-lg);
}

.monitoring-status {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-lg);
}

.status-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.status-icon {
  color: var(--color-accent);
}

.status-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin-bottom: var(--spacing-xs);
}

.status-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

/* Card Header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.card-header h2 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

/* States */
.loading-state,
.error-state,
.empty-state {
  padding: var(--spacing-2xl);
  text-align: center;
  color: var(--color-ink-soft);
}

.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  color: var(--color-danger);
}

/* Tables */
.orders-table,
.history-table {
  overflow-x: auto;
  margin-bottom: var(--spacing-lg);
}

table {
  width: 100%;
  border-collapse: collapse;
}

thead {
  background-color: var(--color-surface-muted);
}

th {
  padding: var(--spacing-md);
  text-align: left;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  border-bottom: 1px solid var(--color-line);
}

td {
  padding: var(--spacing-md);
  font-size: var(--font-size-base);
  color: var(--color-ink);
  border-bottom: 1px solid var(--color-line);
}

tbody tr:hover {
  background-color: var(--color-surface-muted);
}

.symbol-cell {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.symbol {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.name {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.condition-cell {
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time-ago {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.order-id {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.price {
  font-family: var(--font-family-mono);
  font-weight: var(--font-weight-medium);
}

.execution-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.success-icon {
  color: var(--color-success);
}

.error-icon {
  color: var(--color-danger);
}

.message-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

/* Warning Banner */
.warning-banner {
  margin-top: var(--spacing-lg);
  background-color: var(--color-warn-bg);
  border: 1px solid var(--color-warn);
}

.warning-content {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  color: var(--color-warn);
}

.warning-content strong {
  display: block;
  margin-bottom: var(--spacing-xs);
  color: var(--color-ink);
}

.warning-content p {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  line-height: var(--line-height-relaxed);
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .page-head h1 {
    font-size: var(--font-size-xl);
  }

  .monitoring-status {
    grid-template-columns: 1fr;
  }

  .orders-table,
  .history-table {
    font-size: var(--font-size-sm);
  }

  th,
  td {
    padding: var(--spacing-sm);
  }
}
</style>
