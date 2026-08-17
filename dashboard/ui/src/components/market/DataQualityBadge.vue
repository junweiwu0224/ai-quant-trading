<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getDataHealth } from '../../api/market'
import type { DataHealth } from '../../api/types'

interface Props {
  market: string
  symbol: string
  autoRefresh?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  autoRefresh: true
})

interface DataQualityStatus {
  status: 'healthy' | 'delayed' | 'partial' | 'unavailable' | 'loading'
  provider: string
  lastUpdate: string
  coverage: number
  capabilities: string[]
}

const qualityData = ref<DataQualityStatus>({
  status: 'loading',
  provider: 'Unknown',
  lastUpdate: '-',
  coverage: 0,
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
        color: '#d97706' // Orange for partial
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

  return `数据源: ${provider}
最后更新: ${lastUpdate}
覆盖率: ${coverage.toFixed(1)}%
能力: ${capabilities.join('、') || '无'}`
})

async function fetchQualityData() {
  try {
    isLoading.value = true
    error.value = null

    const health = await getDataHealth(true)

    // Parse health data to determine quality status
    const stockDaily = health.stock_daily || {}
    const coverage = health.stock_count || 0
    const sourceHealth = health.source_health || {}

    // Calculate data freshness (simplified - would need actual timestamp parsing)
    const quoteAge = health.quote?.last_update_age_sec || 0
    const signalAge = health.signal?.cache_age_hours || 0

    // Determine status based on coverage and freshness
    let status: 'healthy' | 'delayed' | 'partial' | 'unavailable' = 'healthy'
    let coveragePct = 100

    if (coverage === 0) {
      status = 'unavailable'
      coveragePct = 0
    } else if (quoteAge > 21600 || signalAge > 6) { // 6 hours
      status = 'unavailable'
      coveragePct = coverage > 0 ? 50 : 0
    } else if (quoteAge > 3600 || signalAge > 1) { // 1 hour
      status = 'delayed'
      coveragePct = coverage > 0 ? 80 : 0
    } else if (coverage < 1000) {
      status = 'partial'
      coveragePct = 70
    }

    // Extract provider info
    const provider = health.signal?.provider || 'Unknown'

    // Format last update time
    const lastUpdate = new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })

    // Determine capabilities from health data
    const capabilities: string[] = []
    if (health.quote?.running) capabilities.push('实时')
    if (health.stock_count > 0) capabilities.push('日线')
    if (health.signal?.status === 'online') capabilities.push('信号')

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
      provider: 'Unknown',
      lastUpdate: '-',
      coverage: 0,
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
