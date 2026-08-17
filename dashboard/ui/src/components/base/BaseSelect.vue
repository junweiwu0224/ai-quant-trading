<script setup lang="ts">
import { computed, ref } from 'vue'

export interface SelectOption {
  label: string
  value: string | number
  disabled?: boolean
}

export interface BaseSelectProps {
  modelValue?: string | number
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  error?: string | boolean
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<BaseSelectProps>(), {
  disabled: false,
  size: 'md',
  placeholder: 'Select an option'
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  change: [value: string | number]
}>()

const isOpen = ref(false)
const selectRef = ref<HTMLDivElement | null>(null)

const selectClasses = computed(() => {
  const classes = ['base-select', `base-select--${props.size}`]
  if (props.error) classes.push('base-select--error')
  if (props.disabled) classes.push('base-select--disabled')
  if (isOpen.value) classes.push('base-select--open')
  return classes.join(' ')
})

const selectedOption = computed(() => {
  return props.options.find(opt => opt.value === props.modelValue)
})

const displayText = computed(() => {
  return selectedOption.value?.label || props.placeholder
})

const toggleDropdown = () => {
  if (!props.disabled) {
    isOpen.value = !isOpen.value
  }
}

const selectOption = (option: SelectOption) => {
  if (!option.disabled) {
    emit('update:modelValue', option.value)
    emit('change', option.value)
    isOpen.value = false
  }
}

const handleClickOutside = (event: MouseEvent) => {
  if (selectRef.value && !selectRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

// Close dropdown when clicking outside
if (typeof window !== 'undefined') {
  document.addEventListener('click', handleClickOutside)
}
</script>

<template>
  <div class="base-select-wrapper">
    <div ref="selectRef" :class="selectClasses" @click="toggleDropdown">
      <div class="base-select__display" :class="{ 'base-select__display--placeholder': !selectedOption }">
        {{ displayText }}
      </div>
      <svg class="base-select__arrow" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>

      <transition name="dropdown">
        <div v-if="isOpen" class="base-select__dropdown">
          <div
            v-for="option in options"
            :key="option.value"
            class="base-select__option"
            :class="{
              'base-select__option--selected': option.value === modelValue,
              'base-select__option--disabled': option.disabled
            }"
            @click.stop="selectOption(option)"
          >
            {{ option.label }}
          </div>
        </div>
      </transition>
    </div>

    <div v-if="error && typeof error === 'string'" class="base-select__error">
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.base-select-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.base-select {
  position: relative;
  width: 100%;
  font-family: var(--font-family-base);
  font-size: var(--font-size-base);
  color: var(--color-ink);
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
}

/* Sizes */
.base-select--sm {
  height: 32px;
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.base-select--md {
  height: var(--touch-target-min);
  padding: 0 var(--spacing-md);
  font-size: var(--font-size-base);
}

.base-select--lg {
  height: 52px;
  padding: 0 var(--spacing-lg);
  font-size: var(--font-size-lg);
}

/* Display */
.base-select__display {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-select__display--placeholder {
  color: var(--color-ink-faint);
}

/* Arrow */
.base-select__arrow {
  width: 20px;
  height: 20px;
  color: var(--color-ink-soft);
  transition: transform var(--duration-fast) var(--ease-smooth);
  flex-shrink: 0;
}

.base-select--open .base-select__arrow {
  transform: rotate(180deg);
}

/* States */
.base-select:hover:not(.base-select--disabled) {
  border-color: var(--color-ink-faint);
}

.base-select--open {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-pale);
}

.base-select--error {
  border-color: var(--color-danger);
}

.base-select--disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: var(--color-surface-muted);
}

/* Dropdown */
.base-select__dropdown {
  position: absolute;
  top: calc(100% + var(--spacing-xs));
  left: 0;
  right: 0;
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  max-height: 240px;
  overflow-y: auto;
  z-index: var(--z-dropdown);
}

.base-select__option {
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background-color var(--duration-fast) var(--ease-smooth);
  min-height: var(--touch-target-min);
  display: flex;
  align-items: center;
}

.base-select__option:hover:not(.base-select__option--disabled) {
  background-color: var(--color-surface-muted);
}

.base-select__option--selected {
  background-color: var(--color-accent-pale);
  color: var(--color-accent-strong);
  font-weight: var(--font-weight-medium);
}

.base-select__option--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.base-select__error {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  padding-left: var(--spacing-xs);
}

/* Dropdown animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all var(--duration-fast) var(--ease-smooth);
}

.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
