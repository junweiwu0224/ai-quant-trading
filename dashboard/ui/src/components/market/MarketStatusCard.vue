<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getMarketCapabilities } from '../../api/market'
import type { MarketCapability } from '../../api/market'
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'

const markets = ref<MarketCapability[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)
const expandedMarkets = ref<Set<string>>(new Set())

const marketIcons: Record<string, string> = {
  CN: '🇨🇳',
  HK: '🇭🇰',
  US: '🇺🇸',
  JP: '🇯🇵',
  KR: '🇰🇷',
  TW: '🇨🇳'
}

const statusConfig = computed(() => ({
  active: {
    label: '运行中',
    variant: 'success' as const,
    color: 'var(--color-success)'
  },
  limited: {
    label: '受限',
    variant: 'warning' as const,
    color: 'var(--color-warn)'
  },
  unavailable: {
    label: '未接入',
    variant: 'default' as const,
    color: 'var(--color-ink-faint)'
  }
}))

const capabilityLabels: Record<string, string> = {
  '日线': '日线',
  '分时': '分时',
  '盘口': '盘口',
  '实时': '实时',
  '历史': '历史'
}

function toggleExpand(marketCode: string) {
  if (expandedMarkets.value.has(marketCode)) {
    expandedMarkets.value.delete(marketCode)
  } else {
    expandedMarkets.value.add(marketCode)
  }
}

function isExpanded(marketCode: string): boolean {
  return expandedMarkets.value.has(marketCode)
}

function formatTradingHours(hours: MarketCapability['trading_hours']): string {
  if (!hours) return '-'

  const { open, close, lunch_start, lunch_end } = hours

  if (lunch_start && lunch_end) {
    return `${open}-${lunch_start}, ${lunch_end}-${close}`
  }

  return `${open}-${close}`
}

async function fetchMarkets() {
  try {
    isLoading.value = true
    error.value = null

    const response = await getMarketCapabilities()

    if (response.success) {
      markets.value = response.markets
    } else {
      throw new Error('Failed to fetch markets')
    }
  } catch (err) {
    console.error('Failed to fetch markets:', err)
    error.value = err instanceof Error ? err.message : '获取市场状态失败'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchMarkets()
})
</script>

<template>
  <BaseCard padding="md" bordered>
    <div class="market-status-card">
      <div class="card-header">
        <h3 class="card-title">全球市场状态</h3>
        <button
          v-if="!isLoading && !error"
          class="refresh-button"
          type="button"
          title="刷新"
          @click="fetchMarkets"
        >
          <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state">
        <div class="spinner"></div>
        <span>加载市场数据...</span>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-state">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <span>{{ error }}</span>
      </div>

      <!-- Market List -->
      <div v-else class="markets-list">
        <div
          v-for="market in markets"
          :key="market.code"
          class="market-item"
          :class="{ 'market-item--expanded': isExpanded(market.code) }"
        >
          <div class="market-summary" @click="toggleExpand(market.code)">
            <div class="market-info">
              <span class="market-icon">{{ marketIcons[market.code] || '🌐' }}</span>
              <div class="market-name">
                <span class="name-zh">{{ market.name_zh }}</span>
                <span class="name-en">{{ market.name_en }}</span>
              </div>
            </div>

            <div class="market-status">
              <BaseTag
                :variant="statusConfig[market.status].variant"
                size="sm"
              >
                {{ statusConfig[market.status].label }}
              </BaseTag>
              <svg
                class="expand-icon"
                :class="{ 'expand-icon--expanded': isExpanded(market.code) }"
                width="16"
                height="16"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
            </div>
          </div>

          <!-- Expanded Details -->
          <div v-if="isExpanded(market.code)" class="market-details">
            <div class="detail-row">
              <span class="detail-label">数据源</span>
              <span class="detail-value">{{ market.provider || '未接入' }}</span>
            </div>

            <div class="detail-row">
              <span class="detail-label">交易时间</span>
              <span class="detail-value">{{ formatTradingHours(market.trading_hours) }}</span>
            </div>

            <div class="detail-row">
              <span class="detail-label">时区</span>
              <span class="detail-value">{{ market.timezone }}</span>
            </div>

            <div class="detail-row">
              <span class="detail-label">货币</span>
              <span class="detail-value">{{ market.currency }}</span>
            </div>

            <div v-if="market.capabilities.length > 0" class="detail-row detail-row--full">
              <span class="detail-label">数据能力</span>
              <div class="capabilities-tags">
                <BaseTag
                  v-for="capability in market.capabilities"
                  :key="capability"
                  variant="info"
                  size="sm"
                >
                  {{ capabilityLabels[capability] || capability }}
                </BaseTag>
              </div>
            </div>

            <div v-if="market.reason" class="detail-row detail-row--full">
              <span class="detail-label">说明</span>
              <span class="detail-value detail-value--muted">{{ market.reason }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Summary Footer -->
      <div v-if="!isLoading && !error && markets.length > 0" class="card-footer">
        <span class="footer-text">
          共 {{ markets.length }} 个市场，{{ markets.filter(m => m.status === 'active').length }} 个运行中
        </span>
      </div>
    </div>
  </BaseCard>
</template>

<style scoped>
.market-status-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
}

.card-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.refresh-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  color: var(--color-ink-soft);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.refresh-button:hover {
  background-color: var(--color-surface-muted);
  color: var(--color-ink);
  border-color: var(--color-accent);
}

.refresh-button:active {
  transform: scale(0.95);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl) 0;
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-surface-muted);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Error State */
.error-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

/* Markets List */
.markets-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.market-item {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.market-item:hover {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-sm);
}

.market-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  cursor: pointer;
  user-select: none;
}

.market-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.market-icon {
  font-size: var(--font-size-xl);
  line-height: 1;
}

.market-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.name-zh {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.name-en {
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
  font-family: var(--font-family-mono);
}

.market-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.expand-icon {
  color: var(--color-ink-soft);
  transition: transform var(--duration-fast) var(--ease-smooth);
}

.expand-icon--expanded {
  transform: rotate(180deg);
}

/* Market Details */
.market-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  padding-top: 0;
  background-color: var(--color-surface-muted);
  border-top: 1px solid var(--color-line);
  animation: slideDown var(--duration-normal) var(--ease-smooth);
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.detail-row {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.detail-row--full {
  grid-template-columns: 1fr;
}

.detail-label {
  color: var(--color-ink-soft);
  font-weight: var(--font-weight-medium);
}

.detail-value {
  color: var(--color-ink);
}

.detail-value--muted {
  color: var(--color-ink-soft);
  font-style: italic;
}

.capabilities-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

/* Card Footer */
.card-footer {
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-line);
}

.footer-text {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

/* Responsive */
@media (max-width: 768px) {
  .market-summary {
    padding: var(--spacing-sm);
  }

  .market-details {
    padding: var(--spacing-sm);
    padding-top: 0;
  }

  .detail-row {
    grid-template-columns: 1fr;
    gap: var(--spacing-xs);
  }

  .market-name {
    gap: 0;
  }

  .name-zh {
    font-size: var(--font-size-sm);
  }

  .name-en {
    font-size: 10px;
  }
}
</style>
