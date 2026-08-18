<script setup lang="ts">
import { X } from 'lucide-vue-next'

defineProps<{
  count: number
  label?: string
}>()

defineEmits<{
  clear: []
}>()
</script>

<template>
  <Transition name="selection-toolbar">
    <div v-if="count > 0" class="selection-toolbar" role="toolbar" aria-label="批量操作">
      <strong>{{ count }} {{ label || '项已选择' }}</strong>
      <div class="selection-toolbar__actions"><slot /></div>
      <button class="selection-toolbar__clear" type="button" aria-label="清除选择" title="清除选择" @click="$emit('clear')"><X :size="15" />清除</button>
    </div>
  </Transition>
</template>

<style scoped>
.selection-toolbar { position: sticky; bottom: 16px; z-index: var(--z-sticky); display: flex; align-items: center; gap: 12px; width: fit-content; max-width: 100%; margin: 16px auto 0; padding: 9px 10px 9px 14px; border: 1px solid var(--color-line-strong); border-radius: var(--radius-full); background: var(--color-ink); color: var(--color-surface); box-shadow: var(--shadow-lg); }
.selection-toolbar strong { font-size: 12px; white-space: nowrap; }
.selection-toolbar__actions { display: flex; gap: 6px; flex-wrap: wrap; }
.selection-toolbar__actions :deep(.button) { min-height: 32px; border-color: color-mix(in srgb, var(--color-surface) 30%, transparent); background: transparent; color: var(--color-surface); }
.selection-toolbar__clear { display: inline-flex; align-items: center; gap: 4px; min-height: 30px; padding: 0 8px; border-left: 1px solid color-mix(in srgb, var(--color-surface) 25%, transparent); color: var(--color-ink-soft); font-size: 12px; }
.selection-toolbar-enter-active, .selection-toolbar-leave-active { transition: opacity var(--duration-fast) var(--ease-smooth), transform var(--duration-fast) var(--ease-out); }
.selection-toolbar-enter-from, .selection-toolbar-leave-to { opacity: 0; transform: translateY(8px); }
@media (max-width: 640px) { .selection-toolbar { width: calc(100% - 16px); justify-content: space-between; border-radius: var(--radius-md); } }
</style>
