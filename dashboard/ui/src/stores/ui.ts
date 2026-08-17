import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'
export type ThemeMode = 'light' | 'dark' | 'system'

export interface Notification {
  id: string
  type: NotificationType
  message: string
  title?: string
  duration?: number
  dismissible?: boolean
  timestamp: number
}

export interface ModalState {
  id: string
  component?: string
  props?: Record<string, unknown>
  visible: boolean
}

export interface ToastOptions {
  type?: NotificationType
  title?: string
  duration?: number
  dismissible?: boolean
}

// Safe localStorage helpers
function safeLocalStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

function safeGetItem(key: string, fallback: string): string {
  try {
    return safeLocalStorage()?.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

function safeSetItem(key: string, value: string): boolean {
  try {
    safeLocalStorage()?.setItem(key, value)
    return true
  } catch {
    return false
  }
}

function safeWindowAccess<T>(accessor: () => T, fallback: T): T {
  try {
    return typeof window !== 'undefined' ? accessor() : fallback
  } catch {
    return fallback
  }
}

export const useUIStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const mobileMenuOpen = ref(false)
  const theme = ref<ThemeMode>((safeGetItem('ui-theme', 'system') as ThemeMode) || 'system')
  const notifications = ref<Notification[]>([])
  const modals = ref<ModalState[]>([])
  const loading = ref(false)
  const loadingMessage = ref<string | null>(null)

  // Viewport tracking
  const viewportWidth = ref(safeWindowAccess(() => window.innerWidth, 1024))
  const viewportHeight = ref(safeWindowAccess(() => window.innerHeight, 768))

  const isMobile = computed(() => viewportWidth.value < 768)
  const isTablet = computed(() => viewportWidth.value >= 768 && viewportWidth.value < 1024)
  const isDesktop = computed(() => viewportWidth.value >= 1024)

  const activeNotifications = computed(() => {
    return notifications.value.filter(n => {
      if (!n.duration) return true
      const age = Date.now() - n.timestamp
      return age < n.duration
    })
  })

  const visibleModals = computed(() => {
    return modals.value.filter(m => m.visible)
  })

  const hasActiveModal = computed(() => visibleModals.value.length > 0)

  const isDarkMode = computed(() => {
    if (theme.value === 'dark') return true
    if (theme.value === 'light') return false
    return safeWindowAccess(() => window.matchMedia('(prefers-color-scheme: dark)').matches, false)
  })

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    safeSetItem('sidebar-collapsed', String(sidebarCollapsed.value))
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
    safeSetItem('sidebar-collapsed', String(collapsed))
  }

  function toggleMobileMenu() {
    mobileMenuOpen.value = !mobileMenuOpen.value
  }

  function setMobileMenuOpen(open: boolean) {
    mobileMenuOpen.value = open
  }

  function setTheme(newTheme: ThemeMode) {
    theme.value = newTheme
    safeSetItem('ui-theme', newTheme)
    applyTheme()
  }

  function applyTheme() {
    const dark = isDarkMode.value
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.dataset.theme = dark ? 'dark' : 'light'
      document.documentElement.classList.toggle('dark', dark)
    }
  }

  function addNotification(message: string, options?: ToastOptions): string {
    const id = Math.random().toString(36).substring(7)
    const notification: Notification = {
      id,
      type: options?.type || 'info',
      message,
      title: options?.title,
      duration: options?.duration ?? 5000,
      dismissible: options?.dismissible ?? true,
      timestamp: Date.now()
    }

    notifications.value.push(notification)

    // Auto-remove after duration
    if (notification.duration && notification.duration > 0) {
      setTimeout(() => {
        removeNotification(id)
      }, notification.duration)
    }

    return id
  }

  function removeNotification(id: string) {
    const index = notifications.value.findIndex(n => n.id === id)
    if (index !== -1) {
      notifications.value.splice(index, 1)
    }
  }

  function clearNotifications() {
    notifications.value = []
  }

  function showSuccess(message: string, title?: string, duration?: number) {
    return addNotification(message, { type: 'success', title, duration })
  }

  function showError(message: string, title?: string, duration?: number) {
    return addNotification(message, { type: 'error', title, duration: duration ?? 8000 })
  }

  function showWarning(message: string, title?: string, duration?: number) {
    return addNotification(message, { type: 'warning', title, duration })
  }

  function showInfo(message: string, title?: string, duration?: number) {
    return addNotification(message, { type: 'info', title, duration })
  }

  function openModal(id: string, component?: string, props?: Record<string, unknown>) {
    const existing = modals.value.find(m => m.id === id)
    if (existing) {
      existing.visible = true
      existing.component = component
      existing.props = props
    } else {
      modals.value.push({ id, component, props, visible: true })
    }
  }

  function closeModal(id: string) {
    const modal = modals.value.find(m => m.id === id)
    if (modal) {
      modal.visible = false
    }
  }

  function removeModal(id: string) {
    const index = modals.value.findIndex(m => m.id === id)
    if (index !== -1) {
      modals.value.splice(index, 1)
    }
  }

  function closeAllModals() {
    modals.value.forEach(m => m.visible = false)
  }

  function setLoading(isLoading: boolean, message?: string) {
    loading.value = isLoading
    loadingMessage.value = message ?? null
  }

  function updateViewport() {
    viewportWidth.value = safeWindowAccess(() => window.innerWidth, viewportWidth.value)
    viewportHeight.value = safeWindowAccess(() => window.innerHeight, viewportHeight.value)

    // Close mobile menu on resize to desktop
    if (viewportWidth.value >= 768 && mobileMenuOpen.value) {
      mobileMenuOpen.value = false
    }
  }

  // Store listener references for cleanup
  let themeMediaQuery: MediaQueryList | null = null
  let handleThemeChange: (() => void) | null = null

  // Initialize
  function initialize() {
    // Restore sidebar state
    const savedSidebarState = safeGetItem('sidebar-collapsed', '')
    if (savedSidebarState !== '') {
      sidebarCollapsed.value = savedSidebarState === 'true'
    }

    // Apply theme
    applyTheme()

    if (typeof window === 'undefined') return

    // Setup viewport listener (consolidates resize handling)
    window.addEventListener('resize', updateViewport)

    // Setup media query listener for system theme
    themeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    handleThemeChange = () => {
      if (theme.value === 'system') {
        applyTheme()
      }
    }
    themeMediaQuery.addEventListener('change', handleThemeChange)
  }

  // Cleanup function to remove all event listeners
  function cleanup() {
    if (typeof window === 'undefined') return

    window.removeEventListener('resize', updateViewport)

    if (themeMediaQuery && handleThemeChange) {
      themeMediaQuery.removeEventListener('change', handleThemeChange)
    }
  }

  // Auto-initialize
  initialize()

  return {
    sidebarCollapsed,
    mobileMenuOpen,
    theme,
    notifications,
    modals,
    loading,
    loadingMessage,
    viewportWidth,
    viewportHeight,
    isMobile,
    isTablet,
    isDesktop,
    activeNotifications,
    visibleModals,
    hasActiveModal,
    isDarkMode,
    toggleSidebar,
    setSidebarCollapsed,
    toggleMobileMenu,
    setMobileMenuOpen,
    setTheme,
    applyTheme,
    addNotification,
    removeNotification,
    clearNotifications,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    openModal,
    closeModal,
    removeModal,
    closeAllModals,
    setLoading,
    updateViewport,
    cleanup
  }
})
