<script setup lang="ts">
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle, MinusCircle, RefreshCw } from 'lucide-vue-next'

export type AsyncState = 'idle' | 'loading' | 'refreshing' | 'partial' | 'stale' | 'success' | 'empty' | 'error' | 'submitting' | 'rollback'

const props = withDefaults(defineProps<{
  state: AsyncState
  title?: string
  message?: string
  source?: string
  asOf?: string
  retryLabel?: string
  compact?: boolean
}>(), {
  title: '',
  message: '',
  source: '',
  asOf: '',
  retryLabel: '重试',
  compact: false,
})

defineEmits<{
  retry: []
}>()

const stateCopy: Record<AsyncState, { label: string; icon: typeof LoaderCircle; tone: string }> = {
  idle: { label: '等待', icon: Clock3, tone: 'idle' },
  loading: { label: '读取中', icon: LoaderCircle, tone: 'loading' },
  refreshing: { label: '后台刷新', icon: RefreshCw, tone: 'refreshing' },
  partial: { label: '部分可用', icon: MinusCircle, tone: 'partial' },
  stale: { label: '可能过期', icon: Clock3, tone: 'stale' },
  success: { label: '已同步', icon: CheckCircle2, tone: 'success' },
  empty: { label: '暂无结果', icon: MinusCircle, tone: 'empty' },
  error: { label: '读取失败', icon: AlertCircle, tone: 'error' },
  submitting: { label: '提交中', icon: LoaderCircle, tone: 'submitting' },
  rollback: { label: '已回滚', icon: RefreshCw, tone: 'rollback' },
}

const copy = stateCopy[props.state]
</script>

<template>
  <div
    class="async-state"
    :class="[`async-state--${copy.tone}`, { 'async-state--compact': compact }]"
    :role="state === 'error' ? 'alert' : 'status'"
    :aria-live="state === 'error' ? 'assertive' : ['refreshing', 'success', 'partial', 'rollback'].includes(state) ? 'polite' : 'off'"
  >
    <component :is="copy.icon" class="async-state__icon" :class="{ spin: state === 'loading' || state === 'refreshing' || state === 'submitting' }" :size="compact ? 14 : 16" aria-hidden="true" />
    <div class="async-state__copy">
      <strong>{{ title || copy.label }}</strong>
      <span v-if="message">{{ message }}</span>
      <span v-if="source || asOf" class="async-state__meta">
        <template v-if="source">{{ source }}</template><template v-if="source && asOf"> · </template><template v-if="asOf">截至 {{ asOf }}</template>
      </span>
    </div>
    <button v-if="state === 'error'" class="async-state__retry" type="button" @click="$emit('retry')">{{ retryLabel }}</button>
  </div>
</template>

<style scoped>
.async-state { display: flex; align-items: flex-start; gap: 9px; min-width: 0; padding: 11px 13px; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink-soft); }
.async-state__icon { flex: 0 0 auto; margin-top: 1px; }
.async-state__copy { display: grid; gap: 2px; min-width: 0; font-size: var(--font-size-sm); line-height: 1.45; }
.async-state__copy strong { color: var(--color-ink); font-size: 12px; }
.async-state__copy span { overflow-wrap: anywhere; }
.async-state__meta { color: var(--color-ink-faint); font-family: var(--font-family-mono); font-size: 11px; }
.async-state__retry { flex: 0 0 auto; margin-left: auto; min-height: 30px; padding: 0 10px; border: 1px solid currentColor; border-radius: var(--radius-sm); color: inherit; background: transparent; font-size: 12px; }
.async-state--compact { padding: 6px 9px; border: 0; background: transparent; }
.async-state--loading .async-state__icon, .async-state--refreshing .async-state__icon, .async-state--submitting .async-state__icon { color: var(--color-accent); }
.async-state--success .async-state__icon { color: var(--color-success); }
.async-state--partial .async-state__icon, .async-state--stale .async-state__icon { color: var(--color-data-delayed); }
.async-state--error .async-state__icon, .async-state--rollback .async-state__icon { color: var(--color-danger); }
.async-state--error { border-color: color-mix(in srgb, var(--color-danger) 35%, var(--color-line)); background: var(--color-danger-bg); }
@media (prefers-reduced-motion: reduce) { .async-state__icon.spin { animation: none; } }
</style>
