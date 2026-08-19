<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getDataHealth } from '../../api/market'

interface Props {
  market: string
  symbol: string
  autoRefresh?: boolean
  researchState?: 'loading' | 'available' | 'partial' | 'unavailable'
  researchSource?: string
  researchAsOf?: string
  researchError?: string
  researchCoverage?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoRefresh: true
})

interface DataQualityStatus {
  status: 'healthy' | 'delayed' | 'partial' | 'manual' | 'unavailable' | 'loading'
  provider: string
  lastUpdate: string
  coverage: number | null
  capabilities: string[]
}

const qualityData = ref<DataQualityStatus>({
  status: 'loading',
  provider: 'Unknown',
  lastUpdate: '-',
  coverage: null,
  capabilities: []
})

const isLoading = ref(true)
const error = ref<string | null>(null)
let refreshInterval: number | null = null

const badgeConfig = computed(() => {
  switch (qualityData.value.status) {
    case 'healthy':
      return {
        label: '数据完整',
        variant: 'success' as const,
        color: 'var(--color-success)'
      }
    case 'delayed':
      return {
        label: '数据延迟',
        variant: 'warning' as const,
        color: 'var(--color-warn)'
      }
    case 'partial':
      return {
        label: '部分缺失',
        variant: 'warning' as const,
        color: 'var(--color-warn)'
      }
    case 'manual':
      return {
        label: '手动研究',
        variant: 'warning' as const,
        color: 'var(--color-warn)'
      }
    case 'unavailable':
      return {
        label: '数据不可用',
        variant: 'danger' as const,
        color: 'var(--color-danger)'
      }
    case 'loading':
    default:
      return {
        label: '加载中...',
        variant: 'default' as const,
        color: 'var(--color-ink-soft)'
      }
  }
})

const tooltipContent = computed(() => {
  if (error.value) {
    return `错误: ${error.value}`
  }

  const { provider, lastUpdate, coverage, capabilities } = qualityData.value

  const boundary = qualityData.value.status === 'manual' ? '\n边界: 仅供手动研究，不具备自动推送资格' : ''
  const coverageLabel = typeof coverage === 'number' && Number.isFinite(coverage)
    ? coverage.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1, useGrouping: false }) + '%'
    : '未知'
  return `数据源: ${provider}
最后更新: ${lastUpdate}
覆盖率: ${coverageLabel}
能力: ${capabilities.join('、') || '无'}${boundary}`
})

async function fetchQualityData() {
  try {
    isLoading.value = true
    error.value = null

    const health = await getDataHealth(true)

    const marketHealth = health.markets?.[props.market]
    const marketStatus = String(marketHealth?.research_status || marketHealth?.status || '').toLowerCase()
    const dataState = String(marketHealth?.data_state || '').toLowerCase()
    const manualResearch = props.market !== 'CN' && (
      marketHealth?.manual_research === true
      || props.researchSource === 'yahoo_finance_chart'
      || props.researchSource === 'external_kline_fallback'
    )
    const status = props.researchState === 'unavailable'
      ? 'unavailable'
      : props.researchState === 'loading'
        ? 'loading'
        : manualResearch
          ? 'manual'
          : props.researchState === 'available'
      ? 'healthy'
      : props.researchState === 'partial'
        ? 'partial'
        : ['healthy', 'online', 'active', 'configured'].includes(marketStatus)
          ? 'healthy'
          : ['degraded', 'limited', 'manual_research'].includes(marketStatus)
            ? 'partial'
            : ['unavailable', 'offline', 'not_integrated'].includes(dataState || marketStatus)
              ? 'unavailable'
              : 'loading'
    if (props.researchError) error.value = props.researchError
    // A stock-level research response and the workspace-wide health feed have
    // different coverage universes. Never fall back from a research response
    // to the workspace percentage: a healthy bar series can coexist with an
    // empty local A-share coverage pool, and showing 0% here would be false.
    const coveragePct = props.researchCoverage
      ?? (!props.researchSource
        ? (typeof marketHealth?.coverage_pct === 'number' ? marketHealth.coverage_pct : null)
        : null)
      ?? (!props.researchSource && typeof marketHealth?.coverage === 'number' ? marketHealth.coverage * 100 : null)
    const provider = props.researchSource || String(marketHealth?.provider || health.providers?.market || '未声明')
    const asOf = props.researchAsOf || marketHealth?.last_update || health.signal?.latest_date
    const lastUpdate = asOf ? String(asOf) : '未知'
    const capabilities: string[] = []
    const declared = marketHealth?.capabilities || marketHealth?.declared_capabilities || []
    capabilities.push(...declared.filter((item) => !capabilities.includes(item)))
    if (health.quote?.running) capabilities.push('实时服务')
    if (health.signal?.status === 'online') capabilities.push('信号服务')

    qualityData.value = {
      status,
      provider,
      lastUpdate,
      coverage: coveragePct,
      capabilities
    }
  } catch (err) {
    console.error('Failed to fetch data quality:', err)
    error.value = err instanceof Error ? err.message : '获取数据质量失败'
    qualityData.value = {
      status: 'unavailable',
      provider: '未声明',
      lastUpdate: '未知',
      coverage: null,
      capabilities: []
    }
  } finally {
    isLoading.value = false
  }
}

function startAutoRefresh() {
  if (props.autoRefresh && !refreshInterval) {
    // Refresh every 5 minutes
    refreshInterval = window.setInterval(() => {
      fetchQualityData()
    }, 5 * 60 * 1000)
  }
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

onMounted(() => {
  fetchQualityData()
  startAutoRefresh()
})

watch(
  () => [props.market, props.symbol, props.researchState, props.researchSource, props.researchAsOf, props.researchError, props.researchCoverage],
  () => { void fetchQualityData() },
)

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="data-quality-badge">
    <span
      class="badge"
      :class="`badge--${badgeConfig.variant}`"
      :title="tooltipContent"
    >
      <span class="badge__dot" :style="{ backgroundColor: badgeConfig.color }" />
      <span class="badge__label">{{ badgeConfig.label }}</span>
    </span>
  </div>
</template>

<style scoped>
.data-quality-badge {
  display: inline-flex;
  align-items: center;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  height: 24px;
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-full);
  cursor: help;
  transition: all var(--duration-fast) var(--ease-smooth);
  white-space: nowrap;
}

.badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.badge__label {
  line-height: 1;
}

/* Variants */
.badge--success {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.badge--warning {
  background-color: var(--color-warn-bg);
  color: var(--color-warn);
}

.badge--danger {
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
}

.badge--default {
  background-color: var(--color-surface-muted);
  color: var(--color-ink-soft);
}

.badge:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
</style>
