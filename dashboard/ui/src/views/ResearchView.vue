<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import BaseTabs from '../components/base/BaseTabs.vue'
import type { Tab } from '../components/base/BaseTabs.vue'
import KLineChart from '../components/research/KLineChart.vue'
import TechnicalIndicators from '../components/research/TechnicalIndicators.vue'

const route = useRoute()

const symbol = computed(() => String(route.params.symbol || ''))
const market = computed(() => String(route.params.market || 'CN').toUpperCase())

const tabs: Tab[] = [
  { id: 'kline-tech', label: 'K线与技术' },
  { id: 'evidence', label: '证据与决策' },
  { id: 'backtest', label: '回测草案' },
]

const activeTab = ref('kline-tech')
</script>

<template>
  <section class="research-view">
    <div class="research-header">
      <h1 class="research-title">单股研究</h1>
      <div class="research-meta">
        <span class="meta-badge">{{ market }}</span>
        <span class="meta-symbol">{{ symbol }}</span>
      </div>
    </div>

    <BaseTabs v-model="activeTab" :tabs="tabs" size="md" class="research-tabs">
      <!-- K线与技术 Tab -->
      <div v-if="activeTab === 'kline-tech'" class="tab-content">
        <div class="research-layout">
          <KLineChart :market="market" :symbol="symbol" />
          <TechnicalIndicators :market="market" :symbol="symbol" />
        </div>
      </div>

      <!-- 证据与决策 Tab -->
      <div v-else-if="activeTab === 'evidence'" class="tab-content">
        <div class="empty-state">
          <p class="empty-state-title">开发中...</p>
          <p class="empty-state-text">证据与决策模块即将上线</p>
        </div>
      </div>

      <!-- 回测草案 Tab -->
      <div v-else-if="activeTab === 'backtest'" class="tab-content">
        <div class="empty-state">
          <p class="empty-state-title">开发中...</p>
          <p class="empty-state-text">回测草案模块即将上线</p>
        </div>
      </div>
    </BaseTabs>
  </section>
</template>

<style scoped>
.research-view {
  padding: var(--spacing-lg);
  max-width: 1400px;
  margin: 0 auto;
}

.research-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-lg);
  border-bottom: 2px solid var(--color-line);
}

.research-title {
  margin: 0;
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
}

.research-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.meta-badge {
  padding: var(--spacing-xs) var(--spacing-md);
  background-color: var(--color-accent-pale);
  color: var(--color-accent);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-md);
}

.meta-symbol {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
  font-family: var(--font-family-mono);
}

.research-tabs {
  width: 100%;
}

.tab-content {
  animation: fadeIn var(--duration-slow) var(--ease-smooth);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.research-layout {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  padding: var(--spacing-2xl);
  text-align: center;
}

.empty-state-title {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink-soft);
}

.empty-state-text {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-ink-faint);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .research-view {
    padding: var(--spacing-md);
  }

  .research-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
    margin-bottom: var(--spacing-lg);
  }

  .research-title {
    font-size: var(--font-size-2xl);
  }

  .research-meta {
    width: 100%;
    justify-content: flex-start;
  }

  .research-layout {
    gap: var(--spacing-md);
  }

  .empty-state {
    min-height: 300px;
    padding: var(--spacing-xl);
  }

  .empty-state-title {
    font-size: var(--font-size-xl);
  }
}

/* Small mobile */
@media (max-width: 480px) {
  .research-view {
    padding: var(--spacing-sm);
  }

  .research-title {
    font-size: var(--font-size-xl);
  }

  .meta-symbol {
    font-size: var(--font-size-lg);
  }
}
</style>
