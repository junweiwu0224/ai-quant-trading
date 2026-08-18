<script setup lang="ts">
import BaseCard from '../base/BaseCard.vue'
import ResearchStatePanel from './ResearchStatePanel.vue'
import type { TechnicalIndicators as IndicatorData } from '../../api/types'

const props = withDefaults(defineProps<{
  market: string
  symbol: string
  indicators?: IndicatorData
  state?: 'loading' | 'available' | 'partial' | 'unavailable'
  error?: string
}>(), { indicators: () => ({}), state: 'loading' })

const items = [
  ['ma5', 'MA5', '5日均线'], ['ma10', 'MA10', '10日均线'], ['ma20', 'MA20', '20日均线'],
  ['ma60', 'MA60', '60日均线'], ['macd', 'MACD', '指数平滑异同移动平均线'], ['rsi', 'RSI', '相对强弱指标'],
] as const
function display(key: keyof IndicatorData) {
  const value = props.indicators[key]
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '暂无数据'
}
</script>

<template>
  <BaseCard class="technical-indicators">
    <div class="indicators-header"><h3 class="indicators-title">技术指标</h3><p class="indicators-subtitle">{{ market }} / {{ symbol }} 的真实接口结果</p></div>
    <ResearchStatePanel :state="state" :error="error" />
    <div class="indicators-grid"><div v-for="[key, label, description] in items" :key="key" class="indicator-item"><div class="indicator-label">{{ label }}</div><div class="indicator-value">{{ display(key) }}</div><div class="indicator-description">{{ description }}</div></div></div>
  </BaseCard>
</template>

<style scoped>
.technical-indicators { width:100%; }
.indicators-header { margin-bottom:var(--spacing-md); padding-bottom:var(--spacing-md); border-bottom:1px solid var(--color-line); }
.indicators-title { margin:0 0 var(--spacing-xs); font-size:var(--font-size-lg); color:var(--color-ink); }
.indicators-subtitle { margin:0; font-size:var(--font-size-sm); color:var(--color-ink-soft); }
.indicators-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:var(--spacing-md); margin-top:var(--spacing-md); }
.indicator-item { padding:var(--spacing-md); background:var(--color-surface-muted); border:1px solid var(--color-line); border-radius:var(--radius-md); }
.indicator-label { color:var(--color-accent); font-weight:var(--font-weight-semibold); }
.indicator-value { margin:var(--spacing-xs) 0; color:var(--color-ink); font:var(--font-size-xl) var(--font-family-mono); }
.indicator-description { color:var(--color-ink-faint); font-size:var(--font-size-xs); }
@media (max-width:480px) { .indicators-grid { grid-template-columns:repeat(2,1fr); gap:var(--spacing-sm); } .indicator-item { padding:var(--spacing-sm); } .indicator-value { font-size:var(--font-size-base); } }
</style>
