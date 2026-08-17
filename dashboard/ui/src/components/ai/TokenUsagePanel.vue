<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { X, Download, RefreshCw, TrendingUp, DollarSign, Activity, Sparkles } from 'lucide-vue-next'
import BaseCard from '../base/BaseCard.vue'
import BaseButton from '../base/BaseButton.vue'
import { useTokenUsage } from '../../composables/useTokenUsage'
import type { TokenUsageRecord } from '../../composables/useTokenUsage'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const tokenUsage = useTokenUsage()

// Get today's usage
const todayUsage = computed(() => {
  const records = tokenUsage.getTodayUsage()
  const totalTokens = records.reduce((sum, r) => sum + r.inputTokens + r.outputTokens, 0)
  const totalCost = records.reduce((sum, r) => sum + r.cost, 0)
  return {
    tokens: totalTokens,
    cost: totalCost,
    requests: records.length
  }
})

// Get last 7 days usage for chart
const last7DaysUsage = computed(() => {
  const days: { date: string; tokens: number; label: string }[] = []
  const now = new Date()

  for (let i = 6; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    date.setHours(0, 0, 0, 0)

    const nextDate = new Date(date)
    nextDate.setDate(nextDate.getDate() + 1)

    const records = tokenUsage.getUsageInRange(date.getTime(), nextDate.getTime())
    const totalTokens = records.reduce((sum, r) => sum + r.inputTokens + r.outputTokens, 0)

    days.push({
      date: date.toISOString().split('T')[0],
      tokens: totalTokens,
      label: date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
    })
  }

  return days
})

// Calculate max for chart scaling
const maxTokens = computed(() => {
  const max = Math.max(...last7DaysUsage.value.map(d => d.tokens), 1)
  return max
})

// Model breakdown with percentage
const modelBreakdown = computed(() => {
  const byModel = tokenUsage.usageByModel.value
  const totalCost = tokenUsage.totalCost.value

  return Object.entries(byModel)
    .map(([model, stats]) => ({
      model,
      ...stats,
      percentage: totalCost > 0 ? (stats.cost / totalCost) * 100 : 0
    }))
    .sort((a, b) => b.cost - a.cost)
})

// Recent requests (last 20)
const recentRequests = computed(() => {
  return [...tokenUsage.usageHistory.value]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 20)
})

// Format helpers
const formatNumber = (num: number) => {
  return new Intl.NumberFormat('zh-CN').format(num)
}

const formatCurrency = (amount: number) => {
  return `¥${amount.toFixed(4)}`
}

const formatRelativeTime = (timestamp: number) => {
  const now = Date.now()
  const diff = now - timestamp
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  return `${days}天前`
}

