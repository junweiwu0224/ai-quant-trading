import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles.css'
import './styles/shell.css'

export function registerServiceWorker() {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return Promise.resolve(null)
  return navigator.serviceWorker.register('/sw.js?v=202', { scope: '/' }).catch(() => null)
}

createApp(App).use(createPinia()).use(router).mount('#app')
void registerServiceWorker()
