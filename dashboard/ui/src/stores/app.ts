import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { AccountState, DataHealth, WatchlistItem } from '../types'
import { api } from '../api/client'

export const useAppStore = defineStore('app', () => {
  const theme = ref<'light' | 'dark' | 'system'>((localStorage.getItem('quant-theme') as 'light' | 'dark' | 'system') || 'light')
  const market = ref('CN')
  const selectedPortfolio = ref('watchlist')
  const watchlist = ref<WatchlistItem[]>([])
  const health = ref<DataHealth | null>(null)
  const loading = ref(false)
  const error = ref('')
  const authLoading = ref(true)
  const account = ref<AccountState | null>(null)
  const authenticated = computed(() => Boolean(account.value?.authenticated))
  const isDark = computed(() => theme.value === 'dark' || (theme.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches))

  function applyTheme() {
    document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
  }
  function setTheme(next: 'light' | 'dark' | 'system') {
    theme.value = next
    localStorage.setItem('quant-theme', next)
    applyTheme()
  }
  async function loadWorkspace() {
    if (!authenticated.value) return
    loading.value = true
    error.value = ''
    try {
      const [list, status] = await Promise.all([api.watchlist(), api.health()])
      watchlist.value = Array.isArray(list) ? list : []
      health.value = status
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '工作区数据加载失败'
    } finally {
      loading.value = false
    }
  }
  async function bootstrapAuth() {
    authLoading.value = true
    try {
      const current = await api.accountMe()
      account.value = current.authenticated ? current : null
    } catch (reason) {
      account.value = null
      error.value = reason instanceof Error ? reason.message : '认证状态读取失败'
    } finally {
      authLoading.value = false
    }
  }
  function setAccount(next: AccountState | null) {
    account.value = next?.authenticated ? next : null
    error.value = ''
  }
  function clearAccount() {
    account.value = null
    watchlist.value = []
    health.value = null
  }
  applyTheme()
  return { theme, market, selectedPortfolio, watchlist, health, loading, error, authLoading, account, authenticated, isDark, setTheme, bootstrapAuth, setAccount, clearAccount, loadWorkspace, applyTheme }
})
