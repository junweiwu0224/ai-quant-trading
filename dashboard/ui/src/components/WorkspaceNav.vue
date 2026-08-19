<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useResearchContextStore } from '../stores/researchContext'
import { workspaceForPath, type WorkspaceTab } from '../navigation/workflows'

const route = useRoute()
const researchContext = useResearchContextStore()
const workspace = computed(() => workspaceForPath(route.path))

function resolveTarget(tab: WorkspaceTab) {
  if (!tab.preserveResearchContext || !researchContext.hasInstrument) return tab.to
  const market = researchContext.context.market || String(route.query.market || 'CN')
  const symbol = researchContext.context.symbol || String(route.query.symbol || '')
  return symbol ? { path: `/app/research/${market}/${encodeURIComponent(symbol)}`, query: { source: 'workspace-nav' } } : tab.to
}

function isTabActive(tab: WorkspaceTab) {
  const path = route.path
  if (tab.id === 'research') return path === '/app/research' || /^\/app\/research\/(?:CN|HK|US|JP|KR|TW)\/[^/]+$/.test(path)
  if (tab.id === 'ai') return path === '/app/ai' || path.startsWith('/app/ai/')
  return path === tab.to || path.startsWith(`${tab.to}/`)
}
</script>

<template>
  <nav v-if="workspace" class="workspace-nav" :aria-label="`${workspace.label}工作区模块`">
    <div class="workspace-nav-inner">
      <div class="workspace-nav-heading">
        <component :is="workspace.icon" :size="16" aria-hidden="true" />
        <span>{{ workspace.label }}</span>
      </div>
      <RouterLink
        v-for="tab in workspace.tabs"
        :key="tab.id"
        :to="resolveTarget(tab)"
        class="workspace-nav-link"
        :class="{ 'workspace-nav-active': isTabActive(tab) }"
        :aria-current="isTabActive(tab) ? 'page' : undefined"
      >
        <component :is="tab.icon" :size="15" aria-hidden="true" />
        <span>{{ tab.label }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.workspace-nav {
  border-bottom: 1px solid var(--color-line);
  background: var(--color-surface);
}

.workspace-nav-inner {
  display: flex;
  align-items: stretch;
  gap: 2px;
  width: min(100%, 1480px);
  min-height: 48px;
  margin: 0 auto;
  padding: 0 clamp(14px, 2vw, 30px);
}

.workspace-nav-heading,
.workspace-nav-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 48px;
  padding: 0 12px;
  color: var(--color-ink-soft);
  font-size: 12px;
  text-decoration: none;
  white-space: nowrap;
}

.workspace-nav-heading {
  margin-right: 8px;
  padding-left: 0;
  color: var(--color-ink);
  font-weight: 700;
}

.workspace-nav-heading svg { color: var(--color-accent-strong); }
.workspace-nav-link { border-bottom: 2px solid transparent; }
.workspace-nav-link:hover { color: var(--color-ink); background: var(--color-surface-muted); }
.workspace-nav-link.workspace-nav-active { border-bottom-color: var(--color-accent); color: var(--color-accent-strong); font-weight: 650; }

@media (max-width: 767px) {
  .workspace-nav-inner {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0;
    padding: 0 10px;
  }

  .workspace-nav-heading {
    grid-column: 1 / -1;
    min-height: 32px;
    margin: 0;
    padding: 0 4px;
    font-size: 11px;
  }

  .workspace-nav-link {
    justify-content: center;
    min-width: 0;
    min-height: 42px;
    padding: 4px 3px;
    font-size: 11px;
    white-space: normal;
  }

  .workspace-nav-link span { overflow-wrap: anywhere; text-align: center; }
}
</style>
