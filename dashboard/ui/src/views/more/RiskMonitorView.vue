<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import { Shield, RefreshCw, TrendingUp, AlertCircle, Bell, BellOff } from 'lucide-vue-next'
import { getRiskMonitor } from '../../api/risk'
import type { RiskMonitorData } from '../../api/risk'

const title = '风险监控'
const description = '实时风险指标监控与预警系统'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const riskData = ref<RiskMonitorData | null>(null)

// Computed
const riskScoreLevel = computed(() => {
  if (!riskData.value) return 'low'
  const score = riskData.value.dashboard.risk_score
  if (score > 70) return 'high'
  if (score > 40) return 'medium'
  return 'low'
})

const riskScoreColor = computed(() => {
  const level = riskScoreLevel.value
  if (level === 'high') return 'var(--color-danger)'
  if (level === 'medium') return 'var(--color-warn)'
  return 'var(--color-success)'
})

// Methods
async function loadData() {
  loading.value = true
  error.value = null

  try {
    riskData.value = await getRiskMonitor()
  } catch (err) {
    console.error('Failed to load risk monitor data:', err)
    error.value = '加载数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(num: number): string {
  return num.toFixed(1) + '%'
}

function formatDateTime(iso?: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getRiskLevelVariant(level: string) {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'success'
}

function getRiskLevelText(level: string) {
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  return '低风险'
}

function getAlertStatusVariant(status: string) {
  if (status === 'triggered') return 'danger'
  if (status === 'active') return 'success'
  return 'default'
}

function getAlertStatusText(status: string) {
  if (status === 'triggered') return '已触发'
  if (status === 'active') return '活动中'
  return '已停用'
}

function handleAddAlert() {
  alert('添加预警规则功能开发中')
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="page-container">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <div class="head-actions">
        <BaseButton
          variant="secondary"
          size="sm"
          :disabled="true"
          @click="handleAddAlert"
        >
          <AlertCircle :size="16" />
          添加预警（开发中）
        </BaseButton>
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

    <!-- Error State -->
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <!-- Loading State -->
    <div v-if="loading && !riskData" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="riskData" class="content-grid">
      <!-- Risk Dashboard -->
      <div class="dashboard-grid">
        <BaseCard padding="lg" class="risk-score-card">
          <div class="risk-score-content">
            <div class="score-circle" :style="{ borderColor: riskScoreColor }">
              <div class="score-value" :style="{ color: riskScoreColor }">
                {{ riskData.dashboard.risk_score }}
              </div>
              <div class="score-label">风险评分</div>
            </div>
            <div class="score-info">
              <BaseTag :variant="getRiskLevelVariant(riskScoreLevel)" size="lg">
                {{ getRiskLevelText(riskScoreLevel) }}
              </BaseTag>
              <p class="score-desc">0-30: 低风险 | 31-70: 中风险 | 71-100: 高风险</p>
            </div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <div class="metric-item">
            <div class="metric-label">集中度风险</div>
            <div class="metric-value">{{ riskData.dashboard.concentration_risk }}</div>
            <div class="metric-bar">
              <div
                class="metric-bar-fill"
                :style="{ width: riskData.dashboard.concentration_risk + '%' }"
              ></div>
            </div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <div class="metric-item">
            <div class="metric-label">波动率</div>
            <div class="metric-value">{{ formatPercent(riskData.dashboard.volatility) }}</div>
            <div class="metric-note">年化波动率</div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <div class="metric-item">
            <div class="metric-label">VaR (95%)</div>
            <div class="metric-value negative">¥{{ formatNumber(riskData.dashboard.var_95) }}</div>
            <div class="metric-note">单日最大可能损失</div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <div class="metric-item">
            <div class="metric-label">流动性风险</div>
            <div class="metric-value">
              <BaseTag :variant="getRiskLevelVariant(riskData.dashboard.liquidity_risk)" size="md">
                {{ getRiskLevelText(riskData.dashboard.liquidity_risk) }}
              </BaseTag>
            </div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <div class="metric-item">
            <div class="metric-label">市场敞口</div>
            <div class="metric-value">{{ riskData.dashboard.market_exposure.toFixed(2) }}</div>
            <div class="metric-note">Beta 加权</div>
          </div>
        </BaseCard>
      </div>

      <!-- Alert Rules -->
      <BaseCard padding="lg">
        <h2 class="section-title">预警规则</h2>
        <div v-if="riskData.alert_rules.length === 0" class="empty-state">
          暂无预警规则
        </div>
        <div v-else class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>规则名称</th>
                <th>触发条件</th>
                <th>状态</th>
                <th class="align-right">触发次数</th>
                <th>最后触发</th>
                <th>通知方式</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in riskData.alert_rules" :key="rule.id">
                <td class="rule-name">{{ rule.name }}</td>
                <td class="rule-condition">{{ rule.condition }}</td>
                <td>
                  <BaseTag :variant="getAlertStatusVariant(rule.status)" size="sm">
                    {{ getAlertStatusText(rule.status) }}
                  </BaseTag>
                </td>
                <td class="align-right">{{ rule.trigger_count }}</td>
                <td class="timestamp">{{ formatDateTime(rule.last_triggered) }}</td>
                <td>
                  <div class="actions-list">
                    <span v-for="action in rule.actions" :key="action" class="action-tag">
                      {{ action }}
                    </span>
                  </div>
                </td>
                <td>
                  <BaseButton variant="ghost" size="sm" :disabled="true">
                    编辑
                  </BaseButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </BaseCard>

      <!-- Risk Breakdown -->
      <div class="breakdown-grid">
        <BaseCard padding="lg">
          <h2 class="section-title">行业风险分布</h2>
          <div class="breakdown-list">
            <div
              v-for="item in riskData.breakdowns.by_sector"
              :key="item.category"
              class="breakdown-item"
            >
              <div class="breakdown-header">
                <span class="breakdown-name">{{ item.category }}</span>
                <BaseTag :variant="getRiskLevelVariant(item.risk_level)" size="sm">
                  {{ getRiskLevelText(item.risk_level) }}
                </BaseTag>
              </div>
              <div class="breakdown-bar">
                <div
                  class="breakdown-bar-fill"
                  :class="item.risk_level"
                  :style="{ width: item.percentage + '%' }"
                ></div>
              </div>
              <div class="breakdown-stats">
                <span class="breakdown-percent">{{ formatPercent(item.percentage) }}</span>
                <span class="breakdown-value">¥{{ formatNumber(item.value) }}</span>
              </div>
            </div>
          </div>
        </BaseCard>

        <BaseCard padding="lg">
          <h2 class="section-title">持仓风险分布</h2>
          <div class="breakdown-list">
            <div
              v-for="item in riskData.breakdowns.by_position"
              :key="item.category"
              class="breakdown-item"
            >
              <div class="breakdown-header">
                <span class="breakdown-name">{{ item.category }}</span>
                <BaseTag :variant="getRiskLevelVariant(item.risk_level)" size="sm">
                  {{ getRiskLevelText(item.risk_level) }}
                </BaseTag>
              </div>
              <div class="breakdown-bar">
                <div
                  class="breakdown-bar-fill"
                  :class="item.risk_level"
                  :style="{ width: item.percentage + '%' }"
                ></div>
              </div>
              <div class="breakdown-stats">
                <span class="breakdown-percent">{{ formatPercent(item.percentage) }}</span>
                <span class="breakdown-value">¥{{ formatNumber(item.value) }}</span>
              </div>
            </div>
          </div>
        </BaseCard>
      </div>

      <!-- Historical Risk Chart -->
      <BaseCard padding="lg">
        <h2 class="section-title">历史风险趋势</h2>
        <div class="chart-placeholder">
          <TrendingUp :size="48" class="chart-icon" />
          <p class="chart-label">历史风险走势图</p>
          <p class="chart-note">图表可视化功能开发中</p>
          <p class="chart-hint">已加载 {{ riskData.history.length }} 个数据点</p>
        </div>
      </BaseCard>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      暂无数据
    </div>
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

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--spacing-lg);
}

.risk-score-card {
  grid-column: span 2;
}

.risk-score-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-xl);
}

