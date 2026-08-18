<script setup lang="ts">
interface Props {
  state: 'loading' | 'available' | 'partial' | 'unavailable'
  source?: string
  asOf?: string
  error?: string
}

defineProps<Props>()
</script>

<template>
  <section class="research-state-panel" :class="`research-state-panel--${state}`" role="status">
    <strong v-if="state === 'loading'">加载中...</strong>
    <strong v-else-if="state === 'available'">数据可用</strong>
    <strong v-else-if="state === 'partial'">数据部分可用</strong>
    <strong v-else>数据不可用</strong>
    <span v-if="source">来源 {{ source }}</span>
    <span v-if="asOf">截至 {{ asOf }}</span>
    <span v-if="error" class="research-state-panel__error">{{ error }}</span>
  </section>
</template>

<style scoped>
.research-state-panel {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-line);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

.research-state-panel--available { border-color: var(--color-success); }
.research-state-panel--partial { border-color: var(--color-warn); }
.research-state-panel--unavailable { border-color: var(--color-danger); }
.research-state-panel__error { color: var(--color-danger); }
</style>
