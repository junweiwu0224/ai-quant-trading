<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import MobileNav from './MobileNav.vue'
import MainContent from './MainContent.vue'
import TokenUsagePanel from './ai/TokenUsagePanel.vue'

const menuOpen = ref(false)
const tokenPanelOpen = ref(false)

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
</script>

<template>
  <div class="app-shell">
    <Sidebar :open="menuOpen" @close="closeMenu" @open-token-panel="openTokenPanel" />
    <div v-if="menuOpen" class="scrim mobile-only" @click="closeMenu" />
    <MainContent @toggle-menu="toggleMenu" />
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
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
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
