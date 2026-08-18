<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { ChevronRight, Menu, Moon, Search, Sun, X } from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import type { MarketCode } from '../api/types'
import { COMMAND_WORKFLOWS } from '../navigation/workflows'

const emit = defineEmits<{
  toggleMenu: []
}>()

const props = defineProps<{
  menuOpen?: boolean
}>()

const store = useAppStore()
const route = useRoute()
const router = useRouter()

const paletteOpen = ref(false)
const paletteQuery = ref('')
const paletteIndex = ref(0)
const paletteInput = ref<HTMLInputElement | null>(null)
const paletteTrigger = ref<HTMLButtonElement | null>(null)
const menuTrigger = ref<HTMLButtonElement | null>(null)

const themeIcon = computed(() => store.isDark ? Sun : Moon)

const paletteItems = COMMAND_WORKFLOWS.map(({ label, description, to }) => ({ label, hint: description, to }))

const paletteResults = computed(() => {
  const queryText = paletteQuery.value.trim().toLowerCase()
  if (!queryText) return paletteItems
  return paletteItems.filter((item) => `${item.label} ${item.hint}`.toLowerCase().includes(queryText))
})

watch(paletteResults, () => {
  paletteIndex.value = 0
})

watch(() => props.menuOpen, (open, previous) => {
  if (previous && !open) void nextTick(() => menuTrigger.value?.focus())
})

function openPalette() {
  paletteOpen.value = true
  paletteQuery.value = ''
  paletteIndex.value = 0
  void nextTick(() => paletteInput.value?.focus())
}

function closePalette() {
  paletteOpen.value = false
  paletteQuery.value = ''
  paletteIndex.value = 0
  void nextTick(() => paletteTrigger.value?.focus())
}

function navigateFromPalette(to: string) {
  closePalette()
  void router.push(to)
}

function movePalette(delta: number) {
  if (!paletteResults.value.length) return
  const size = paletteResults.value.length
  paletteIndex.value = (paletteIndex.value + delta + size) % size
  void nextTick(() => document.getElementById(`palette-option-${paletteIndex.value}`)?.scrollIntoView({ block: 'nearest' }))
}

function handlePaletteKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    movePalette(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    movePalette(-1)
  } else if (event.key === 'Enter' && paletteResults.value[paletteIndex.value]) {
    event.preventDefault()
    navigateFromPalette(paletteResults.value[paletteIndex.value].to)
  }
}

function handleMarketChange(event: Event) {
  const nextMarket = String((event.target as HTMLSelectElement).value || 'CN').toUpperCase()
  store.setMarket(nextMarket as MarketCode)
  const currentMarket = String(route.params.market || '').toUpperCase()
  const currentSymbol = String(route.params.symbol || '').trim()
  if (currentMarket && currentSymbol && currentMarket !== nextMarket) {
    void router.replace({
      path: `/app/research/${nextMarket}/${encodeURIComponent(currentSymbol)}`,
      query: { ...route.query, market: nextMarket },
    })
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    openPalette()
  } else if (event.key === 'Escape' && paletteOpen.value) {
    closePalette()
  }
}

onMounted(() => window.addEventListener('keydown', handleGlobalKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleGlobalKeydown))
</script>

