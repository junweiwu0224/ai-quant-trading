<script setup lang="ts">
import { ref, onMounted } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import BaseInput from '../../components/base/BaseInput.vue'
import { Code2, RefreshCw, Play, FileCode } from 'lucide-vue-next'
import { getStrategies } from '../../api/strategy'
import type { Strategy } from '../../api/strategy'

const title = '策略工作台'
const description = '策略开发、回测与版本管理的集成环境'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const strategies = ref<Strategy[]>([])
const selectedStrategy = ref<Strategy | null>(null)

// Backtest config
const backtestConfig = ref({
  startDate: '2023-01-01',
  endDate: '2024-08-17',
  initialCapital: 1000000,
  commissionRate: 0.0003,
  slippageRate: 0.0001
})

// Mock results state
const showResults = ref(false)

// Methods
async function loadData() {
  loading.value = true
  error.value = null

  try {
    const strategiesData = await getStrategies()
    strategies.value = strategiesData

    // Auto-select first strategy
    if (strategiesData.length > 0 && !selectedStrategy.value) {
      selectStrategy(strategiesData[0])
    }
  } catch (err) {
    console.error('Failed to load strategies:', err)
    error.value = '加载策略数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function selectStrategy(strategy: Strategy) {
  selectedStrategy.value = strategy
  showResults.value = false
}

function getTypeLabel(type: string): string {
  const labelMap: Record<string, string> = {
    momentum: '动量',
    mean_reversion: '均值回归',
    arbitrage: '套利',
    ml_based: '机器学习',
    custom: '自定义'
  }
  return labelMap[type] || type
}

function getTypeVariant(type: string): 'success' | 'warning' | 'info' | 'default' {
  const variantMap: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    momentum: 'success',
    mean_reversion: 'info',
    arbitrage: 'warning',
    ml_based: 'info',
    custom: 'default'
  }
  return variantMap[type] || 'default'
}

function getStatusVariant(status: string): 'success' | 'warning' | 'default' {
  const variantMap: Record<string, 'success' | 'warning' | 'default'> = {
    active: 'success',
    draft: 'warning',
    archived: 'default'
  }
  return variantMap[status] || 'default'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    active: '运行中',
    draft: '草稿',
    archived: '已归档'
  }
  return labelMap[status] || status
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN')
}

function handleRunBacktest() {
  alert('回测执行功能开发中\n\n提示：将支持参数优化、Walk-Forward验证等高级功能')
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
    <div v-if="loading && strategies.length === 0" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="strategies.length > 0" class="content-layout">
      <!-- Left Sidebar: Strategy List -->
      <aside class="sidebar">
        <BaseCard padding="md">
          <h2 class="section-title">策略列表</h2>
          <div class="strategy-list">
            <div
              v-for="strategy in strategies"
              :key="strategy.id"
              class="strategy-item"
              :class="{ selected: selectedStrategy?.id === strategy.id }"
              @click="selectStrategy(strategy)"
            >
              <div class="strategy-header">
                <FileCode :size="16" class="strategy-icon" />
                <span class="strategy-name">{{ strategy.name }}</span>
              </div>
              <div class="strategy-meta">
                <BaseTag :variant="getTypeVariant(strategy.type)" size="sm">
                  {{ getTypeLabel(strategy.type) }}
                </BaseTag>
                <BaseTag :variant="getStatusVariant(strategy.status)" size="sm">
                  {{ getStatusLabel(strategy.status) }}
                </BaseTag>
              </div>
              <div class="strategy-date">
                更新: {{ formatDateTime(strategy.updated_at) }}
              </div>
            </div>
          </div>
        </BaseCard>
      </aside>

      <!-- Main Area -->
      <div class="main-area">
        <div v-if="selectedStrategy" class="main-content">
          <!-- Code Editor Area -->
          <BaseCard padding="lg" class="editor-card">
            <div class="editor-header">
              <div>
                <h2 class="section-title">{{ selectedStrategy.name }}</h2>
                <p class="editor-description">{{ selectedStrategy.description }}</p>
              </div>
              <div class="editor-actions">
                <BaseTag :variant="getStatusVariant(selectedStrategy.status)">
                  {{ getStatusLabel(selectedStrategy.status) }}
                </BaseTag>
              </div>
            </div>

            <div class="code-editor">
              <div class="code-editor-toolbar">
                <span class="toolbar-label">
                  <Code2 :size="14" />
                  Python Strategy Code
                </span>
                <span class="toolbar-hint">只读模式 - 完整编辑器功能开发中</span>
              </div>
              <pre class="code-content">{{ selectedStrategy.code }}</pre>
            </div>
          </BaseCard>

          <!-- Backtest Config Panel -->
          <BaseCard padding="lg" class="config-card">
            <h2 class="section-title">回测配置</h2>
            <div class="config-grid">
              <div class="config-item">
                <label>起始日期</label>
                <BaseInput
                  v-model="backtestConfig.startDate"
                  type="date"
                  size="md"
                />
              </div>
              <div class="config-item">
                <label>结束日期</label>
                <BaseInput
                  v-model="backtestConfig.endDate"
                  type="date"
                  size="md"
                />
              </div>
              <div class="config-item">
                <label>初始资金</label>
                <BaseInput
                  v-model="backtestConfig.initialCapital"
                  type="number"
                  size="md"
                  placeholder="1000000"
                />
              </div>
              <div class="config-item">
                <label>手续费率</label>
                <BaseInput
                  v-model="backtestConfig.commissionRate"
                  type="number"
                  step="0.0001"
                  size="md"
                  placeholder="0.0003"
                />
              </div>
              <div class="config-item">
                <label>滑点率</label>
                <BaseInput
                  v-model="backtestConfig.slippageRate"
                  type="number"
                  step="0.0001"
                  size="md"
                  placeholder="0.0001"
                />
              </div>
            </div>

            <div class="config-actions">
              <BaseButton
                variant="primary"
                size="md"
                :disabled="true"
                @click="handleRunBacktest"
              >
                <Play :size="16" />
                运行回测（功能开发中）
              </BaseButton>
            </div>
          </BaseCard>

          <!-- Results Dashboard -->
          <BaseCard padding="lg" class="results-card">
            <h2 class="section-title">回测结果</h2>

            <div class="results-placeholder">
              <div class="placeholder-chart">
                <div class="chart-icon">📈</div>
                <p>权益曲线图表区域</p>
                <span class="placeholder-hint">运行回测后显示策略表现曲线</span>
              </div>

              <div class="metrics-preview">
                <div class="metric-card">
                  <div class="metric-label">累计收益率</div>
                  <div class="metric-value placeholder-value">--</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">年化收益率</div>
                  <div class="metric-value placeholder-value">--</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">Sharpe比率</div>
                  <div class="metric-value placeholder-value">--</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">最大回撤</div>
                  <div class="metric-value placeholder-value">--</div>
                </div>
              </div>
            </div>
          </BaseCard>
        </div>

        <!-- No Selection State -->
        <div v-else class="no-selection">
          <FileCode :size="48" class="no-selection-icon" />
          <p>请从左侧选择一个策略</p>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      暂无策略数据
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1800px;
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
  grid-template-columns: 320px 1fr;
  gap: var(--spacing-lg);
}

