<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight, ShieldCheck } from 'lucide-vue-next'

export interface BacktestDraftProps {
  market: string
  symbol: string
}

const props = defineProps<BacktestDraftProps>()

const validationTarget = computed(() => ({
  path: '/app/validation',
  query: { market: props.market, symbol: props.symbol, source: 'research' },
}))
</script>

<template>
  <section class="panel backtest-handoff">
    <div class="panel-head">
      <div>
        <h2>进入验证工作区</h2>
        <p>回测参数、样本外检验、Monte Carlo 与组合资格在统一验证链路中执行。</p>
      </div>
      <ShieldCheck :size="18" class="faint" />
    </div>
    <div class="panel-body backtest-handoff-body">
      <dl class="backtest-context">
        <div><dt>市场</dt><dd>{{ market }}</dd></div>
        <div><dt>标的</dt><dd>{{ symbol }}</dd></div>
        <div><dt>执行边界</dt><dd>仅研究与模拟验证</dd></div>
      </dl>
      <p>当前页面不会保存本地草案或生成占位结果。进入验证工作区后，所有指标均来自实际回测响应。</p>
      <RouterLink class="button primary" :to="validationTarget">
        打开验证工作区
        <ArrowRight :size="15" />
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.backtest-handoff { max-width: 760px; }
.backtest-handoff-body { display: grid; gap: 18px; }
.backtest-handoff-body > p { margin: 0; color: var(--color-ink-soft); font-size: 13px; line-height: 1.6; }
.backtest-handoff-body > .button { justify-self: start; }
.backtest-context { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin: 0; background: var(--color-line); border: 1px solid var(--color-line); }
.backtest-context div { min-width: 0; padding: 12px; background: var(--color-surface); }
.backtest-context dt { color: var(--color-ink-faint); font-size: 11px; }
.backtest-context dd { margin: 5px 0 0; overflow-wrap: anywhere; color: var(--color-ink); font-size: 13px; font-weight: 650; }

@media (max-width: 600px) {
  .backtest-context { grid-template-columns: 1fr; }
  .backtest-handoff-body > .button { width: 100%; }
}
</style>
