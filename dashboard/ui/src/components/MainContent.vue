<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { Boxes, ChevronRight, LockKeyhole, Menu, Moon, MoreHorizontal, Search, Settings, Sparkles, Sun, UserRound, X } from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { useResearchContextStore } from '../stores/researchContext'
import type { MarketCode } from '../api/types'
import { COMMAND_WORKFLOWS } from '../navigation/workflows'
import WorkspaceNav from './WorkspaceNav.vue'

defineEmits<{
  toggleMenu: []
}>()

const props = defineProps<{
  menuOpen?: boolean
}>()

const store = useAppStore()
const researchContext = useResearchContextStore()
const route = useRoute()
const router = useRouter()

const paletteOpen = ref(false)
const paletteQuery = ref('')
const paletteIndex = ref(0)
const paletteInput = ref<HTMLInputElement | null>(null)
const palettePanel = ref<HTMLElement | null>(null)
const paletteTrigger = ref<HTMLButtonElement | null>(null)
const menuTrigger = ref<HTMLButtonElement | null>(null)
const moreOpen = ref(false)

const themeIcon = computed(() => store.isDark ? Sun : Moon)
const workspaceName = computed(() => store.account?.workspace?.name || store.account?.workspace?.slug || '当前工作区')
const contextInstrument = computed(() => researchContext.hasInstrument ? `${researchContext.context.market} / ${researchContext.context.symbol}` : '未选择标的')
const freshnessLabel = computed(() => ({
  live: '数据新鲜', delayed: '数据延迟', stale: '数据过期', unavailable: '数据不可用',
} as Record<string, string>)[String(researchContext.context.freshness || '')] || '数据未知')
const freshnessClass = computed(() => ({ live: 'good', delayed: 'warn', stale: 'bad', unavailable: 'muted' } as Record<string, string>)[String(researchContext.context.freshness || '')] || 'muted')
const qualificationLabel = computed(() => researchContext.context.eligibility?.eligible === true ? '资格通过' : researchContext.context.eligibility ? '资格阻断' : '资格未检查')
const qualificationClass = computed(() => researchContext.context.eligibility?.eligible === true ? 'good' : researchContext.context.eligibility ? 'bad' : 'muted')

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
  moreOpen.value = false
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
  if (event.key === 'Tab') {
    const focusable = Array.from(palettePanel.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), a[href], select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) || []).filter((element) => element.offsetParent !== null)
    const first = focusable[0]
    const last = focusable.at(-1)
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  } else if (event.key === 'ArrowDown') {
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
  } else if (researchContext.hasInstrument && researchContext.context.market !== nextMarket) {
    researchContext.clear()
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    openPalette()
  } else if (event.key === 'Escape' && paletteOpen.value) {
    closePalette()
  } else if (event.key === 'Escape' && moreOpen.value) {
    moreOpen.value = false
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

        <RouterLink
          class="icon-button ai-global-link"
          to="/app/ai"
          title="打开 AI 研究工作台"
          aria-label="打开 AI 研究工作台"
        >
          <Sparkles :size="18" />
        </RouterLink>

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

        <div class="more-menu desktop-only">
          <button class="icon-button" type="button" aria-label="打开系统菜单" :aria-expanded="moreOpen" @click="moreOpen = !moreOpen">
            <MoreHorizontal :size="18" />
          </button>
          <div v-if="moreOpen" class="more-menu-popover" role="menu">
            <RouterLink to="/app/workflows" role="menuitem" @click="moreOpen = false"><Boxes :size="16" />工作流地图</RouterLink>
            <RouterLink to="/app/broker" role="menuitem" @click="moreOpen = false"><LockKeyhole :size="16" />Broker 安全</RouterLink>
            <RouterLink to="/app/settings" role="menuitem" @click="moreOpen = false"><Settings :size="16" />设置与账户</RouterLink>
          </div>
        </div>

        <RouterLink class="avatar" to="/app/settings" title="打开账户设置" aria-label="打开账户设置">
          <UserRound :size="17" />
        </RouterLink>
      </div>
    </header>

    <div class="workspace-bar" aria-label="当前研究上下文">
      <span class="workspace-bar-item workspace-bar-secondary"><span>工作区</span><strong>{{ workspaceName }}</strong></span>
      <span class="workspace-bar-item"><span>标的</span><strong>{{ contextInstrument }}</strong></span>
      <span class="workspace-bar-item workspace-bar-secondary"><span>数据</span><strong class="workspace-status" :class="freshnessClass">{{ freshnessLabel }}</strong></span>
      <span class="workspace-bar-item"><span>资格</span><strong class="workspace-status" :class="qualificationClass">{{ qualificationLabel }}</strong></span>
    </div>

    <WorkspaceNav />

    <div v-if="paletteOpen" class="palette-backdrop" @click.self="closePalette">
      <section ref="palettePanel" class="command-palette panel" role="dialog" aria-modal="true" aria-labelledby="palette-title" @keydown="handlePaletteKeydown">
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
          <component :is="Component" :key="routedComponent.name || routedComponent.path" />
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
}

.topbar-context { flex: 1; }
.content-wrap { flex: 1; overflow-y: auto; }

.workspace-bar { display:flex; align-items:center; min-height:40px; padding:6px var(--spacing-4); overflow-x:auto; border-bottom:1px solid var(--color-border); background:var(--color-bg-secondary); }
.workspace-bar-item { display:flex; align-items:baseline; gap:6px; min-width:0; padding:0 14px; border-right:1px solid var(--color-border); white-space:nowrap; }
.workspace-bar-item:first-child { padding-left:0; }
.workspace-bar-item:last-child { border-right:0; }
.workspace-bar-item > span { color:var(--color-text-tertiary); font-size:10px; }
.workspace-bar-item > strong { max-width:220px; overflow:hidden; color:var(--color-text-secondary); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.workspace-status.good { color:var(--color-success); }
.workspace-status.warn { color:var(--color-warn); }
.workspace-status.bad { color:var(--color-danger); }
.workspace-status.muted { color:var(--color-text-tertiary); }

@media (max-width: 767px) {
  .mobile-only { display: grid; }
  .desktop-only { display: none; }
  .workspace-bar { min-height:38px; padding:5px 12px; }
  .workspace-bar-item { flex:1 1 0; justify-content:center; padding:0 8px; }
  .workspace-bar-secondary { display:none; }
  .workspace-bar-item > strong { max-width:130px; }
}

@media (min-width: 768px) {
  .mobile-only { display: none; }
  .desktop-only { display: flex; }
}
</style>
