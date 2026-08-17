<script setup lang="ts">
import { computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'

export interface KLineChartProps {
  market: string
  symbol: string
}

const props = defineProps<KLineChartProps>()

const chartTitle = computed(() => `K线图 - ${props.symbol}`)
</script>

<template>
  <BaseCard class="kline-chart">
    <div class="chart-header">
      <h3 class="chart-title">{{ chartTitle }}</h3>
      <div class="chart-meta">
        <span class="meta-item">市场: {{ market }}</span>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-placeholder">
        <p class="placeholder-text">图表加载中...</p>
        <p class="placeholder-hint">实际图表功能将在后续阶段实现</p>
      </div>
    </div>
  </BaseCard>
</template>

<style scoped>
.kline-chart {
  width: 100%;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
}

.chart-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.chart-meta {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.meta-item {
  padding: var(--spacing-xs) var(--spacing-sm);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-sm);
}

.chart-container {
  height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
}

.chart-placeholder {
  text-align: center;
  padding: var(--spacing-xl);
}

.placeholder-text {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
}

.placeholder-hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-ink-faint);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .chart-container {
    height: 300px;
  }

  .chart-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .chart-title {
    font-size: var(--font-size-base);
  }
}
</style>
