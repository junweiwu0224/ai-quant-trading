<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import Sidebar from './Sidebar.vue'
import MobileNav from './MobileNav.vue'
import MainContent from './MainContent.vue'
import TokenUsagePanel from './ai/TokenUsagePanel.vue'

const menuOpen = ref(false)
const tokenPanelOpen = ref(false)

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && menuOpen.value) closeMenu()
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.body.classList.remove('drawer-open')
})

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function openTokenPanel() {
  tokenPanelOpen.value = true
  menuOpen.value = false
}

function closeTokenPanel() {
  tokenPanelOpen.value = false
}

watch(menuOpen, (open) => {
  document.body.classList.toggle('drawer-open', open)
})
</script>

<template>
  <div class="app-shell">
    <Sidebar id="mobile-navigation" :open="menuOpen" @close="closeMenu" @open-token-panel="openTokenPanel" />
    <Transition name="scrim">
      <div v-if="menuOpen" class="scrim mobile-only" @click="closeMenu" />
    </Transition>
    <MainContent :menu-open="menuOpen" @toggle-menu="toggleMenu" />
    <MobileNav />
    <TokenUsagePanel :open="tokenPanelOpen" @close="closeTokenPanel" />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--color-bg-primary);
}

.scrim {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-ink) 45%, transparent);
  z-index: 99;
}

.scrim-enter-active,
.scrim-leave-active {
  transition: opacity var(--duration-normal) var(--ease-smooth);
}

.scrim-enter-from,
.scrim-leave-to {
  opacity: 0;
}

@media (min-width: 768px) {
  .mobile-only {
    display: none;
  }
}

@media (max-width: 767px) {
  .mobile-only {
    display: block;
  }
}
</style>
