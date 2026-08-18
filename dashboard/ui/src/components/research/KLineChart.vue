<script setup lang="ts">
import { computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'
import ResearchStatePanel from './ResearchStatePanel.vue'
import type { KLineBar } from '../../api/types'

const props = withDefaults(defineProps<{
  market: string
  symbol: string
  bars?: KLineBar[]
  state?: 'loading' | 'available' | 'partial' | 'unavailable'
  source?: string
  asOf?: string
  error?: string
}>(), { bars: () => [], state: 'loading' })

const chartTitle = computed(() => `K线图 - ${props.symbol}`)
const validBars = computed(() => props.bars.filter((bar) => Number.isFinite(Number(bar.close))))
const points = computed(() => {
  const valid = validBars.value
  if (!valid.length) return ''
  const values = valid.map((bar) => Number(bar.close))
  const min = Math.min(...values)
  const spread = Math.max(Math.max(...values) - min, 0.0001)
  return valid.map((bar, index) => {
    const x = 12 + index / Math.max(valid.length - 1, 1) * 776
    const y = 218 - (Number(bar.close) - min) / spread * 196
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})
</script>

<template>
  <BaseCard class="kline-chart">
    <div class="chart-header"><h3 class="chart-title">{{ chartTitle }}</h3><div class="chart-meta"><span class="meta-item">市场: {{ market }}</span><span v-if="source" class="meta-item">来源: {{ source }}</span></div></div>
    <ResearchStatePanel :state="state" :source="source" :as-of="asOf" :error="error" />
    <div v-if="state !== 'loading' && points" class="chart-container"><svg viewBox="0 0 800 240" role="img" :aria-label="`${symbol} 收盘价走势`"><line x1="12" y1="218" x2="788" y2="218" class="chart-axis" /><polyline :points="points" class="chart-line" fill="none" /></svg><div class="chart-labels"><span>{{ validBars[0]?.date || '—' }}</span><strong>{{ validBars[validBars.length - 1]?.close ?? '—' }}</strong><span>{{ validBars[validBars.length - 1]?.date || '—' }}</span></div></div>
    <div v-else-if="state !== 'loading'" class="empty chart-empty">当前股票没有可绘制的有效 K 线数据。</div>
  </BaseCard>
</template>

<style scoped>
.kline-chart { width: 100%; }
.chart-header { display:flex; justify-content:space-between; align-items:center; gap:var(--spacing-md); margin-bottom:var(--spacing-md); padding-bottom:var(--spacing-md); border-bottom:1px solid var(--color-line); }
.chart-title { margin:0; font-size:var(--font-size-lg); color:var(--color-ink); }
.chart-meta { display:flex; flex-wrap:wrap; gap:var(--spacing-sm); font-size:var(--font-size-sm); color:var(--color-ink-soft); }
.meta-item { padding:var(--spacing-xs) var(--spacing-sm); background:var(--color-surface-muted); border-radius:var(--radius-sm); }
.chart-container { margin-top:var(--spacing-md); padding:var(--spacing-md); background:var(--color-surface-muted); border:1px solid var(--color-line); border-radius:var(--radius-md); }
.chart-container svg { width:100%; height:360px; display:block; }
.chart-axis { stroke:var(--color-line); }
.chart-line { stroke:var(--color-accent); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }
.chart-labels { display:flex; justify-content:space-between; color:var(--color-ink-soft); font-size:var(--font-size-xs); }
.chart-empty { min-height:160px; display:grid; place-items:center; }
@media (max-width:768px) { .chart-container svg { height:260px; } .chart-header { flex-direction:column; align-items:flex-start; } }
</style>
