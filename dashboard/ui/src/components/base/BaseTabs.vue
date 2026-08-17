<script setup lang="ts">
import { computed } from 'vue'

export interface Tab {
  id: string
  label: string
  disabled?: boolean
  badge?: string | number
}

export interface BaseTabsProps {
  modelValue: string
  tabs: Tab[]
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<BaseTabsProps>(), {
  size: 'md'
})

const emit = defineEmits<{
  'update:modelValue': [id: string]
  change: [id: string]
}>()

const tabsClasses = computed(() => {
  return ['base-tabs', `base-tabs--${props.size}`].join(' ')
})

const selectTab = (tab: Tab) => {
  if (!tab.disabled && tab.id !== props.modelValue) {
    emit('update:modelValue', tab.id)
    emit('change', tab.id)
  }
}
</script>

<template>
  <div :class="tabsClasses">
    <div class="base-tabs__nav">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="base-tabs__tab"
        :class="{
          'base-tabs__tab--active': tab.id === modelValue,
          'base-tabs__tab--disabled': tab.disabled
        }"
        :disabled="tab.disabled"
        @click="selectTab(tab)"
      >
        <span class="base-tabs__label">{{ tab.label }}</span>
        <span v-if="tab.badge !== undefined" class="base-tabs__badge">{{ tab.badge }}</span>
      </button>
    </div>

    <div class="base-tabs__content">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.base-tabs {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.base-tabs__nav {
  display: flex;
  gap: var(--spacing-xs);
  border-bottom: 1px solid var(--color-line);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.base-tabs__nav::-webkit-scrollbar {
  height: 2px;
}

.base-tabs__nav::-webkit-scrollbar-track {
  background: transparent;
}

.base-tabs__nav::-webkit-scrollbar-thumb {
  background: var(--color-line);
  border-radius: var(--radius-full);
}

.base-tabs__tab {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  font-family: var(--font-family-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink-soft);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
  white-space: nowrap;
  outline: none;
}

/* Sizes */
.base-tabs--sm .base-tabs__tab {
  min-height: 36px;
  font-size: var(--font-size-sm);
}

.base-tabs--md .base-tabs__tab {
  min-height: var(--touch-target-min);
  font-size: var(--font-size-base);
}

.base-tabs--lg .base-tabs__tab {
  min-height: 52px;
  font-size: var(--font-size-lg);
}

/* States */
.base-tabs__tab:hover:not(.base-tabs__tab--disabled) {
  color: var(--color-ink);
  background-color: var(--color-surface-muted);
}

.base-tabs__tab--active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

.base-tabs__tab--active:hover {
  background-color: transparent;
}

.base-tabs__tab--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.base-tabs__tab:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* Badge */
.base-tabs__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 var(--spacing-xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-surface);
  background-color: var(--color-accent);
  border-radius: var(--radius-full);
}

.base-tabs__tab--active .base-tabs__badge {
  background-color: var(--color-accent-strong);
}

.base-tabs__content {
  /* Content slot area */
}
</style>
