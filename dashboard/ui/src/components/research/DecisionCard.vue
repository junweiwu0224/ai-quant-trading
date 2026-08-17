<script setup lang="ts">
import { computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'

export interface DecisionData {
  type: 'buy' | 'sell' | 'hold'
  confidence: number
  reasoning: string[]
  riskWarning: string
}

interface Props {
  market?: string
  symbol?: string
}

defineProps<Props>()

// Placeholder decision data
const decision = computed<DecisionData>(() => ({
  type: 'hold',
  confidence: 65,
  reasoning: [
    '技术指标显示当前处于震荡区间，缺乏明确方向信号',
    '基本面数据表现中性，未出现重大利好或利空消息',
    '市场整体情绪谨慎，建议等待更明确的入场时机'
  ],
  riskWarning: '本决策基于历史数据，不构成投资建议'
}))

const getDecisionVariant = (type: string) => {
  switch (type) {
    case 'buy': return 'success'
    case 'sell': return 'danger'
    case 'hold': return 'default'
    default: return 'default'
  }
}

const getDecisionLabel = (type: string) => {
  switch (type) {
    case 'buy': return '买入'
    case 'sell': return '卖出'
    case 'hold': return '观望'
    default: return '未知'
  }
}

const getConfidenceColor = (confidence: number) => {
  if (confidence >= 75) return 'var(--color-success)'
  if (confidence >= 50) return 'var(--color-warn)'
  return 'var(--color-danger)'
}
</script>

<template>
  <div class="decision-card-wrapper">
    <h2 class="decision-title">决策建议</h2>
    <BaseCard class="decision-card" padding="lg" bordered elevated>
      <div class="decision-header">
        <div class="decision-type">
          <BaseTag
            :variant="getDecisionVariant(decision.type)"
            size="lg"
            class="decision-badge"
          >
            {{ getDecisionLabel(decision.type) }}
          </BaseTag>
        </div>
        <div class="decision-confidence">
          <div class="confidence-label">置信度</div>
          <div
            class="confidence-value"
            :style="{ color: getConfidenceColor(decision.confidence) }"
          >
            {{ decision.confidence }}%
          </div>
        </div>
      </div>

      <div class="decision-body">
        <div class="reasoning-section">
          <h3 class="section-title">关键推理</h3>
          <ul class="reasoning-list">
            <li
              v-for="(reason, index) in decision.reasoning"
              :key="index"
              class="reasoning-item"
            >
              {{ reason }}
            </li>
          </ul>
        </div>

        <div class="risk-section">
          <div class="risk-icon">⚠️</div>
          <div class="risk-content">
            <div class="risk-title">风险提示</div>
            <div class="risk-text">{{ decision.riskWarning }}</div>
          </div>
        </div>
      </div>
    </BaseCard>
  </div>
</template>

<style scoped>
.decision-card-wrapper {
  width: 100%;
}

.decision-title {
  margin: 0 0 var(--spacing-lg) 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.decision-card {
  background-color: var(--color-surface);
  border: 2px solid var(--color-accent);
  box-shadow: var(--shadow-md);
  animation: fadeInScale var(--duration-slow) var(--ease-smooth);
}

@keyframes fadeInScale {
  from {
    opacity: 0;
    transform: scale(0.98);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.decision-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-lg);
  padding-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--color-line);
  margin-bottom: var(--spacing-lg);
}

.decision-type {
  flex: 1;
}

.decision-badge {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  padding: var(--spacing-sm) var(--spacing-lg);
  height: auto;
}

.decision-confidence {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--spacing-xs);
}

.confidence-label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.confidence-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  font-family: var(--font-family-mono);
  line-height: 1;
}

.decision-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.reasoning-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.section-title {
  margin: 0;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.reasoning-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.reasoning-item {
  position: relative;
  padding-left: var(--spacing-lg);
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  line-height: var(--line-height-relaxed);
}

.reasoning-item::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--color-accent);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
}

.risk-section {
  display: flex;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
  background-color: var(--color-warn-bg);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-warn);
}

.risk-icon {
  font-size: var(--font-size-2xl);
  line-height: 1;
  flex-shrink: 0;
}

.risk-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.risk-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-warn);
}

.risk-text {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  line-height: var(--line-height-normal);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .decision-title {
    font-size: var(--font-size-lg);
    margin-bottom: var(--spacing-md);
  }

  .decision-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
  }

  .decision-type {
    width: 100%;
  }

  .decision-confidence {
    align-items: flex-start;
  }

  .confidence-value {
    font-size: var(--font-size-2xl);
  }

  .decision-body {
    gap: var(--spacing-lg);
  }

  .reasoning-item {
    font-size: var(--font-size-xs);
  }

  .risk-section {
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .risk-icon {
    font-size: var(--font-size-xl);
  }
}

/* Small mobile */
@media (max-width: 480px) {
  .decision-title {
    font-size: var(--font-size-base);
  }

  .decision-badge {
    font-size: var(--font-size-base);
    padding: var(--spacing-xs) var(--spacing-md);
  }

  .confidence-value {
    font-size: var(--font-size-xl);
  }

  .section-title {
    font-size: var(--font-size-sm);
  }

  .risk-title {
    font-size: var(--font-size-xs);
  }

  .risk-text {
    font-size: var(--font-size-xs);
  }
}
</style>
