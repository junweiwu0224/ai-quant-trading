<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAppStore } from './stores/app'
import AuthView from './views/AuthView.vue'
import AppShell from './components/AppShell.vue'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const standalone = computed(() => route.path.startsWith('/report/'))
const authRoute = computed(() => route.path === '/auth')

const supportedMarkets = new Set(['CN', 'HK', 'US', 'JP', 'KR', 'TW'])
function normalMarket(value: unknown) {
  const market = String(value || '').toUpperCase()
  return supportedMarkets.has(market) ? market : 'CN'
}

function handleAuthExpired() {
  store.clearAccount()
  if (!standalone.value && !authRoute.value) {
    void router.replace({ path: '/auth', query: { next: route.fullPath } })
  }
}

onMounted(() => {
  if (route.params.market) store.market = normalMarket(route.params.market)
  window.addEventListener('quant-auth-expired', handleAuthExpired)
  void store.bootstrapAuth().then(() => {
    if (standalone.value) return
    if (!store.authenticated && !authRoute.value) {
      void router.replace({ path: '/auth', query: { next: route.fullPath } })
      return
    }
    if (store.authenticated) void store.loadWorkspace()
  })
})

onUnmounted(() => {
  window.removeEventListener('quant-auth-expired', handleAuthExpired)
})

watch(() => route.params.market, (market) => {
  if (market) store.market = normalMarket(market)
})

watch(() => store.market, (market) => {
  if (!route.path.startsWith('/app/research/') || !route.params.symbol) return
  const nextMarket = normalMarket(market)
  if (String(route.params.market || '').toUpperCase() !== nextMarket) {
    void router.replace({ path: `/app/research/${nextMarket}/${encodeURIComponent(String(route.params.symbol))}`, query: route.query })
  }
})
</script>

<template>
  <RouterView v-if=”standalone || authRoute” />
  <AuthView v-else-if=”!store.authLoading && !store.authenticated” />
  <main v-else-if=”store.authLoading” class=”auth-loading”>
    <div class=”loading-orb” aria-hidden=”true” />
    <strong>正在准备工作区…</strong>
    <span>读取会话与工作区状态</span>
  </main>
  <AppShell v-else />
</template>
