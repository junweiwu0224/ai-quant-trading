<script setup lang="ts">
import { computed, useAttrs } from 'vue'

export interface BaseInputProps {
  modelValue?: string | number
  type?: 'text' | 'number' | 'email' | 'password' | 'search' | 'tel' | 'url'
  placeholder?: string
  disabled?: boolean
  error?: string | boolean
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<BaseInputProps>(), {
  type: 'text',
  disabled: false,
  size: 'md'
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  focus: [event: FocusEvent]
  blur: [event: FocusEvent]
}>()

const attrs = useAttrs()

const inputClasses = computed(() => {
  const classes = ['base-input', `base-input--${props.size}`]
  if (props.error) classes.push('base-input--error')
  if (props.disabled) classes.push('base-input--disabled')
  return classes.join(' ')
})

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('update:modelValue', value)
}

const handleFocus = (event: FocusEvent) => {
  emit('focus', event)
}

const handleBlur = (event: FocusEvent) => {
  emit('blur', event)
}
</script>

<template>
  <div class="base-input-wrapper">
    <input
      :class="inputClasses"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      v-bind="attrs"
      @input="handleInput"
      @focus="handleFocus"
      @blur="handleBlur"
    />
    <div v-if="error && typeof error === 'string'" class="base-input__error">
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.base-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.base-input {
  width: 100%;
  font-family: var(--font-family-base);
  font-size: var(--font-size-base);
  color: var(--color-ink);
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  transition: all var(--duration-fast) var(--ease-smooth);
  outline: none;
}

.base-input::placeholder {
  color: var(--color-ink-faint);
}

/* Sizes */
.base-input--sm {
  height: 32px;
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.base-input--md {
  height: var(--touch-target-min);
  padding: 0 var(--spacing-md);
  font-size: var(--font-size-base);
}

.base-input--lg {
  height: 52px;
  padding: 0 var(--spacing-lg);
  font-size: var(--font-size-lg);
}

/* States */
.base-input:hover:not(.base-input--disabled) {
  border-color: var(--color-ink-faint);
}

.base-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-pale);
}

.base-input--error {
  border-color: var(--color-danger);
}

.base-input--error:focus {
  box-shadow: 0 0 0 3px var(--color-danger-bg);
}

.base-input--disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: var(--color-surface-muted);
}

.base-input__error {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  padding-left: var(--spacing-xs);
}

/* Number input arrows styling */
.base-input[type="number"]::-webkit-inner-spin-button,
.base-input[type="number"]::-webkit-outer-spin-button {
  opacity: 1;
}
</style>
