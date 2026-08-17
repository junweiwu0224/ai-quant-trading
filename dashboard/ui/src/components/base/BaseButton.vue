<script setup lang="ts">
import { computed } from 'vue'

export interface BaseButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
  type?: 'button' | 'submit' | 'reset'
}

const props = withDefaults(defineProps<BaseButtonProps>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  type: 'button'
})

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const buttonClasses = computed(() => {
  const classes = ['base-button', `base-button--${props.variant}`, `base-button--${props.size}`]
  if (props.disabled || props.loading) classes.push('base-button--disabled')
  if (props.loading) classes.push('base-button--loading')
  return classes.join(' ')
})

const handleClick = (event: MouseEvent) => {
  if (!props.disabled && !props.loading) {
    emit('click', event)
  }
}
</script>

<template>
  <button
    :class="buttonClasses"
    :type="type"
    :disabled="disabled || loading"
    @click="handleClick"
  >
    <span v-if="loading" class="base-button__spinner"></span>
    <span class="base-button__content" :class="{ 'base-button__content--loading': loading }">
      <slot />
    </span>
  </button>
</template>

<style scoped>
.base-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  font-family: var(--font-family-base);
  font-weight: var(--font-weight-medium);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
  white-space: nowrap;
  user-select: none;
}

/* Sizes */
.base-button--sm {
  height: 32px;
  padding: 0 var(--spacing-md);
  font-size: var(--font-size-sm);
}

.base-button--md {
  height: var(--touch-target-min);
  padding: 0 var(--spacing-lg);
  font-size: var(--font-size-base);
}

.base-button--lg {
  height: 52px;
  padding: 0 var(--spacing-xl);
  font-size: var(--font-size-lg);
}

/* Primary variant */
.base-button--primary {
  background-color: var(--color-accent);
  color: var(--color-surface);
}

.base-button--primary:hover:not(.base-button--disabled) {
  background-color: var(--color-accent-strong);
  box-shadow: var(--shadow-sm);
}

.base-button--primary:active:not(.base-button--disabled) {
  transform: translateY(1px);
}

/* Secondary variant */
.base-button--secondary {
  background-color: var(--color-surface-muted);
  color: var(--color-ink);
  border: 1px solid var(--color-line);
}

.base-button--secondary:hover:not(.base-button--disabled) {
  background-color: var(--color-surface-strong);
  border-color: var(--color-ink-faint);
}

.base-button--secondary:active:not(.base-button--disabled) {
  transform: translateY(1px);
}

/* Ghost variant */
.base-button--ghost {
  background-color: transparent;
  color: var(--color-ink-soft);
}

.base-button--ghost:hover:not(.base-button--disabled) {
  background-color: var(--color-surface-muted);
  color: var(--color-ink);
}

.base-button--ghost:active:not(.base-button--disabled) {
  background-color: var(--color-surface-strong);
}

/* Danger variant */
.base-button--danger {
  background-color: var(--color-danger);
  color: var(--color-surface);
}

.base-button--danger:hover:not(.base-button--disabled) {
  background-color: var(--color-danger-strong);
  box-shadow: var(--shadow-sm);
}

.base-button--danger:active:not(.base-button--disabled) {
  transform: translateY(1px);
}

/* Disabled state */
.base-button--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading state */
.base-button--loading {
  cursor: wait;
}

.base-button__content--loading {
  opacity: 0.4;
}

.base-button__spinner {
  position: absolute;
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: var(--radius-full);
  animation: spin var(--duration-slower) linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Focus styles for accessibility */
.base-button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
