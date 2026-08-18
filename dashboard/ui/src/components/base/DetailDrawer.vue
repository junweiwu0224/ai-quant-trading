<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
  title?: string
  eyebrow?: string
  labelledBy?: string
}>()

const closeButton = ref<HTMLButtonElement | null>(null)
let returnFocus: HTMLElement | null = null

defineEmits<{
  close: []
}>()

watch(() => props.open, (open, previous) => {
  if (open && !previous) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    void nextTick(() => closeButton.value?.focus())
  } else if (!open && previous) {
    void nextTick(() => returnFocus?.focus())
  }
})
</script>

<template>
  <Transition name="drawer-scrim">
    <div v-if="open" class="detail-drawer-backdrop" @click.self="$emit('close')">
      <aside class="detail-drawer" role="dialog" aria-modal="true" :aria-labelledby="labelledBy || 'detail-drawer-title'">
        <header class="detail-drawer__head">
          <div>
            <span v-if="eyebrow" class="detail-drawer__eyebrow">{{ eyebrow }}</span>
            <h2 :id="labelledBy || 'detail-drawer-title'">{{ title || '详情' }}</h2>
          </div>
          <button ref="closeButton" class="icon-button" type="button" aria-label="关闭详情" title="关闭详情" @click="$emit('close')"><X :size="18" /></button>
        </header>
        <div class="detail-drawer__body"><slot /></div>
        <footer v-if="$slots.footer" class="detail-drawer__foot"><slot name="footer" /></footer>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.detail-drawer-backdrop { position: fixed; inset: 0; z-index: var(--z-modal-backdrop); display: flex; justify-content: flex-end; background: color-mix(in srgb, var(--color-ink) 40%, transparent); }
.detail-drawer { width: min(520px, 100vw); height: 100%; overflow: auto; background: var(--color-surface); border-left: 1px solid var(--color-line-strong); box-shadow: var(--shadow-xl); }
.detail-drawer__head { position: sticky; top: 0; z-index: 1; display: flex; justify-content: space-between; gap: 16px; padding: 22px 24px; border-bottom: 1px solid var(--color-line); background: color-mix(in srgb, var(--color-surface) 92%, transparent); backdrop-filter: blur(12px); }
.detail-drawer__head h2 { margin-top: 4px; font-size: 20px; }
.detail-drawer__eyebrow { color: var(--color-accent-strong); font: 11px var(--font-family-mono); letter-spacing: .08em; }
.detail-drawer__body { padding: 24px; }
.detail-drawer__foot { position: sticky; bottom: 0; padding: 14px 24px; border-top: 1px solid var(--color-line); background: var(--color-surface); }
.drawer-scrim-enter-active, .drawer-scrim-leave-active { transition: opacity var(--duration-normal) var(--ease-smooth); }
.drawer-scrim-enter-from, .drawer-scrim-leave-to { opacity: 0; }
.drawer-scrim-enter-active .detail-drawer, .drawer-scrim-leave-active .detail-drawer { transition: transform var(--duration-normal) var(--ease-out); }
.drawer-scrim-enter-from .detail-drawer, .drawer-scrim-leave-to .detail-drawer { transform: translateX(28px); }
@media (max-width: 640px) { .detail-drawer__head, .detail-drawer__body, .detail-drawer__foot { padding-left: 16px; padding-right: 16px; } }
</style>
