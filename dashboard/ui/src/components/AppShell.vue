<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import MobileNav from './MobileNav.vue'
import MainContent from './MainContent.vue'

const menuOpen = ref(false)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}
</script>

<template>
  <div class="app-shell">
    <Sidebar :open="menuOpen" @close="closeMenu" />
    <div v-if="menuOpen" class="scrim mobile-only" @click="closeMenu" />
    <MainContent @toggle-menu="toggleMenu" />
    <MobileNav />
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
