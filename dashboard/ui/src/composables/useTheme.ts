import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useAppStore } from '../stores/app'

export type Theme = 'light' | 'dark' | 'system'

export function useTheme() {
  const store = useAppStore()
  const theme = computed(() => store.theme as Theme)
  const isDark = computed(() => store.isDark)

  const syncSystemTheme = () => {
    if (theme.value === 'system') store.applyTheme()
  }

  const setTheme = (newTheme: Theme) => {
    store.setTheme(newTheme)
  }

  const toggleTheme = () => {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  onMounted(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', syncSystemTheme)
    onBeforeUnmount(() => mediaQuery.removeEventListener('change', syncSystemTheme))
  })

  return { theme, isDark, setTheme, toggleTheme }
}
