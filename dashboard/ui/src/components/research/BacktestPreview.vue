<script setup lang="ts">
import { computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'

export interface BacktestPreviewProps {
  market: string
  symbol: string
  strategyName?: string
  timePeriod?: string
  initialCapital?: number
  positionSizing?: string
  stopLoss?: number
  takeProfit?: number
}

const props = withDefaults(defineProps<BacktestPreviewProps>(), {
  strategyName: '策略草案',
  timePeriod: '最近一年',
  initialCapital: 100000,
  positionSizing: 'fixed-ratio',
  stopLoss: 5,
  takeProfit: 10
})

// Position sizing display mapping
const positionSizingLabel = computed(() => {
  const labels: Record<string, string> = {
    'fixed-amount': '固定金额',
    'fixed-ratio': '固定比例',
    'dynamic': '动态调整'
  }
  return labels[props.positionSizing] || '固定比例'
})

// Format currency for display
const formattedCapital = computed(() => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(props.initialCapital)
})
</script>

<template>
  <BaseCard padding="lg" bordered class="preview-card">
    <h2 class="preview-title">配置预览</h2>

    <!-- Strategy Summary -->
    <section class="preview-section">
      <h3 class="section-title">策略概览</h3>
      <div class="preview-grid">
        <div class="preview-item">
          <span class="item-label">策略名称</span>
          <span class="item-value">{{ strategyName }}</span>
        </div>
        <div class="preview-item">
          <span class="item-label">标的代码</span>
          <span class="item-value item-value--mono">{{ market }}:{{ symbol }}</span>
        </div>
        <div class="preview-item">
          <span class="item-label">回测周期</span>
          <span class="item-value">{{ timePeriod }}</span>
        </div>
        <div class="preview-item">
          <span class="item-label">初始资金</span>
          <span class="item-value">{{ formattedCapital }}</span>
        </div>
      </div>
    </section>

    <!-- Risk Parameters -->
    <section class="preview-section">
      <h3 class="section-title">风险参数</h3>
      <div class="preview-grid">
        <div class="preview-item">
          <span class="item-label">仓位管理</span>
          <span class="item-value">{{ positionSizingLabel }}</span>
        </div>
        <div class="preview-item">
          <span class="item-label">止损比例</span>
          <span class="item-value item-value--danger">{{ stopLoss }}%</span>
        </div>
        <div class="preview-item">
          <span class="item-label">止盈比例</span>
          <span class="item-value item-value--success">{{ takeProfit }}%</span>
        </div>
      </div>
    </section>

    <!-- Expected Metrics -->
    <section class="preview-section">
      <h3 class="section-title">预期指标</h3>
      <div class="metrics-grid">
        <div class="metric-card">
          <span class="metric-label">收益率</span>
          <span class="metric-value metric-value--pending">待计算</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">夏普比率</span>
          <span class="metric-value metric-value--pending">待计算</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">最大回撤</span>
          <span class="metric-value metric-value--pending">待计算</span>
        </div>
      </div>
    </section>
  </BaseCard>
</template>

<style scoped>
.preview-card {
  background-color: var(--color-surface-muted);
}

.preview-title {
  margin: 0 0 var(--spacing-xl) 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
}

.preview-section {
  margin-bottom: var(--spacing-lg);
}

.preview-section:last-child {
  margin-bottom: 0;
}

.section-title {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preview-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.preview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--color-line);
}

.preview-item:last-child {
  border-bottom: none;
}

.item-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.item-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}

.item-value--mono {
  font-family: var(--font-family-mono);
  color: var(--color-accent);
}

.item-value--danger {
  color: var(--color-danger);
}

.item-value--success {
  color: var(--color-success);
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-sm);
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  text-align: center;
}

.metric-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.metric-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.metric-value--pending {
  color: var(--color-ink-faint);
  font-style: italic;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .preview-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-xs);
  }
}
</style>