<template>
  <main class="main-shell">
    <header class="topbar">
      <button
        ref="menuTrigger"
        class="icon-button mobile-only"
        title="打开导航"
        aria-label="打开导航"
        aria-controls="mobile-navigation"
        :aria-expanded="props.menuOpen === true"
        @click="$emit('toggleMenu')"
      >
        <Menu :size="20" />
      </button>

      <div class="topbar-context">
        <span class="context-label">当前工作流</span>
        <strong>{{ String(route.meta.title || '决策中心') }}</strong>
      </div>

      <div class="topbar-actions">
        <label class="market-select">
          <span class="sr-only">市场</span>
          <select :value="store.market" @change="handleMarketChange">
            <option value="CN">A 股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
            <option value="JP">日股</option>
            <option value="KR">韩股</option>
            <option value="TW">台股</option>
          </select>
        </label>

        <button
          ref="paletteTrigger"
        class="icon-button palette-trigger"
          title="打开快捷导航（⌘K / Ctrl+K）"
          aria-label="打开快捷导航（⌘K / Ctrl+K）"
          @click="openPalette"
        >
          <Search :size="18" />
        </button>

        <button
          class="icon-button theme-button desktop-only"
          title="切换主题"
          aria-label="切换主题"
          @click="store.setTheme(store.isDark ? 'light' : 'dark')"
        >
          <component :is="themeIcon" :size="18" />
        </button>

        <RouterLink class="avatar" to="/app/settings" title="打开账户设置">
          研究
        </RouterLink>
      </div>
    </header>

    <div v-if="paletteOpen" class="palette-backdrop" @click.self="closePalette">
      <section class="command-palette panel" role="dialog" aria-modal="true" aria-labelledby="palette-title" @keydown="handlePaletteKeydown">
        <div class="command-palette-head">
          <div>
            <span class="context-label">快捷导航</span>
            <h2 id="palette-title">去哪里继续研究？</h2>
          </div>
          <button
            class="icon-button"
            type="button"
            title="关闭快捷导航"
            aria-label="关闭快捷导航"
            @click="closePalette"
          >
            <X :size="18" />
          </button>
        </div>

        <div class="palette-search">
          <label class="sr-only" for="palette-query">搜索工作流</label>
          <Search :size="17" aria-hidden="true" />
          <input
            id="palette-query"
            ref="paletteInput"
            v-model="paletteQuery"
            type="search"
            autocomplete="off"
            placeholder="搜索决策、研究、Agent、报告…"
            role="combobox"
            aria-controls="palette-options"
            :aria-activedescendant="paletteResults.length ? `palette-option-${paletteIndex}` : undefined"
            aria-autocomplete="list"
            @keydown="handlePaletteKeydown"
          />
          <kbd>Esc</kbd>
        </div>

        <div v-if="paletteResults.length" id="palette-options" class="palette-list" role="listbox" aria-label="工作流结果">
          <button
            v-for="(item, index) in paletteResults"
            :id="`palette-option-${index}`"
            :key="item.to"
            class="palette-item"
            :class="{ selected: index === paletteIndex }"
            type="button"
            role="option"
            :aria-selected="index === paletteIndex"
            @mouseenter="paletteIndex = index"
            @click="navigateFromPalette(item.to)"
          >
            <span class="palette-item-icon"><ChevronRight :size="16" /></span>
            <span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
            <ChevronRight :size="15" class="faint" />
          </button>
        </div>

        <div v-else class="empty palette-empty">
          没有匹配的工作流。试试"研究""报告"或"Agent"。
        </div>

        <div class="palette-footer">
          <span><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> 打开</span>
          <span>回车选择 · Escape 关闭</span>
        </div>
      </section>
    </div>

    <div class="content-wrap">
      <RouterView v-slot="{ Component, route: routedComponent }">
        <Transition name="workspace-route" mode="out-in">
          <component :is="Component" :key="routedComponent.fullPath" />
        </Transition>
      </RouterView>
    </div>
  </main>
</template>

<style scoped>
.main-shell {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-left: 240px;
  min-height: 100vh;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  height: 56px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-4);
  gap: var(--spacing-4);
}

.topbar-context {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
}

.context-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.topbar-context strong {
  font-size: 14px;
  color: var(--color-text-primary);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.icon-button {
  background: none;
  border: none;
  padding: var(--spacing-2);
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.icon-button:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.market-select select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.content-wrap {
  flex: 1;
  padding: var(--spacing-6);
  overflow-y: auto;
}

.palette-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 15vh;
}

.command-palette {
  width: 90%;
  max-width: 640px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.command-palette-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--color-border);
}

.command-palette-head h2 {
  font-size: 16px;
  margin: 0;
  color: var(--color-text-primary);
}

.palette-search {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--color-border);
}

.palette-search input {
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font-size: 14px;
  color: var(--color-text-primary);
}

.palette-search kbd {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.palette-list {
  max-height: 400px;
  overflow-y: auto;
}

.palette-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  width: 100%;
  padding: var(--spacing-3) var(--spacing-4);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;
}

.palette-item:hover, .palette-item:focus-visible, .palette-item.selected {
  background: var(--color-accent-pale);
  color: var(--color-accent-strong);
}

.palette-item strong {
  display: block;
  font-size: 14px;
  color: var(--color-text-primary);
}

.palette-item small {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.palette-item-icon {
  color: var(--color-accent);
}

.faint {
  color: var(--color-text-tertiary);
  margin-left: auto;
}

.palette-empty {
  padding: var(--spacing-6);
  text-align: center;
  color: var(--color-text-secondary);
}

.palette-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 767px) {
  .main-shell {
    margin-left: 0;
    padding-bottom: 64px;
  }

  .mobile-only {
    display: flex;
  }

  .desktop-only {
    display: none;
  }

  .content-wrap {
    padding: var(--spacing-4);
  }
}

@media (min-width: 768px) {
  .mobile-only {
    display: none;
  }

  .desktop-only {
    display: flex;
  }
}
</style>
