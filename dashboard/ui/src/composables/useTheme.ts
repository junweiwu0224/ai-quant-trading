import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'quant-theme';

export function useTheme() {
  const theme = ref<Theme>('light');

  const isDark = computed(() => {
    return theme.value === 'dark' ||
      (theme.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  });

  const applyTheme = (newTheme: Theme) => {
    const dark = newTheme === 'dark' ||
      (newTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

    document.body.classList.toggle('theme-dark', dark);
    document.body.classList.toggle('theme-light', !dark);
  };

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme;
    localStorage.setItem(STORAGE_KEY, newTheme);
    applyTheme(newTheme);
  };

  const toggleTheme = () => {
    const next = theme.value === 'light' ? 'dark' : 'light';
    setTheme(next);
  };

  onMounted(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && ['light', 'dark', 'system'].includes(saved)) {
      theme.value = saved as Theme;
      applyTheme(saved as Theme);
    }

    // 监听系统主题变化
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      if (theme.value === 'system') {
        applyTheme('system');
      }
    };
    mediaQuery.addEventListener('change', handler);

    // 清理事件监听器
    onBeforeUnmount(() => {
      mediaQuery.removeEventListener('change', handler);
    });
  });

  return {
    theme,
    isDark,
    setTheme,
    toggleTheme
  };
}
