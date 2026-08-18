<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CheckCircle2, ChevronDown, CircleAlert, Clock3, Database, Globe2, RefreshCw, ShieldCheck, WifiOff } from 'lucide-vue-next'
import { getMarketCapabilities } from '../../api/market'
import type { MarketCapability } from '../../api/market'
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'

const markets = ref<MarketCapability[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)
const expandedMarkets = ref<Set<string>>(new Set())

const capabilityLabels: Record<string, string> = {
  '日线': '日线',
  '分时': '分时',
  '盘口': '盘口',
  '实时': '实时',
  '历史': '历史'
}

function toggleExpand(marketCode: string) {
  const next = new Set(expandedMarkets.value)
  if (next.has(marketCode)) {
    next.delete(marketCode)
  } else {
    next.add(marketCode)
  }
  expandedMarkets.value = next
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

function statusLabel(status: MarketCapability['status']): string {
  return status === 'active' ? '已配置来源' : status === 'limited' ? '手动研究' : '不可用'
}

function statusVariant(status: MarketCapability['status']): 'success' | 'warning' | 'default' {
  return status === 'active' ? 'success' : status === 'limited' ? 'warning' : 'default'
}

function marketStateLabel(market: MarketCapability): string {
  return market.data_state_label || (market.data_state === 'configured' ? '已声明来源，运行时待探测' : '市场级自动源未接入')
}

function providerLabel(provider: NonNullable<MarketCapability['provider_details']>[number]): string {
  if (provider.qualifies_for_daily_auto_push || provider.qualifies_for_intraday_auto_push) return '已通过资格校验'
  if (provider.status === 'target_not_integrated') return '目标 provider 未接入'
  return '已声明，未获自动资格'
}

function qualificationText(market: MarketCapability): string {
  if (market.qualification_reasons?.length) return market.qualification_reasons.join('；')
  if (market.manual_research) return '仅支持手动标的研究；自动推送需独立健康、日历和新鲜度校验'
  return '资格由运行时 provider 健康与新鲜度决定'
}

const configuredCount = computed(() => markets.value.filter((market) => market.data_state === 'configured' || market.status === 'active').length)

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
          <RefreshCw :size="16" :class="{ spin: isLoading }" />
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state" aria-live="polite">
        <div v-for="index in 4" :key="index" class="loading-row"><span /><span /><i /></div>
        <small>正在读取六市场能力与数据来源…</small>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-state">
        <CircleAlert :size="18" />
        <span>{{ error }}</span>
        <button class="button ghost compact-button" type="button" @click="fetchMarkets">重试</button>
      </div>

      <!-- Market List -->
      <div v-else class="markets-list">
        <div
          v-for="market in markets"
          :key="market.code"
          class="market-item"
          :class="{ 'market-item--expanded': isExpanded(market.code) }"
        >
          <button class="market-summary" type="button" :aria-expanded="isExpanded(market.code)" @click="toggleExpand(market.code)">
            <div class="market-info">
              <span class="market-icon"><Globe2 :size="18" /></span>
              <div class="market-name">
                <span class="name-zh">{{ market.name_zh }}</span>
                <span class="name-en">{{ market.name_en }}</span>
              </div>
            </div>

            <div class="market-status">
              <BaseTag
                :variant="statusVariant(market.status)"
                size="sm"
              >
                {{ statusLabel(market.status) }}
              </BaseTag>
              <ChevronDown class="expand-icon" :class="{ 'expand-icon--expanded': isExpanded(market.code) }" :size="16" />
            </div>
          </button>
          <div class="market-state-line"><span><Database :size="13" />{{ marketStateLabel(market) }}</span><span v-if="market.runtime_state_label" class="market-runtime"><Clock3 :size="13" />{{ market.runtime_state_label }}</span><span v-if="market.freshness_status" class="market-runtime"><Clock3 :size="13" />{{ market.freshness_status }}</span><span v-if="market.generated_at" class="market-runtime"><Clock3 :size="13" />{{ market.generated_at }}</span><span><Clock3 :size="13" />{{ market.timezone }}</span></div>

          <!-- Expanded Details -->
          <div v-if="isExpanded(market.code)" class="market-details">
            <div class="detail-row">
              <span class="detail-label">数据源</span>
              <span class="detail-value">{{ market.provider || '市场级自动源未接入' }}</span>
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

            <div v-if="market.provider_details?.length" class="detail-row detail-row--full">
              <span class="detail-label">Provider 边界</span>
              <div class="provider-list">
                <span v-for="provider in market.provider_details" :key="provider.name" class="provider-item">
                  <strong>{{ provider.name }}</strong><small>{{ providerLabel(provider) }}</small>
                </span>
              </div>
            </div>

            <div class="detail-row detail-row--full">
              <span class="detail-label">自动化资格</span>
              <div class="capability-status-list">
                <span :class="market.scheduled_daily_report ? 'good' : 'muted'"><CheckCircle2 :size="13" />{{ market.scheduled_daily_report ? '已通过日报资格' : '日报未获资格' }}</span>
                <span :class="market.intraday_auto_push ? 'good' : 'muted'"><ShieldCheck :size="13" />{{ market.intraday_auto_push ? '已通过盘中资格' : '盘中未获资格' }}</span>
              </div>
              <span class="detail-value detail-value--muted">{{ qualificationText(market) }}</span>
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
          {{ markets.length }} 个市场 · {{ configuredCount }} 个已配置 · {{ markets.length - configuredCount }} 个待接入
        </span>
        <span class="footer-note"><WifiOff :size="13" />待接入市场仍保留手动研究边界，不伪造行情</span>
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

.refresh-button:focus-visible,
.market-summary:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
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
  align-items: stretch;
  gap: var(--spacing-md);
  padding: var(--spacing-xl) 0;
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

.loading-state small {
  align-self: center;
}

.loading-row {
  display: grid;
  grid-template-columns: 30px 1fr 56px;
  gap: 10px;
  align-items: center;
}

.loading-row span,
.loading-row i {
  display: block;
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--color-surface-muted), var(--color-bg-tertiary), var(--color-surface-muted));
  background-size: 200% 100%;
  animation: shimmer 1.2s ease-in-out infinite;
}

.loading-row span:first-child {
  width: 24px;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: -200% 0; }
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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
  width: 100%;
  border: 0;
  font: inherit;
  text-align: left;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  cursor: pointer;
  user-select: none;
  background: transparent;
  color: inherit;
}

.market-summary:hover {
  background: var(--color-surface-muted);
}

.market-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.market-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  color: var(--color-accent-strong);
  border-radius: 7px;
  background: var(--color-accent-pale);
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

.market-state-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 0 var(--spacing-md) var(--spacing-sm);
  color: var(--color-ink-faint);
  font-size: 11px;
}

.market-state-line span,
.capability-status-list span,
.footer-note {
  display: inline-flex;
  align-items: center;
  gap: 5px;
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

.provider-list {
  display: grid;
  gap: 6px;
}

.provider-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--color-ink);
}

.provider-item small {
  color: var(--color-ink-soft);
}

.capability-status-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--color-ink-soft);
  font-size: 12px;
}

.capability-status-list .good {
  color: var(--color-success);
}

.capability-status-list .muted {
  color: var(--color-ink-faint);
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

.footer-note {
  margin-top: 6px;
  color: var(--color-ink-faint);
  font-size: 11px;
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
