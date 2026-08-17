<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import { Settings, Activity, DollarSign, Key, TrendingUp, AlertCircle, CheckCircle, XCircle } from 'lucide-vue-next'
import { useTokenUsage } from '../../composables/useTokenUsage'
import {
  getAIRuntimeStatus,
  getModelConfigs,
  getTokenUsageHistory,
  getCostBreakdown,
  getApiKeys,
} from '../../api/aiRuntime'
import type {
  AIRuntimeStatus,
  ModelConfig,
  TokenUsageData,
  CostBreakdown,
  ApiKey,
} from '../../api/aiRuntime'
import { LIVE_TRADING_ENABLED } from '../../config/features'

const title = 'AI Runtime 配置'
const description = 'AI 模型、Provider 与 Token 使用管理'

// Composable usage
const tokenUsage = useTokenUsage()

// API data
const runtimeStatus = ref<AIRuntimeStatus | null>(null)
const modelConfigs = ref<ModelConfig[]>([])
const usageHistory = ref<TokenUsageData[]>([])
const costBreakdown = ref<CostBreakdown[]>([])
const apiKeys = ref<ApiKey[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const isLiveTradingDisabled = computed(() => !LIVE_TRADING_ENABLED)

const statusColor = (status: string) => {
  switch (status) {
    case 'online': return 'success'
    case 'degraded': return 'warning'
    case 'offline': return 'danger'
    default: return 'default'
  }
}

const apiKeyStatusColor = (status: string) => {
  switch (status) {
    case 'valid': return 'success'
    case 'invalid': return 'danger'
    case 'expired': return 'warning'
    case 'not-set': return 'default'
    default: return 'default'
  }
}

const statusLabel = (status: string) => {
  const labels: Record<string, string> = {
    online: '在线',
    degraded: '降级',
    offline: '离线',
  }
  return labels[status] || status
}

const apiKeyStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    valid: '有效',
    invalid: '无效',
    expired: '已过期',
    'not-set': '未设置',
  }
  return labels[status] || status
}

const providerLabel = (provider: string) => {
  const labels: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    azure: 'Azure',
    custom: '自定义',
  }
  return labels[provider] || provider
}

const formatNumber = (num: number) => {
  return new Intl.NumberFormat('zh-CN').format(num)
}

const formatCurrency = (amount: number) => {
  return `¥${amount.toFixed(2)}`
}

const formatDateTime = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const loadData = async () => {
  loading.value = true
  error.value = null

  try {
    const [status, models, history, costs, keys] = await Promise.all([
      getAIRuntimeStatus(),
      getModelConfigs(),
      getTokenUsageHistory(30),
      getCostBreakdown(),
      getApiKeys(),
    ])

    runtimeStatus.value = status
    modelConfigs.value = models
    usageHistory.value = history
    costBreakdown.value = costs
    apiKeys.value = keys
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载数据失败'
  } finally {
    loading.value = false
  }
}

const handleTestConnection = (provider: string) => {
  alert('API 密钥测试功能已禁用')
}

const handleUpdateApiKey = (provider: string) => {
  alert('API 密钥修改功能已禁用')
}