// Export CSV
const exportCSV = () => {
  const headers = ['日期时间', '模型', '输入Token', '输出Token', '总Token', '成本']
  const rows = tokenUsage.usageHistory.value.map(record => [
    new Date(record.timestamp).toLocaleString('zh-CN'),
    record.model,
    record.inputTokens.toString(),
    record.outputTokens.toString(),
    (record.inputTokens + record.outputTokens).toString(),
    record.cost.toFixed(6)
  ])

  const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `token-usage-${new Date().toISOString().split('T')[0]}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

// Export JSON
const exportJSON = () => {
  const data = tokenUsage.exportData()
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `token-usage-${new Date().toISOString().split('T')[0]}.json`
  link.click()
  URL.revokeObjectURL(url)
}

// Reset with confirmation
const handleReset = () => {
  if (confirm('确定要清空所有 Token 使用记录吗？此操作不可恢复。')) {
    tokenUsage.reset()
  }
}

// Keyboard shortcut
const handleKeydown = (e: KeyboardEvent) => {
  if (e.ctrlKey && e.shiftKey && e.key === 'T') {
    e.preventDefault()
    emit('close')
  }

  if (e.key === 'Escape' && props.open) {
    emit('close')
  }
}

// Click outside to close
const panelRef = ref<HTMLElement | null>(null)
const handleClickOutside = (e: MouseEvent) => {
  if (props.open && panelRef.value && !panelRef.value.contains(e.target as Node)) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('mousedown', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('mousedown', handleClickOutside)
})
</script>

<template>
  <Transition name="panel">
    <div v-if="open" class="panel-overlay">
      <aside ref="panelRef" class="token-usage-panel">
        <!-- Header -->
        <div class="panel-header">
          <div class="panel-title">
            <Sparkles :size="20" />
            <h2>Token 用量</h2>
          </div>
          <button class="close-btn" @click="$emit('close')" title="关闭 (Esc)">
            <X :size="20" />
          </button>
        </div>

        <!-- Content -->
        <div class="panel-content">
          <!-- Quick Summary -->
          <BaseCard padding="md" class="summary-card">
            <h3 class="section-title">今日统计</h3>
            <div class="summary-grid">
              <div class="summary-item">
                <Activity :size="18" class="summary-icon primary" />
                <div class="summary-details">
                  <div class="summary-label">请求数</div>
                  <div class="summary-value">{{ formatNumber(todayUsage.requests) }}</div>
                </div>
              </div>
              <div class="summary-item">
                <TrendingUp :size="18" class="summary-icon success" />
                <div class="summary-details">
                  <div class="summary-label">Token</div>
                  <div class="summary-value">{{ formatNumber(todayUsage.tokens) }}</div>
                </div>
              </div>
              <div class="summary-item">
                <DollarSign :size="18" class="summary-icon warning" />
                <div class="summary-details">
                  <div class="summary-label">成本</div>
                  <div class="summary-value">{{ formatCurrency(todayUsage.cost) }}</div>
                </div>
              </div>
            </div>
          </BaseCard>

          <!-- Usage Chart -->
          <BaseCard padding="md" class="chart-card">
            <h3 class="section-title">最近 7 天</h3>
            <div v-if="last7DaysUsage.some(d => d.tokens > 0)" class="chart">
              <div class="chart-bars">
                <div
                  v-for="day in last7DaysUsage"
                  :key="day.date"
                  class="chart-bar-container"
                  :title="`${day.label}: ${formatNumber(day.tokens)} tokens`"
                >
                  <div class="chart-bar-wrapper">
                    <div
                      class="chart-bar"
                      :style="{ height: `${(day.tokens / maxTokens) * 100}%` }"
                    ></div>
                  </div>
                  <div class="chart-label">{{ day.label }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>暂无数据</p>
            </div>
          </BaseCard>

          <!-- Model Breakdown -->
          <BaseCard padding="md" class="breakdown-card">
            <h3 class="section-title">模型统计</h3>
            <div v-if="modelBreakdown.length > 0" class="breakdown-table">
              <div class="breakdown-header">
                <div class="col-model">模型</div>
                <div class="col-tokens">Token</div>
                <div class="col-cost">成本</div>
                <div class="col-percentage">占比</div>
              </div>
              <div
                v-for="item in modelBreakdown"
                :key="item.model"
                class="breakdown-row"
              >
                <div class="col-model">
                  <div class="model-name">{{ item.model }}</div>
                  <div class="model-count">{{ item.count }} 次</div>
                </div>
                <div class="col-tokens">
                  <div class="token-detail">{{ formatNumber(item.totalTokens) }}</div>
                  <div class="token-split">
                    <span class="token-in">↓{{ formatNumber(item.inputTokens) }}</span>
                    <span class="token-out">↑{{ formatNumber(item.outputTokens) }}</span>
                  </div>
                </div>
                <div class="col-cost">{{ formatCurrency(item.cost) }}</div>
                <div class="col-percentage">
                  <div class="percentage-bar">
                    <div class="percentage-fill" :style="{ width: `${item.percentage}%` }"></div>
                  </div>
                  <span class="percentage-text">{{ item.percentage.toFixed(1) }}%</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>暂无记录</p>
            </div>
          </BaseCard>

          <!-- Recent Requests -->
          <BaseCard padding="md" class="requests-card">
            <h3 class="section-title">最近请求</h3>
            <div v-if="recentRequests.length > 0" class="requests-list">
              <div
                v-for="record in recentRequests"
                :key="record.id"
                class="request-item"
              >
                <div class="request-time">{{ formatRelativeTime(record.timestamp) }}</div>
                <div class="request-details">
                  <div class="request-model">{{ record.model }}</div>
                  <div class="request-tokens">
                    {{ formatNumber(record.inputTokens + record.outputTokens) }} tokens
                    <span class="request-cost">{{ formatCurrency(record.cost) }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>暂无记录</p>
            </div>
          </BaseCard>
        </div>

        <!-- Footer Actions -->
        <div class="panel-footer">
          <div class="footer-actions">
            <BaseButton variant="secondary" size="sm" @click="exportCSV">
              <Download :size="16" />
              导出 CSV
            </BaseButton>
            <BaseButton variant="secondary" size="sm" @click="exportJSON">
              <Download :size="16" />
              导出 JSON
            </BaseButton>
            <BaseButton variant="danger" size="sm" @click="handleReset">
              <RefreshCw :size="16" />
              清空记录
            </BaseButton>
          </div>
          <div class="footer-hint">
            <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>T</kbd> 切换面板
          </div>
        </div>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.panel-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
}

.token-usage-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 420px;
  max-width: 100vw;
  background: var(--color-surface);
  border-left: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

/* Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-line);
  background: var(--color-surface);
  position: sticky;
  top: 0;
  z-index: 10;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--color-accent);
}

.panel-title h2 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs);
  color: var(--color-ink-soft);
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.close-btn:hover {
  background: var(--color-surface-muted);
  color: var(--color-ink);
}

/* Content */
.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 var(--spacing-md) 0;
}

/* Summary Card */
.summary-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm);
  background: var(--color-surface-muted);
  border-radius: var(--radius-md);
}

.summary-icon {
  flex-shrink: 0;
}

.summary-icon.primary {
  color: var(--color-accent);
}

.summary-icon.success {
  color: var(--color-success);
}

.summary-icon.warning {
  color: var(--color-warn);
}

.summary-details {
  flex: 1;
}

.summary-label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
  margin-bottom: var(--spacing-xs);
}

.summary-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

/* Chart */
.chart {
  height: 160px;
  padding: var(--spacing-md) 0;
}

.chart-bars {
  height: 100%;
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-xs);
}

.chart-bar-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  cursor: pointer;
}

.chart-bar-wrapper {
  width: 100%;
  height: 120px;
  display: flex;
  align-items: flex-end;
}

.chart-bar {
  width: 100%;
  min-height: 2px;
  background: var(--color-accent);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  transition: all var(--duration-normal) var(--ease-smooth);
}

.chart-bar-container:hover .chart-bar {
  opacity: 0.8;
}

.chart-label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

/* Breakdown Table */
.breakdown-table {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.breakdown-header {
  display: grid;
  grid-template-columns: 2fr 1.5fr 1fr 1.5fr;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.breakdown-row {
  display: grid;
  grid-template-columns: 2fr 1.5fr 1fr 1.5fr;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-xs);
  background: var(--color-surface-muted);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  align-items: center;
}

.col-model {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.model-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.model-count {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.col-tokens {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.token-detail {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.token-split {
  display: flex;
  gap: var(--spacing-xs);
  font-size: var(--font-size-xs);
}

.token-in {
  color: var(--color-success);
}

.token-out {
  color: var(--color-accent);
}

.col-cost {
  font-weight: var(--font-weight-medium);
  color: var(--color-warn);
}

.col-percentage {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.percentage-bar {
  width: 100%;
  height: 4px;
  background: var(--color-surface-strong);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.percentage-fill {
  height: 100%;
  background: var(--color-accent);
  transition: width var(--duration-normal) var(--ease-smooth);
}

.percentage-text {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
  text-align: right;
}

/* Requests List */
.requests-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  max-height: 400px;
  overflow-y: auto;
}

.request-item {
  display: flex;
  gap: var(--spacing-md);
  padding: var(--spacing-sm);
  background: var(--color-surface-muted);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.request-time {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
  min-width: 60px;
}

.request-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.request-model {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.request-tokens {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.request-cost {
  margin-left: var(--spacing-xs);
  color: var(--color-warn);
  font-weight: var(--font-weight-medium);
}

/* Footer */
.panel-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-line);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.footer-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.footer-hint {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
  text-align: center;
}

.footer-hint kbd {
  padding: 2px 6px;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
}

/* Empty State */
.empty-state {
  padding: var(--spacing-2xl);
  text-align: center;
  color: var(--color-ink-soft);
}

.empty-state p {
  margin: 0;
  font-size: var(--font-size-sm);
}

/* Transitions */
.panel-enter-active,
.panel-leave-active {
  transition: opacity var(--duration-normal) var(--ease-smooth);
}

.panel-enter-active .token-usage-panel,
.panel-leave-active .token-usage-panel {
  transition: transform var(--duration-normal) var(--ease-smooth);
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.panel-enter-from .token-usage-panel {
  transform: translateX(100%);
}

.panel-leave-to .token-usage-panel {
  transform: translateX(100%);
}

/* Mobile */
@media (max-width: 768px) {
  .token-usage-panel {
    width: 100vw;
    border-left: none;
  }

  .breakdown-header {
    font-size: 10px;
  }

  .breakdown-row {
    font-size: var(--font-size-xs);
  }

  .footer-actions {
    flex-direction: column;
  }

  .footer-actions button {
    width: 100%;
  }
}
</style>
