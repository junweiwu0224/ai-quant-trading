<script setup lang="ts">
import { X } from 'lucide-vue-next'

defineProps<{
  label?: string
  value?: string
}>()

defineEmits<{
  clear: []
}>()
</script>

<template>
  <div class="filter-bar" aria-label="当前筛选">
    <span class="filter-bar__label">{{ label || '当前查询' }}</span>
    <span v-if="value" class="filter-bar__value">{{ value }}<button type="button" aria-label="清除筛选" title="清除筛选" @click="$emit('clear')"><X :size="13" /></button></span>
    <span v-else class="filter-bar__empty">未设置条件</span>
    <slot />
  </div>
</template>

<style scoped>
.filter-bar { display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 5px 8px; border: 1px solid var(--color-line); border-radius: var(--radius-sm); background: var(--color-surface-muted); color: var(--color-ink-soft); font-size: 12px; }
.filter-bar__label { color: var(--color-ink-faint); font-family: var(--font-family-mono); font-size: 11px; letter-spacing: .04em; }
.filter-bar__value { display: inline-flex; align-items: center; gap: 5px; padding: 4px 7px; border-radius: var(--radius-full); background: var(--color-accent-pale); color: var(--color-accent-strong); }
.filter-bar__value button { display: inline-flex; color: inherit; }
.filter-bar__empty { color: var(--color-ink-faint); }
</style>