const handleExportUsage = () => {
  const data = tokenUsage.exportData()
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `token-usage-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadData()
})</script>

<template>
  <div class="page-container">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <Settings :size="22" class="faint" />
    </div>

    <!-- Runtime Status Overview -->
    <div v-if="runtimeStatus" class="status-grid">
      <BaseCard padding="md">
        <div class="stat-card">
          <Activity :size="24" class="stat-icon primary" />
          <div class="stat-content">
            <div class="stat-label">总请求数</div>
            <div class="stat-value">{{ formatNumber(runtimeStatus.totalRequests) }}</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard padding="md">
        <div class="stat-card">
          <TrendingUp :size="24" class="stat-icon success" />
          <div class="stat-content">
            <div class="stat-label">Token 使用量</div>
            <div class="stat-value">{{ formatNumber(runtimeStatus.totalTokens) }}</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard padding="md">
        <div class="stat-card">
          <DollarSign :size="24" class="stat-icon warning" />
          <div class="stat-content">
            <div class="stat-label">总成本</div>
            <div class="stat-value">{{ formatCurrency(runtimeStatus.totalCost) }}</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard padding="md">
        <div class="stat-card">
          <CheckCircle :size="24" :class="['stat-icon', runtimeStatus.healthStatus === 'healthy' ? 'success' : 'danger']" />
          <div class="stat-content">
            <div class="stat-label">健康状态</div>
            <div class="stat-value">
              <BaseTag :variant="runtimeStatus.healthStatus === 'healthy' ? 'success' : 'danger'">
                {{ runtimeStatus.healthStatus === 'healthy' ? '正常' : '异常' }}
              </BaseTag>
            </div>
          </div>
        </div>
      </BaseCard>
    </div>

    <!-- Token Usage from Composable -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>Token 使用追踪（本地）</h2>
        <BaseButton variant="secondary" size="sm" @click="handleExportUsage">
          导出数据
        </BaseButton>
      </div>

      <div class="usage-summary">
        <div class="usage-item">
          <div class="usage-label">输入 Token</div>
          <div class="usage-value">{{ formatNumber(tokenUsage.totalInputTokens.value) }}</div>
        </div>
        <div class="usage-item">
          <div class="usage-label">输出 Token</div>
          <div class="usage-value">{{ formatNumber(tokenUsage.totalOutputTokens.value) }}</div>
        </div>
        <div class="usage-item">
          <div class="usage-label">总计</div>
          <div class="usage-value primary">{{ formatNumber(tokenUsage.totalTokens.value) }}</div>
        </div>
        <div class="usage-item">
          <div class="usage-label">预估成本</div>
          <div class="usage-value warning">{{ formatCurrency(tokenUsage.totalCost.value) }}</div>
        </div>
      </div>

      <div v-if="Object.keys(tokenUsage.usageByModel.value).length > 0" class="model-breakdown">
        <h3>按模型统计</h3>
        <div class="model-grid">
          <div v-for="(stats, model) in tokenUsage.usageByModel.value" :key="model" class="model-stat">
            <div class="model-name">{{ model }}</div>
            <div class="model-details">
              <span>{{ formatNumber(stats.totalTokens) }} tokens</span>
              <span class="dot">•</span>
              <span>{{ formatCurrency(stats.cost) }}</span>
              <span class="dot">•</span>
              <span>{{ stats.count }} 次请求</span>
            </div>
          </div>
        </div>
      </div>
    </BaseCard>

    <!-- Model Configurations -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>模型配置</h2>
      </div>

      <div v-if="loading" class="loading-state">加载中...</div>
      <div v-else-if="error" class="error-state">
        <AlertCircle :size="20" />
        {{ error }}
      </div>
      <div v-else-if="modelConfigs.length === 0" class="empty-state">
        暂无模型配置
      </div>
      <div v-else class="models-grid">
        <div v-for="model in modelConfigs" :key="model.id" class="model-card">
          <div class="model-card-header">
            <div>
              <h3>{{ model.name }}</h3>
              <BaseTag size="sm" variant="default">{{ providerLabel(model.provider) }}</BaseTag>
            </div>
            <BaseTag :variant="statusColor(model.status)">
              {{ statusLabel(model.status) }}
            </BaseTag>
          </div>

          <div class="model-stats">
            <div class="model-stat-item">
              <span class="label">今日请求</span>
              <span class="value">{{ formatNumber(model.requestsToday) }}</span>
            </div>
            <div class="model-stat-item">
              <span class="label">今日 Token</span>
              <span class="value">{{ formatNumber(model.tokensToday) }}</span>
            </div>
            <div class="model-stat-item">
              <span class="label">今日成本</span>
              <span class="value">{{ formatCurrency(model.costToday) }}</span>
            </div>
          </div>

          <div class="model-info">
            <div class="info-row">
              <span class="label">模型 ID:</span>
              <span class="value mono">{{ model.modelId }}</span>
            </div>
            <div class="info-row">
              <span class="label">API 状态:</span>
              <BaseTag size="sm" :variant="apiKeyStatusColor(model.apiKeyStatus)">
                {{ apiKeyStatusLabel(model.apiKeyStatus) }}
              </BaseTag>
            </div>
            <div v-if="model.lastUsedAt" class="info-row">
              <span class="label">最后使用:</span>
              <span class="value">{{ formatDateTime(model.lastUsedAt) }}</span>
            </div>
          </div>

          <div v-if="model.metadata?.degradedReason" class="degraded-notice">
            <AlertCircle :size="16" />
            <span>{{ model.metadata.degradedReason }}</span>
          </div>
        </div>
      </div>
    </BaseCard>

    <!-- Cost Breakdown -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>成本分析</h2>
      </div>

      <div v-if="costBreakdown.length === 0" class="empty-state">
        暂无成本数据
      </div>
      <div v-else class="cost-table">
        <table>
          <thead>
            <tr>
              <th>模型</th>
              <th>Provider</th>
              <th>输入 Token</th>
              <th>输出 Token</th>
              <th>总 Token</th>
              <th>请求数</th>
              <th>成本</th>
              <th>占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cost in costBreakdown" :key="cost.model">
              <td class="model-name">{{ cost.model }}</td>
              <td>
                <BaseTag size="sm" variant="default">
                  {{ providerLabel(cost.provider) }}
                </BaseTag>
              </td>
              <td>{{ formatNumber(cost.inputTokens) }}</td>
              <td>{{ formatNumber(cost.outputTokens) }}</td>
              <td class="total-tokens">{{ formatNumber(cost.totalTokens) }}</td>
              <td>{{ formatNumber(cost.requests) }}</td>
              <td class="cost">{{ formatCurrency(cost.cost) }}</td>
              <td>
                <div class="percentage-cell">
                  <div class="percentage-bar">
                    <div class="percentage-fill" :style="{ width: `${cost.percentage}%` }"></div>
                  </div>
                  <span class="percentage-text">{{ cost.percentage.toFixed(1) }}%</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseCard>

    <!-- API Keys -->
    <BaseCard padding="lg">
      <div class="card-header">
        <h2>API 密钥管理</h2>
      </div>

      <div v-if="apiKeys.length === 0" class="empty-state">
        暂无 API 密钥
      </div>
      <div v-else class="keys-list">
        <div v-for="key in apiKeys" :key="key.id" class="key-item">
          <div class="key-info">
            <Key :size="20" class="key-icon" />
            <div class="key-details">
              <div class="key-provider">{{ providerLabel(key.provider) }}</div>
              <div class="key-masked">{{ key.maskedKey }}</div>
            </div>
          </div>

          <div class="key-status">
            <BaseTag :variant="apiKeyStatusColor(key.status)">
              {{ apiKeyStatusLabel(key.status) }}
            </BaseTag>
          </div>

          <div class="key-actions">
            <BaseButton
              variant="ghost"
              size="sm"
              :disabled="isLiveTradingDisabled"
              @click="handleTestConnection(key.provider)"
              :title="isLiveTradingDisabled ? 'API 测试功能已禁用' : ''"
            >
              测试连接
            </BaseButton>
            <BaseButton
              variant="ghost"
              size="sm"
              :disabled="isLiveTradingDisabled"
              @click="handleUpdateApiKey(key.provider)"
              :title="isLiveTradingDisabled ? 'API 密钥修改功能已禁用' : ''"
            >
              更新密钥
            </BaseButton>
          </div>
        </div>
      </div>
    </BaseCard>

    <!-- Warning Banner -->
    <BaseCard v-if="isLiveTradingDisabled" padding="md" class="warning-banner">
      <div class="warning-content">
        <AlertCircle :size="20" />
        <div>
          <strong>配置修改已禁用</strong>
          <p>API 密钥和模型配置的修改功能已被禁用。系统使用预配置的模拟数据进行演示。</p>
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

/* Status Grid */
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.stat-icon {
  flex-shrink: 0;
}

.stat-icon.primary {
  color: var(--color-accent);
}

.stat-icon.success {
  color: var(--color-success);
}

.stat-icon.warning {
  color: var(--color-warn);
}

.stat-icon.danger {
  color: var(--color-danger);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin-bottom: var(--spacing-xs);
}

.stat-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
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

/* Usage Summary */
.usage-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-xl);
}

.usage-item {
  text-align: center;
}

.usage-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin-bottom: var(--spacing-xs);
}

.usage-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.usage-value.primary {
  color: var(--color-accent);
}

.usage-value.warning {
  color: var(--color-warn);
}

/* Model Breakdown */
.model-breakdown {
  margin-top: var(--spacing-xl);
  padding-top: var(--spacing-xl);
  border-top: 1px solid var(--color-line);
}

.model-breakdown h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0 0 var(--spacing-md) 0;
}

.model-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.model-stat {
  padding: var(--spacing-md);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
}

.model-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
  margin-bottom: var(--spacing-xs);
}

.model-details {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.dot {
  margin: 0 var(--spacing-xs);
}

/* Models Grid */
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: var(--spacing-lg);
}

.model-card {
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  transition: all var(--duration-fast) var(--ease-smooth);
}

.model-card:hover {
  border-color: var(--color-ink-faint);
  box-shadow: var(--shadow-sm);
}

.model-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-md);
}

.model-card-header h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0 0 var(--spacing-xs) 0;
}

.model-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
}

.model-stat-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.model-stat-item .label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.model-stat-item .value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.model-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--font-size-sm);
}

.info-row .label {
  color: var(--color-ink-soft);
}

.info-row .value {
  color: var(--color-ink);
}

.info-row .value.mono {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
}

.degraded-notice {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm);
  background-color: var(--color-warn-bg);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-warn);
}

/* Cost Table */
.cost-table {
  overflow-x: auto;
}

.cost-table table {
  width: 100%;
  border-collapse: collapse;
}

.cost-table thead {
  background-color: var(--color-surface-muted);
}

.cost-table th {
  padding: var(--spacing-md);
  text-align: left;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  border-bottom: 1px solid var(--color-line);
}

.cost-table td {
  padding: var(--spacing-md);
  font-size: var(--font-size-base);
  color: var(--color-ink);
  border-bottom: 1px solid var(--color-line);
}

.cost-table tbody tr:hover {
  background-color: var(--color-surface-muted);
}

.cost-table .model-name {
  font-weight: var(--font-weight-medium);
}

.cost-table .total-tokens {
  font-family: var(--font-family-mono);
}

.cost-table .cost {
  font-weight: var(--font-weight-medium);
  color: var(--color-warn);
}

.percentage-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.percentage-bar {
  flex: 1;
  height: 6px;
  background-color: var(--color-surface-strong);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.percentage-fill {
  height: 100%;
  background-color: var(--color-accent);
  transition: width var(--duration-normal) var(--ease-smooth);
}

.percentage-text {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  min-width: 45px;
  text-align: right;
}

/* API Keys */
.keys-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.key-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
}

.key-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex: 1;
}

.key-icon {
  color: var(--color-ink-soft);
}

.key-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.key-provider {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.key-masked {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.key-status {
  flex-shrink: 0;
}

.key-actions {
  display: flex;
  gap: var(--spacing-sm);
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

  .status-grid {
    grid-template-columns: 1fr;
  }

  .usage-summary {
    grid-template-columns: repeat(2, 1fr);
  }

  .models-grid {
    grid-template-columns: 1fr;
  }

  .model-stats {
    grid-template-columns: 1fr;
  }

  .key-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .key-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
