<script setup lang="ts">
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'
import ResearchStatePanel from './ResearchStatePanel.vue'

const props = withDefaults(defineProps<{
  market?: string
  symbol?: string
  decision?: { type?: string; confidence?: number; reasoning?: string[]; riskWarning?: string } | null
  state?: 'loading' | 'available' | 'partial' | 'unavailable'
  error?: string
}>(), { decision: null, state: 'unavailable' })

function label(type?: string) { return type === 'buy' ? '买入' : type === 'sell' ? '卖出' : type === 'hold' ? '观望' : '无法判断' }
function variant(type?: string): 'success' | 'danger' | 'default' | 'warning' { return type === 'buy' ? 'success' : type === 'sell' ? 'danger' : type === 'hold' ? 'default' : 'warning' }
const confidence = () => typeof props.decision?.confidence === 'number' && Number.isFinite(props.decision.confidence) ? `${props.decision.confidence}%` : '—'
</script>

<template>
  <div class="decision-card-wrapper">
    <h2 class="decision-title">研究结论</h2>
    <ResearchStatePanel :state="state || 'unavailable'" :error="error || (!decision ? '当前无法生成确定性结论；可继续人工研究或进入验证。' : undefined)" />
    <BaseCard v-if="decision" class="decision-card" padding="lg" bordered elevated><div class="decision-header"><BaseTag :variant="variant(decision.type)" size="lg">{{ label(decision.type) }}</BaseTag><div class="decision-confidence"><span>置信度</span><strong>{{ confidence() }}</strong></div></div><div class="decision-body"><div><h3>关键依据</h3><ul><li v-for="(reason, index) in decision.reasoning || []" :key="index">{{ reason }}</li><li v-if="!decision.reasoning?.length">接口未提供文字依据。</li></ul></div><div class="risk-section"><strong>风险提示</strong><span>{{ decision.riskWarning || '这不是交易指令。研究结论不等于交易指令，请先完成验证和风控检查。' }}</span></div></div></BaseCard>
  </div>
</template>

<style scoped>
.decision-card-wrapper { width:100%; }
.decision-title { margin:var(--spacing-lg) 0 var(--spacing-md); font-size:var(--font-size-xl); color:var(--color-ink); }
.decision-card { margin-top:var(--spacing-md); border:2px solid var(--color-accent); }
.decision-header { display:flex; justify-content:space-between; align-items:center; gap:var(--spacing-lg); padding-bottom:var(--spacing-lg); border-bottom:1px solid var(--color-line); }
.decision-confidence { display:flex; flex-direction:column; align-items:flex-end; gap:var(--spacing-xs); color:var(--color-ink-faint); font-size:var(--font-size-xs); }
.decision-confidence strong { color:var(--color-ink); font:var(--font-size-2xl) var(--font-family-mono); }
.decision-body { display:flex; flex-direction:column; gap:var(--spacing-lg); padding-top:var(--spacing-lg); color:var(--color-ink-soft); }
.decision-body h3 { margin:0 0 var(--spacing-sm); color:var(--color-ink); font-size:var(--font-size-base); }
ul { margin:0; padding-left:var(--spacing-lg); display:grid; gap:var(--spacing-sm); }
.risk-section { display:flex; flex-direction:column; gap:var(--spacing-xs); padding:var(--spacing-md); background:var(--color-warn-bg); border:1px solid color-mix(in srgb, var(--color-warn) 35%, var(--color-line)); border-radius:var(--radius-md); }
.risk-section strong { color:var(--color-warn); }
</style>
