<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import { Sparkles, RefreshCw, TrendingUp, TrendingDown } from 'lucide-vue-next'
import { getAlphaFactors, getFactorPerformance } from '../../api/alpha'
import type { AlphaFactor, FactorPerformance } from '../../api/alpha'

const title = 'Alpha 因子库'
const description = '因子研究、回测与组合优化平台'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const factors = ref<AlphaFactor[]>([])
const selectedFactor = ref<AlphaFactor | null>(null)
const factorPerformance = ref<FactorPerformance | null>(null)
const performanceLoading = ref(false)

// Filter state
const categoryFilter = ref<string>('all')

// Computed
const filteredFactors = computed(() => {
  if (categoryFilter.value === 'all') {
    return factors.value
  }
  return factors.value.filter(f => f.category === categoryFilter.value)
})

const categories = [
  { value: 'all', label: '全部' },
  { value: 'momentum', label: '动量' },
  { value: 'value', label: '价值' },
  { value: 'quality', label: '质量' },
  { value: 'volatility', label: '波动率' },
  { value: 'size', label: '规模' },
  { value: 'custom', label: '自定义' }
]

// Methods
async function loadData() {
  loading.value = true
  error.value = null

  try {
    const factorsData = await getAlphaFactors()
    factors.value = factorsData

    // Auto-select first factor
    if (factorsData.length > 0 && !selectedFactor.value) {
      await selectFactor(factorsData[0])
    }
  } catch (err) {
    console.error('Failed to load alpha factors:', err)
    error.value = '加载因子数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function selectFactor(factor: AlphaFactor) {
  selectedFactor.value = factor
  performanceLoading.value = true

  try {
    const performance = await getFactorPerformance(factor.id)
    factorPerformance.value = performance
  } catch (err) {
    console.error('Failed to load factor performance:', err)
  } finally {
    performanceLoading.value = false
  }
}

function getCategoryLabel(category: string): string {
  return categories.find(c => c.value === category)?.label || category
}

function getCategoryVariant(category: string): 'default' | 'success' | 'warning' | 'info' {
  const variantMap: Record<string, 'default' | 'success' | 'warning' | 'info'> = {
    momentum: 'success',
    value: 'info',
    quality: 'warning',
    volatility: 'default',
    size: 'default',
    custom: 'default'
  }
  return variantMap[category] || 'default'
}

function getStatusVariant(status: string): 'success' | 'warning' | 'default' {
  const variantMap: Record<string, 'success' | 'warning' | 'default'> = {
    active: 'success',
    testing: 'warning',
    inactive: 'default'
  }
  return variantMap[status] || 'default'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    active: '运行中',
    testing: '测试中',
    inactive: '已停用'
  }
  return labelMap[status] || status
}

function formatNumber(num: number, decimals: number = 2): string {
  return num.toFixed(decimals)
}

function formatPercent(num: number): string {
  return num.toFixed(2) + '%'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('zh-CN')
}

