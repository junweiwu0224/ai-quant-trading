<script setup lang="ts">
import { computed } from 'vue'

export interface BaseTagProps {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'up' | 'down'
  size?: 'sm' | 'md' | 'lg'
  closable?: boolean
}

const props = withDefaults(defineProps<BaseTagProps>(), {
  variant: 'default',
  size: 'md',
  closable: false
})

const emit = defineEmits<{
  close: []
}>()

const tagClasses = computed(() => {
  return ['base-tag', `base-tag--${props.variant}`, `base-tag--${props.size}`].join(' ')
})

const handleClose = () => {
  emit('close')
}
</script>

<template>
  <span :class="tagClasses">
    <span class="base-tag__content">
      <slot />
    </span>
    <button
      v-if="closable"
      class="base-tag__close"
      type="button"
      aria-label="Close"
      @click="handleClose"
    >
      <svg viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>
    </button>
  </span>
</template>

<style scoped>
.base-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-family: var(--font-family-base);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: all var(--duration-fast) var(--ease-smooth);
}

/* Sizes */
.base-tag--sm {
  height: 20px;
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-xs);
}

.base-tag--md {
  height: 24px;
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.base-tag--lg {
  height: 28px;
  padding: 0 var(--spacing-md);
  font-size: var(--font-size-base);
}

/* Variants */
.base-tag--default {
  background-color: var(--color-surface-muted);
  color: var(--color-ink-soft);
}

.base-tag--success {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.base-tag--warning {
  background-color: var(--color-warn-bg);
  color: var(--color-warn);
}

.base-tag--danger {
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
}

.base-tag--info {
  background-color: var(--color-info-bg);
  color: var(--color-info);
}

.base-tag--up {
  background-color: var(--color-success-bg);
  color: var(--color-up);
}

.base-tag--down {
  background-color: var(--color-danger-bg);
  color: var(--color-down);
}

/* Content */
.base-tag__content {
  line-height: 1;
}

/* Close button */
.base-tag__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  padding: 0;
  background: transparent;
  border: none;
  color: currentColor;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity var(--duration-fast) var(--ease-smooth);
}

.base-tag__close:hover {
  opacity: 1;
}

.base-tag__close svg {
  width: 100%;
  height: 100%;
}

.base-tag__close:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
  border-radius: var(--radius-sm);
}
</style>
