<script setup lang="ts">
import { computed } from 'vue'

export interface BaseCardProps {
  padding?: 'sm' | 'md' | 'lg'
  elevated?: boolean
  bordered?: boolean
  hoverable?: boolean
}

const props = withDefaults(defineProps<BaseCardProps>(), {
  padding: 'md',
  elevated: false,
  bordered: true,
  hoverable: false
})

const cardClasses = computed(() => {
  const classes = ['base-card', `base-card--padding-${props.padding}`]
  if (props.elevated) classes.push('base-card--elevated')
  if (props.bordered) classes.push('base-card--bordered')
  if (props.hoverable) classes.push('base-card--hoverable')
  return classes.join(' ')
})
</script>

<template>
  <div :class="cardClasses">
    <slot />
  </div>
</template>

<style scoped>
.base-card {
  background-color: var(--color-surface);
  border-radius: var(--radius-lg);
  transition: all var(--duration-normal) var(--ease-smooth);
}

/* Padding variants */
.base-card--padding-sm {
  padding: var(--spacing-md);
}

.base-card--padding-md {
  padding: var(--spacing-lg);
}

.base-card--padding-lg {
  padding: var(--spacing-xl);
}

/* Bordered variant */
.base-card--bordered {
  border: 1px solid var(--color-line);
}

/* Elevated variant */
.base-card--elevated {
  box-shadow: var(--shadow-md);
}

/* Hoverable variant */
.base-card--hoverable {
  cursor: pointer;
}

.base-card--hoverable:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.base-card--hoverable:active {
  transform: translateY(0);
  box-shadow: var(--shadow-md);
}
</style>
