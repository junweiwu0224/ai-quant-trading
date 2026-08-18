<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { Moon, Sun } from 'lucide-vue-next'
import { useTheme } from '../composables/useTheme'
import { MOBILE_WORKFLOWS } from '../navigation/workflows'

const { isDark, toggleTheme } = useTheme()

const mobileNav = MOBILE_WORKFLOWS
</script>

<template>
  <nav class="mobile-nav mobile-only" aria-label="移动导航">
    <RouterLink
      v-for="item in mobileNav"
      :key="item.to"
      :to="item.to"
      class="mobile-nav-item"
    >
      <component :is="item.icon" :size="18" />
      <span>{{ item.label }}</span>
    </RouterLink>
    <button class="mobile-nav-item theme-btn" type="button" :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'" :aria-pressed="isDark" @click="toggleTheme">
      <component :is="isDark ? Sun : Moon" :size="18" />
      <span>主题</span>
    </button>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 64px;
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
  border-top: 1px solid var(--color-border);
  backdrop-filter: blur(14px);
  display: flex;
  justify-content: space-around;
  align-items: center;
  z-index: 50;
  padding: 0 var(--spacing-2);
}

.mobile-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1);
  padding: var(--spacing-2);
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 11px;
  border-radius: var(--radius-md);
  transition: color var(--duration-fast) var(--ease-smooth), background-color var(--duration-fast) var(--ease-smooth), transform var(--duration-fast) var(--ease-smooth);
  flex: 1;
  max-width: 80px;
}

.mobile-nav-item:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.mobile-nav-item.router-link-active {
  color: var(--color-accent);
  background: var(--color-accent-pale);
}

.theme-btn {
  background: none;
  border: none;
  cursor: pointer;
}

@media (min-width: 768px) {
  .mobile-only {
    display: none;
  }
}

@media (max-width: 767px) {
  .mobile-only {
    display: flex;
  }
}
</style>