.score-circle {
  width: 140px;
  height: 140px;
  border-radius: var(--radius-full);
  border: 8px solid;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.score-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  line-height: 1;
}

.score-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin-top: var(--spacing-xs);
}

.score-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.score-desc {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: 0;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.metric-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.metric-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.metric-value.negative {
  color: var(--color-danger);
}

.metric-note {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
}

.metric-bar {
  height: 8px;
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  background: linear-gradient(to right, var(--color-success), var(--color-warn), var(--color-danger));
  border-radius: var(--radius-full);
  transition: width var(--duration-normal) var(--ease-smooth);
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

.data-table .rule-name {
  font-weight: var(--font-weight-medium);
}

.data-table .rule-condition {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.data-table .timestamp {
  color: var(--color-ink-soft);
  font-size: var(--font-size-xs);
}

.actions-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.action-tag {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  background-color: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

/* Breakdown */
.breakdown-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-lg);
}

.breakdown-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.breakdown-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.breakdown-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.breakdown-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.breakdown-bar {
  height: 24px;
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.breakdown-bar-fill {
  height: 100%;
  border-radius: var(--radius-sm);
  transition: width var(--duration-normal) var(--ease-smooth);
}

.breakdown-bar-fill.low {
  background-color: var(--color-success);
}

.breakdown-bar-fill.medium {
  background-color: var(--color-warn);
}

.breakdown-bar-fill.high {
  background-color: var(--color-danger);
}

.breakdown-stats {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
}

.breakdown-percent {
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.breakdown-value {
  color: var(--color-ink-soft);
}

/* Chart Placeholder */
.chart-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  border: 2px dashed var(--color-line);
  border-radius: var(--radius-md);
  text-align: center;
}

.chart-icon {
  color: var(--color-ink-faint);
  margin-bottom: var(--spacing-md);
}

.chart-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  margin: 0 0 var(--spacing-xs) 0;
}

.chart-note {
  font-size: var(--font-size-sm);
  color: var(--color-ink-faint);
  margin: 0 0 var(--spacing-sm) 0;
}

.chart-hint {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
  margin: 0;
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

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .risk-score-card {
    grid-column: span 1;
  }

  .risk-score-content {
    flex-direction: column;
    text-align: center;
  }

  .breakdown-grid {
    grid-template-columns: 1fr;
  }
}
</style>
