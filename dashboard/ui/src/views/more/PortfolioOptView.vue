<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import { PieChart, RefreshCw, TrendingUp, AlertTriangle } from 'lucide-vue-next'
import { getPortfolioAnalysis } from '../../api/portfolio'
import type { PortfolioAnalysis } from '../../api/portfolio'

const title = '持仓优化'
const description = '基于现代投资组合理论的持仓分析与优化建议'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const analysis = ref<PortfolioAnalysis | null>(null)

// Computed
const positionChartData = computed(() => {
  if (!analysis.value) return []
  return analysis.value.positions.map(p => ({
    label: p.name,
    value: p.weight,
    color: getColorForWeight(p.weight)
  }))
})

// Methods
async function loadData() {
  loading.value = true
  error.value = null

  try {
    analysis.value = await getPortfolioAnalysis()
  } catch (err) {
    console.error('Failed to load portfolio analysis:', err)
    error.value = '加载数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(num: number): string {
  return num.toFixed(2) + '%'
}

function getColorForWeight(weight: number): string {
  if (weight > 25) return 'var(--color-danger)'
  if (weight > 15) return 'var(--color-warn)'
  return 'var(--color-accent)'
}

function getSuggestionIcon(type: string) {
  return type === 'add' ? TrendingUp : AlertTriangle
}

function getSuggestionVariant(priority: string) {
  if (priority === 'high') return 'danger'
  if (priority === 'medium') return 'warning'
  return 'info'
}

function getCorrelationColor(value: number): string {
  const intensity = Math.abs(value)
  if (value > 0.7) return '#ef4444'
  if (value > 0.3) return '#f59e0b'
  if (value > -0.3) return '#6b7280'
  if (value > -0.7) return '#3b82f6'
  return '#8b5cf6'
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
    <div v-if="loading && !analysis" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="analysis" class="content-grid">
      <!-- Portfolio Composition -->
      <BaseCard padding="lg">
        <h2 class="section-title">持仓结构</h2>
        <div class="composition-layout">
          <div class="composition-chart">
            <div class="pie-placeholder">
              <PieChart :size="48" class="chart-icon" />
              <p class="chart-label">持仓分布图</p>
              <p class="chart-note">可视化功能开发中</p>
            </div>
          </div>
          <div class="composition-list">
            <div v-for="position in analysis.positions" :key="position.symbol" class="position-item">
              <div class="position-info">
                <span class="position-name">{{ position.name }}</span>
                <span class="position-code">{{ position.symbol }}</span>
              </div>
              <div class="position-bar">
                <div
                  class="position-bar-fill"
                  :style="{ width: position.weight + '%', backgroundColor: getColorForWeight(position.weight) }"
                ></div>
              </div>
              <div class="position-stats">
                <span class="position-weight">{{ formatPercent(position.weight) }}</span>
                <span class="position-value">¥{{ formatNumber(position.value) }}</span>
              </div>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Risk Metrics -->
      <BaseCard padding="lg">
        <h2 class="section-title">风险收益指标</h2>
        <div class="metrics-grid">
          <div class="metric-card">
            <div class="metric-label">Beta</div>
            <div class="metric-value">{{ analysis.risk_metrics.beta.toFixed(2) }}</div>
            <div class="metric-desc">市场相关性</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Sharpe Ratio</div>
            <div class="metric-value positive">{{ analysis.risk_metrics.sharpe_ratio.toFixed(2) }}</div>
            <div class="metric-desc">风险调整收益</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Max Drawdown</div>
            <div class="metric-value negative">{{ analysis.risk_metrics.max_drawdown.toFixed(1) }}%</div>
            <div class="metric-desc">最大回撤</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">VaR (95%)</div>
            <div class="metric-value">¥{{ formatNumber(analysis.risk_metrics.var_95) }}</div>
            <div class="metric-desc">风险价值</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Volatility</div>
            <div class="metric-value">{{ analysis.risk_metrics.volatility.toFixed(1) }}%</div>
            <div class="metric-desc">年化波动率</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Alpha</div>
            <div class="metric-value positive">{{ analysis.risk_metrics.alpha.toFixed(1) }}%</div>
            <div class="metric-desc">超额收益</div>
          </div>
        </div>
      </BaseCard>

      <!-- Optimization Suggestions -->
      <BaseCard padding="lg">
        <h2 class="section-title">优化建议</h2>
        <div class="suggestions-list">
          <div v-for="suggestion in analysis.suggestions" :key="suggestion.symbol" class="suggestion-item">
            <div class="suggestion-header">
              <BaseTag :variant="getSuggestionVariant(suggestion.priority)" size="sm">
                {{ suggestion.priority === 'high' ? '高优先级' : suggestion.priority === 'medium' ? '中优先级' : '低优先级' }}
              </BaseTag>
              <div class="suggestion-title">
                <component :is="getSuggestionIcon(suggestion.type)" :size="18" />
                <strong>{{ suggestion.name }}</strong>
                <span class="suggestion-code">{{ suggestion.symbol }}</span>
              </div>
            </div>
            <div class="suggestion-body">
              <div class="suggestion-weights">
                <div class="weight-item">
                  <span class="weight-label">当前权重</span>
                  <span class="weight-value">{{ formatPercent(suggestion.current_weight) }}</span>
                </div>
                <div class="weight-arrow">→</div>
                <div class="weight-item">
                  <span class="weight-label">建议权重</span>
                  <span class="weight-value suggested">{{ formatPercent(suggestion.suggested_weight) }}</span>
                </div>
              </div>
              <p class="suggestion-reason">{{ suggestion.reason }}</p>
            </div>
            <div class="suggestion-actions">
              <BaseButton variant="secondary" size="sm" :disabled="true">
                应用建议（功能开发中）
              </BaseButton>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Correlation Matrix -->
      <BaseCard padding="lg">
        <h2 class="section-title">相关性矩阵</h2>
        <div class="correlation-container">
          <div class="correlation-matrix">
            <div class="correlation-row header-row">
              <div class="correlation-cell empty"></div>
              <div
                v-for="symbol in analysis.correlation.symbols"
                :key="'h-' + symbol"
                class="correlation-cell header"
              >
                {{ symbol.split('.')[0] }}
              </div>
            </div>
            <div
              v-for="(row, i) in analysis.correlation.matrix"
              :key="'r-' + i"
              class="correlation-row"
            >
              <div class="correlation-cell header">
                {{ analysis.correlation.symbols[i].split('.')[0] }}
              </div>
              <div
                v-for="(value, j) in row"
                :key="'c-' + j"
                class="correlation-cell"
                :style="{ backgroundColor: getCorrelationColor(value) }"
              >
                {{ value.toFixed(2) }}
              </div>
            </div>
          </div>
          <div class="correlation-legend">
            <span>负相关 -1</span>
            <div class="legend-gradient"></div>
            <span>正相关 +1</span>
          </div>
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

/* Portfolio Composition */
.composition-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: var(--spacing-xl);
}

.composition-chart {
  display: flex;
  align-items: center;
  justify-content: center;
}

.pie-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 200px;
  height: 200px;
  border: 2px dashed var(--color-line);
  border-radius: var(--radius-full);
  text-align: center;
}

