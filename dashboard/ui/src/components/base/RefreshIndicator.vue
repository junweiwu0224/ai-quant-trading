<script setup lang="ts">
import { RefreshCw } from 'lucide-vue-next'

withDefaults(defineProps<{
  state: 'refreshing' | 'stale' | 'live' | 'delayed' | 'unavailable'
  label?: string
  asOf?: string
}>(), {
  label: '',
  asOf: '',
})
</script>

<template>
  <span class="refresh-indicator" :class="`refresh-indicator--${state}`" role="status">
    <RefreshCw :size="13" :class="{ spin: state === 'refreshing' }" aria-hidden="true" />
    <span>{{ label || (state === 'refreshing' ? '正在刷新' : state === 'stale' ? '可能过期' : state === 'live' ? '实时可用' : state === 'delayed' ? '延迟数据' : '暂不可用') }}</span>
    <small v-if="asOf">{{ asOf }}</small>
  </span>
</template>

<style scoped>
.refresh-indicator { display: inline-flex; align-items: center; gap: 6px; min-height: 24px; padding: 0 8px; border: 1px solid var(--color-line); border-radius: var(--radius-full); color: var(--color-ink-soft); background: var(--color-surface); font-size: 11px; white-space: nowrap; }
.refresh-indicator small { color: var(--color-ink-faint); font-family: var(--font-family-mono); }
.refresh-indicator--refreshing { color: var(--color-accent-strong); border-color: color-mix(in srgb, var(--color-accent) 40%, var(--color-line)); }
.refresh-indicator--live { color: var(--color-data-live); }
.refresh-indicator--delayed { color: var(--color-data-delayed); }
.refresh-indicator--stale { color: var(--color-data-stale); }
.refresh-indicator--unavailable { color: var(--color-data-unavailable); }
</style>
