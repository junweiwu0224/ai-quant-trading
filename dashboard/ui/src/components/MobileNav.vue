<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { BookOpen, FileText, BarChart3, LayoutDashboard, Search, Moon, Sun } from 'lucide-vue-next'
import { useTheme } from '../composables/useTheme'

const { isDark, toggleTheme } = useTheme()

const mobileNav = [
  { to: '/app/decision', label: '决策', icon: LayoutDashboard },
  { to: '/app/intelligence', label: '情报', icon: BarChart3 },
  { to: '/app/reports', label: '报告', icon: FileText },
  { to: '/app/research', label: '研究', icon: Search },
]
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
    <button class="mobile-nav-item theme-btn" @click="toggleTheme">
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
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border);
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
  transition: all 0.2s ease;
  flex: 1;
  max-width: 80px;
}

.mobile-nav-item:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.mobile-nav-item.router-link-active {
  color: var(--color-accent);
  background: var(--color-accent-bg);
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
