<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { MOBILE_WORKFLOWS, workspaceForPath } from '../navigation/workflows'

const mobileNav = MOBILE_WORKFLOWS
const route = useRoute()

function isActive(item: typeof mobileNav[number]) {
  return workspaceForPath(route.path)?.id === item.workspace
}
</script>

<template>
  <nav class="mobile-nav mobile-only" aria-label="移动导航">
    <RouterLink
      v-for="item in mobileNav"
      :key="item.to"
      :to="item.to"
      class="mobile-nav-item"
      :class="{ 'workspace-nav-active': isActive(item) }"
    >
      <component :is="item.icon" :size="18" />
      <span>{{ item.navLabel || item.label }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  inset: auto 0 0;
  z-index: 50;
  align-items: center;
}

.mobile-nav-item {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 3px;
  text-decoration: none;
}

@media (min-width: 768px) {
  .mobile-only { display: none; }
}
</style>
