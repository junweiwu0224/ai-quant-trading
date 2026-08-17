<script setup lang="ts">
import BaseCard from '../base/BaseCard.vue'

export interface TechnicalIndicatorsProps {
  market: string
  symbol: string
}

defineProps<TechnicalIndicatorsProps>()

interface Indicator {
  label: string
  value: string
  description: string
}

const indicators: Indicator[] = [
  { label: 'MA5', value: '计算中...', description: '5日均线' },
  { label: 'MA10', value: '计算中...', description: '10日均线' },
  { label: 'MA20', value: '计算中...', description: '20日均线' },
  { label: 'MACD', value: '计算中...', description: '指数平滑异同移动平均线' },
  { label: 'RSI', value: '计算中...', description: '相对强弱指标' },
  { label: 'KDJ', value: '计算中...', description: '随机指标' },
]
</script>

<template>
  <BaseCard class="technical-indicators">
    <div class="indicators-header">
      <h3 class="indicators-title">技术指标</h3>
      <p class="indicators-subtitle">实时技术分析指标</p>
    </div>

    <div class="indicators-grid">
      <div
        v-for="indicator in indicators"
        :key="indicator.label"
        class="indicator-item"
      >
        <div class="indicator-label">{{ indicator.label }}</div>
        <div class="indicator-value">{{ indicator.value }}</div>
        <div class="indicator-description">{{ indicator.description }}</div>
      </div>
    </div>
  </BaseCard>
</template>

<style scoped>
.technical-indicators {
  width: 100%;
}

.indicators-header {
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
}

.indicators-title {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.indicators-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.indicators-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-md);
}

.indicator-item {
  padding: var(--spacing-md);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  transition: all var(--duration-fast) var(--ease-smooth);
}

.indicator-item:hover {
  background-color: var(--color-surface-strong);
  transform: translateY(-1px);
}

.indicator-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent);
  margin-bottom: var(--spacing-xs);
}

.indicator-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
  margin-bottom: var(--spacing-xs);
  font-family: var(--font-family-mono);
}

.indicator-description {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .indicators-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-sm);
  }

  .indicator-item {
    padding: var(--spacing-sm);
  }

  .indicator-value {
    font-size: var(--font-size-lg);
  }
}

/* Small mobile */
@media (max-width: 480px) {
  .indicators-grid {
    grid-template-columns: 1fr;
  }
}
</style>