function handleOptimize() {
  alert('因子组合优化功能开发中\n\n提示：将支持多因子权重优化、正交化处理等高级功能')
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
    <div v-if="loading && factors.length === 0" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="factors.length > 0" class="content-layout">
      <!-- Left: Factor Library -->
      <div class="factors-section">
        <BaseCard padding="lg">
          <div class="section-header">
            <h2 class="section-title">因子库</h2>
            <div class="filter-tabs">
              <button
                v-for="cat in categories"
                :key="cat.value"
                class="filter-tab"
                :class="{ active: categoryFilter === cat.value }"
                @click="categoryFilter = cat.value"
              >
                {{ cat.label }}
              </button>
            </div>
          </div>

          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>因子名称</th>
                  <th>分类</th>
                  <th class="align-right">IC</th>
                  <th class="align-right">IR</th>
                  <th class="align-right">Sharpe</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="factor in filteredFactors"
                  :key="factor.id"
                  class="clickable-row"
                  :class="{ selected: selectedFactor?.id === factor.id }"
                  @click="selectFactor(factor)"
                >
                  <td class="factor-name">{{ factor.name }}</td>
                  <td>
                    <BaseTag :variant="getCategoryVariant(factor.category)" size="sm">
                      {{ getCategoryLabel(factor.category) }}
                    </BaseTag>
                  </td>
                  <td class="align-right" :class="factor.ic >= 0 ? 'positive' : 'negative'">
                    {{ formatNumber(factor.ic, 3) }}
                  </td>
                  <td class="align-right">{{ formatNumber(factor.ir) }}</td>
                  <td class="align-right">{{ formatNumber(factor.sharpe) }}</td>
                  <td>
                    <BaseTag :variant="getStatusVariant(factor.status)" size="sm">
                      {{ getStatusLabel(factor.status) }}
                    </BaseTag>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </BaseCard>
      </div>

      <!-- Right: Factor Detail and Performance -->
      <div class="detail-section">
        <!-- Factor Detail Card -->
        <BaseCard v-if="selectedFactor" padding="lg" class="detail-card">
          <div class="detail-header">
            <div>
              <h2 class="section-title">{{ selectedFactor.name }}</h2>
              <p class="detail-description">{{ selectedFactor.description }}</p>
            </div>
            <BaseTag :variant="getStatusVariant(selectedFactor.status)">
              {{ getStatusLabel(selectedFactor.status) }}
            </BaseTag>
          </div>

          <div class="detail-info">
            <div class="info-row">
              <span class="info-label">分类:</span>
              <BaseTag :variant="getCategoryVariant(selectedFactor.category)" size="sm">
                {{ getCategoryLabel(selectedFactor.category) }}
              </BaseTag>
            </div>
            <div class="info-row">
              <span class="info-label">创建时间:</span>
              <span class="info-value">{{ formatDate(selectedFactor.created_at) }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">更新时间:</span>
              <span class="info-value">{{ formatDate(selectedFactor.updated_at) }}</span>
            </div>
          </div>

          <div class="formula-section">
            <h3 class="subsection-title">因子公式</h3>
            <div class="formula-code">{{ selectedFactor.formula }}</div>
          </div>
        </BaseCard>

        <!-- Performance Card -->
        <BaseCard v-if="selectedFactor" padding="lg" class="performance-card">
          <h2 class="section-title">回测表现</h2>

          <div v-if="performanceLoading" class="loading-indicator">
            <div class="spinner-sm"></div>
            <span>加载中...</span>
          </div>

          <div v-else-if="factorPerformance" class="metrics-grid">
            <div class="metric-item">
              <div class="metric-label">累计收益</div>
              <div class="metric-value" :class="factorPerformance.return >= 0 ? 'profit' : 'loss'">
                {{ factorPerformance.return >= 0 ? '+' : '' }}{{ formatPercent(factorPerformance.return) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">Sharpe比率</div>
              <div class="metric-value">{{ formatNumber(factorPerformance.sharpe) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">最大回撤</div>
              <div class="metric-value loss">{{ formatPercent(factorPerformance.max_drawdown) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">胜率</div>
              <div class="metric-value">{{ formatPercent(factorPerformance.win_rate) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">平均持仓天数</div>
              <div class="metric-value">{{ factorPerformance.avg_holding_days }} 天</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">测试周期</div>
              <div class="metric-value secondary">{{ factorPerformance.period }}</div>
            </div>
          </div>

          <div v-else class="empty-performance">
            暂无回测数据
          </div>
        </BaseCard>

        <!-- Factor Combination Builder -->
        <BaseCard padding="lg" class="combination-card">
          <h2 class="section-title">因子组合构建</h2>
          <p class="section-hint">选择多个因子进行组合优化，系统将自动计算最优权重配置</p>

          <div class="combination-actions">
            <BaseButton
              variant="primary"
              size="md"
              :disabled="true"
              @click="handleOptimize"
            >
              <Sparkles :size="16" />
              优化权重配置（功能开发中）
            </BaseButton>
          </div>
        </BaseCard>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      暂无因子数据
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1600px;
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

.content-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

.filter-tabs {
  display: flex;
  gap: var(--spacing-xs);
}

.filter-tab {
  padding: var(--spacing-xs) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.filter-tab:hover {
  background-color: var(--color-surface-muted);
  border-color: var(--color-ink-faint);
}

.filter-tab.active {
  background-color: var(--color-accent);
  color: var(--color-surface);
  border-color: var(--color-accent);
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

.data-table .align-right {
  text-align: right;
}

.data-table .factor-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.data-table .positive {
  color: var(--color-up);
}

.data-table .negative {
  color: var(--color-down);
}

.clickable-row {
  cursor: pointer;
  transition: background-color var(--duration-fast) var(--ease-smooth);
}

.clickable-row:hover {
  background-color: var(--color-surface-muted);
}

.clickable-row.selected {
  background-color: var(--color-accent-bg);
}

/* Detail Section */
.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.detail-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.detail-description {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: var(--spacing-xs) 0 0 0;
}

.detail-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
}

.info-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.info-label {
  color: var(--color-ink-soft);
  min-width: 80px;
}

.info-value {
  color: var(--color-ink);
}

.formula-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.subsection-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

.formula-code {
  padding: var(--spacing-md);
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  color: var(--color-ink);
  overflow-x: auto;
}

/* Performance Card */
.loading-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

.spinner-sm {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-line);
  border-top-color: var(--color-accent);
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-lg);
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.metric-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.metric-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.metric-value.secondary {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
}

.metric-value.profit {
  color: var(--color-up);
}

.metric-value.loss {
  color: var(--color-down);
}

.empty-performance {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

/* Combination Card */
.section-hint {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: var(--spacing-sm) 0 var(--spacing-lg) 0;
}

.combination-actions {
  display: flex;
  gap: var(--spacing-md);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-base);
}

@media (max-width: 1200px) {
  .content-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .page-head {
    flex-direction: column;
    gap: var(--spacing-md);
  }

  .filter-tabs {
    flex-wrap: wrap;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