/* Sidebar */
.sidebar {
  position: sticky;
  top: var(--spacing-lg);
  align-self: start;
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0 0 var(--spacing-lg) 0;
}

.strategy-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.strategy-item {
  padding: var(--spacing-md);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.strategy-item:hover {
  background-color: var(--color-surface-muted);
  border-color: var(--color-ink-faint);
}

.strategy-item.selected {
  background-color: var(--color-accent-bg);
  border-color: var(--color-accent);
}

.strategy-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.strategy-icon {
  color: var(--color-ink-soft);
}

.strategy-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.strategy-meta {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-xs);
}

.strategy-date {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

/* Main Area */
.main-area {
  min-height: 600px;
}

.main-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

/* Code Editor */
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.editor-description {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: var(--spacing-xs) 0 0 0;
}

.editor-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.code-editor {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.code-editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--color-surface-strong);
  border-bottom: 1px solid var(--color-line);
}

.toolbar-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.toolbar-hint {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.code-content {
  margin: 0;
  padding: var(--spacing-lg);
  background-color: var(--color-surface);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-relaxed);
  color: var(--color-ink);
  overflow-x: auto;
  white-space: pre;
}

/* Config Panel */
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.config-item label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.config-actions {
  display: flex;
  gap: var(--spacing-md);
}

/* Results */
.results-placeholder {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.placeholder-chart {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  background-color: var(--color-surface-muted);
  border: 2px dashed var(--color-line);
  border-radius: var(--radius-md);
  text-align: center;
}

.chart-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-md);
}

.placeholder-chart p {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
  margin: 0 0 var(--spacing-xs) 0;
}

.placeholder-hint {
  font-size: var(--font-size-sm);
  color: var(--color-ink-faint);
}

.metrics-preview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-lg);
}

.metric-card {
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  text-align: center;
}

.metric-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin-bottom: var(--spacing-sm);
}

.metric-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.metric-value.placeholder-value {
  color: var(--color-ink-faint);
}

/* No Selection */
.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
  text-align: center;
}

.no-selection-icon {
  color: var(--color-ink-faint);
  margin-bottom: var(--spacing-md);
}

.no-selection p {
  font-size: var(--font-size-base);
  margin: 0;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-base);
}

@media (max-width: 1200px) {
  .content-layout {
    grid-template-columns: 280px 1fr;
  }

  .config-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .content-layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
  }

  .config-grid {
    grid-template-columns: 1fr;
  }

  .metrics-preview {
    grid-template-columns: 1fr;
  }
}
</style>