.chart-icon {
  color: var(--color-ink-faint);
  margin-bottom: var(--spacing-sm);
}

.chart-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  margin: 0 0 var(--spacing-xs) 0;
}

.chart-note {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
  margin: 0;
}

.composition-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.position-item {
  display: grid;
  grid-template-columns: 140px 1fr 140px;
  gap: var(--spacing-md);
  align-items: center;
}

.position-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.position-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.position-code {
  font-size: var(--font-size-xs);
  font-family: var(--font-family-mono);
  color: var(--color-ink-soft);
}

.position-bar {
  height: 24px;
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.position-bar-fill {
  height: 100%;
  border-radius: var(--radius-sm);
  transition: width var(--duration-normal) var(--ease-smooth);
}

.position-stats {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.position-weight {
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.position-value {
  color: var(--color-ink-soft);
}

/* Risk Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-lg);
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
}

.metric-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
}

.metric-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.metric-value.positive {
  color: var(--color-success);
}

.metric-value.negative {
  color: var(--color-danger);
}

.metric-desc {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
}

/* Suggestions */
.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.suggestion-item {
  padding: var(--spacing-lg);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-accent);
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.suggestion-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-base);
  color: var(--color-ink);
}

.suggestion-code {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.suggestion-body {
  margin-bottom: var(--spacing-md);
}

.suggestion-weights {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-md);
}

.weight-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.weight-label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.weight-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.weight-value.suggested {
  color: var(--color-accent);
}

.weight-arrow {
  font-size: var(--font-size-xl);
  color: var(--color-ink-faint);
}

.suggestion-reason {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: 0;
}

.suggestion-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* Correlation Matrix */
.correlation-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.correlation-matrix {
  display: flex;
  flex-direction: column;
  overflow-x: auto;
}

.correlation-row {
  display: flex;
}

.correlation-cell {
  min-width: 80px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border: 1px solid var(--color-line);
  color: var(--color-surface);
}

.correlation-cell.empty {
  background-color: transparent;
  border: none;
}

.correlation-cell.header {
  background-color: var(--color-surface-muted);
  color: var(--color-ink);
  font-size: var(--font-size-xs);
}

.correlation-legend {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.legend-gradient {
  flex: 1;
  height: 20px;
  background: linear-gradient(to right, #8b5cf6, #3b82f6, #6b7280, #f59e0b, #ef4444);
  border-radius: var(--radius-sm);
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

  .composition-layout {
    grid-template-columns: 1fr;
  }

  .position-item {
    grid-template-columns: 1fr;
    gap: var(--spacing-sm);
  }

  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .suggestion-weights {
    flex-direction: column;
    align-items: flex-start;
  }

  .weight-arrow {
    transform: rotate(90deg);
  }
}
</style>
