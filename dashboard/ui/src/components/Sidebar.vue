<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { X } from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { PRIMARY_WORKFLOWS, workspaceForPath } from '../navigation/workflows'

defineProps<{
  id?: string
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const store = useAppStore()
const route = useRoute()
const nav = PRIMARY_WORKFLOWS
const currentWorkspace = () => workspaceForPath(route.path)

function handleNavClick() {
  emit('close')
}

</script>

<template>
  <aside :id="id" class="sidebar" :class="{ open }">
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
        :class="{ 'workspace-active': currentWorkspace()?.id === item.workspace }"
        @click="handleNavClick"
      >
        <component :is="item.icon" :size="18" stroke-width="1.8" />
        <span>{{ item.navLabel || item.label }}</span>
      </RouterLink>
    </nav>


    <div class="sidebar-footer">
      <div class="health-mini">
        <span class="status-dot" :class="store.health ? 'good' : 'muted'" />
        <span>{{ store.health ? '数据状态已读取' : '等待数据状态' }}</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  z-index: 100;
  overflow-y: auto;
}

@media (max-width: 767px) {
  .sidebar {
    visibility: hidden;
    transform: translateX(-100%);
  }

  .sidebar.open {
    visibility: visible;
    transform: translateX(0);
  }

  .mobile-only {
    display: grid;
    margin-left: auto;
  }
}

@media (min-width: 768px) {
  .sidebar { visibility: visible; }
  .mobile-only { display: none; }
}
</style>
