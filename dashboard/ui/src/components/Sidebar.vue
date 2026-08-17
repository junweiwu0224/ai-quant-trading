<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Bell, Boxes, ChevronRight, FileText, FlaskConical, BarChart3, LayoutDashboard, Settings, X, Moon, Sun } from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { useTheme } from '../composables/useTheme'

defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const store = useAppStore()
const { isDark, toggleTheme } = useTheme()

const nav = [
  { to: '/app/decision', label: '决策中心', icon: LayoutDashboard },
  { to: '/app/intelligence', label: '市场情报', icon: BarChart3 },
  { to: '/app/reports', label: '报告', icon: FileText },
  { to: '/app/validation', label: '验证', icon: FlaskConical },
  { to: '/app/research', label: '单股研究', icon: Bell },
  { to: '/app/notifications', label: '通知', icon: Bell },
]

const themeIcon = computed(() => isDark.value ? Sun : Moon)

function handleNavClick() {
  emit('close')
}
</script>

<template>
  <aside class="sidebar" :class="{ open }">
    <div class="brand">
      <div class="brand-mark">AQ</div>
      <div><strong>AI Quant</strong><small>决策工作台</small></div>
      <button class="icon-button mobile-only" title="关闭导航" aria-label="关闭导航" @click="$emit('close')">
        <X :size="18" />
      </button>
    </div>

    <div class="workspace-line">
      <span class="status-dot" />
      {{ store.market === 'CN' ? '中国市场工作区' : store.market }}
    </div>

    <nav class="primary-nav" aria-label="主导航">
      <RouterLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        class="nav-link"
        @click="handleNavClick"
      >
        <component :is="item.icon" :size="18" stroke-width="1.8" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="nav-section-title">工作区</div>

    <nav class="secondary-nav" aria-label="工作区导航">
      <RouterLink to="/app/settings" class="nav-link" @click="handleNavClick">
        <Settings :size="18" />
        <span>设置</span>
      </RouterLink>
      <RouterLink to="/app/more" class="nav-link" @click="handleNavClick">
        <Boxes :size="18" />
        <span>更多工具</span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <button class="theme-toggle" @click="toggleTheme">
        <component :is="themeIcon" :size="18" />
        <span>{{ isDark ? '浅色模式' : '深色模式' }}</span>
      </button>
      <div class="health-mini">
        <span class="status-dot" :class="store.health ? 'good' : 'muted'" />
        <span>{{ store.health ? '数据状态已读取' : '等待数据状态' }}</span>
      </div>
      <RouterLink class="legacy-link" to="/app/more/agents">
        <ChevronRight :size="15" />
        Agent 工作台
      </RouterLink>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 240px;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: transform 0.3s ease;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--color-border);
}

.brand-mark {
  width: 32px;
  height: 32px;
  background: var(--color-accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 14px;
}

.brand strong {
  display: block;
  font-size: 14px;
  color: var(--color-text-primary);
}

.brand small {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.workspace-line {
  padding: var(--spacing-3) var(--spacing-4);
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  border-bottom: 1px solid var(--color-border);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
}

.status-dot.muted {
  background: var(--color-text-tertiary);
}

.status-dot.good {
  background: var(--color-success);
}

.primary-nav,
.secondary-nav {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-2) var(--spacing-3);
}

.nav-section-title {
  padding: var(--spacing-3) var(--spacing-4);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s ease;
}

.nav-link:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.nav-link.router-link-active {
  background: var(--color-accent-bg);
  color: var(--color-accent);
  font-weight: 500;
}

.sidebar-footer {
  margin-top: auto;
  padding: var(--spacing-4);
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.theme-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s ease;
  width: 100%;
}

.theme-toggle:hover {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.health-mini {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.legacy-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: 12px;
  color: var(--color-text-tertiary);
  text-decoration: none;
  transition: color 0.2s ease;
}

.legacy-link:hover {
  color: var(--color-text-secondary);
}

.icon-button {
  background: none;
  border: none;
  padding: var(--spacing-1);
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.icon-button:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

@media (max-width: 767px) {
  .sidebar {
    transform: translateX(-100%);
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .mobile-only {
    display: flex;
    margin-left: auto;
  }
}

@media (min-width: 768px) {
  .mobile-only {
    display: none;
  }
}
</style>
