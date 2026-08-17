import { ref, computed } from 'vue'

export interface TokenUsageRecord {
  id: string
  timestamp: number
  inputTokens: number
  outputTokens: number
  model: string
  cost: number
}

export interface ModelPricing {
  inputPer1k: number
  outputPer1k: number
}

// Default pricing model (can be customized)
const MODEL_PRICING: Record<string, ModelPricing> = {
  'gpt-4': { inputPer1k: 0.03, outputPer1k: 0.06 },
  'gpt-4-turbo': { inputPer1k: 0.01, outputPer1k: 0.03 },
  'gpt-3.5-turbo': { inputPer1k: 0.0005, outputPer1k: 0.0015 },
  'claude-3-opus': { inputPer1k: 0.015, outputPer1k: 0.075 },
  'claude-3-sonnet': { inputPer1k: 0.003, outputPer1k: 0.015 },
  'claude-3-haiku': { inputPer1k: 0.00025, outputPer1k: 0.00125 },
  'default': { inputPer1k: 0.001, outputPer1k: 0.002 }
}

const STORAGE_KEY = 'quant-token-usage'

/**
 * Token usage tracking composable
 * Tracks AI token consumption and cost estimation
 */
export function useTokenUsage() {
  const usageHistory = ref<TokenUsageRecord[]>([])

  // Load from localStorage on init
  const loadFromStorage = () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const data = JSON.parse(stored)
        if (Array.isArray(data)) {
          usageHistory.value = data
        }
      }
    } catch (err) {
      console.warn('Failed to load token usage from localStorage:', err)
    }
  }

  // Save to localStorage
  const saveToStorage = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(usageHistory.value))
    } catch (err) {
      console.warn('Failed to save token usage to localStorage:', err)
    }
  }

  // Calculate cost for a record
  const calculateCost = (inputTokens: number, outputTokens: number, model: string): number => {
    const pricing = MODEL_PRICING[model] || MODEL_PRICING['default']
    const inputCost = (inputTokens / 1000) * pricing.inputPer1k
    const outputCost = (outputTokens / 1000) * pricing.outputPer1k
    return inputCost + outputCost
  }

  // Total input tokens
  const totalInputTokens = computed(() => {
    return usageHistory.value.reduce((sum, record) => sum + record.inputTokens, 0)
  })

  // Total output tokens
  const totalOutputTokens = computed(() => {
    return usageHistory.value.reduce((sum, record) => sum + record.outputTokens, 0)
  })

  // Total tokens (input + output)
  const totalTokens = computed(() => {
    return totalInputTokens.value + totalOutputTokens.value
  })

  // Total estimated cost
  const totalCost = computed(() => {
    return usageHistory.value.reduce((sum, record) => sum + record.cost, 0)
  })

  // Usage by model
  const usageByModel = computed(() => {
    const byModel: Record<string, {
      inputTokens: number
      outputTokens: number
      totalTokens: number
      cost: number
      count: number
    }> = {}

    for (const record of usageHistory.value) {
      if (!byModel[record.model]) {
        byModel[record.model] = {
          inputTokens: 0,
          outputTokens: 0,
          totalTokens: 0,
          cost: 0,
          count: 0
        }
      }

      byModel[record.model].inputTokens += record.inputTokens
      byModel[record.model].outputTokens += record.outputTokens
      byModel[record.model].totalTokens += record.inputTokens + record.outputTokens
      byModel[record.model].cost += record.cost
      byModel[record.model].count += 1
    }

    return byModel
  })

  /**
   * Record token usage
   * @param inputTokens - Number of input tokens
   * @param outputTokens - Number of output tokens
   * @param model - Model name/identifier
   */
  function recordUsage(inputTokens: number, outputTokens: number, model: string = 'default'): void {
    const cost = calculateCost(inputTokens, outputTokens, model)
    const record: TokenUsageRecord = {
      id: `${Date.now()}-${Math.random().toString(36).substring(7)}`,
      timestamp: Date.now(),
      inputTokens,
      outputTokens,
      model,
      cost
    }

    usageHistory.value.push(record)
    saveToStorage()
  }

  /**
   * Reset all usage history
   */
  function reset(): void {
    usageHistory.value = []
    saveToStorage()
  }

  /**
   * Export usage data as JSON
   * @returns JSON string of usage history
   */
  function exportData(): string {
    const exportData = {
      exported_at: new Date().toISOString(),
      total_input_tokens: totalInputTokens.value,
      total_output_tokens: totalOutputTokens.value,
      total_tokens: totalTokens.value,
      total_cost: totalCost.value,
      by_model: usageByModel.value,
      history: usageHistory.value
    }

    return JSON.stringify(exportData, null, 2)
  }

  /**
   * Get usage for a specific time range
   * @param startTime - Start timestamp
   * @param endTime - End timestamp
   */
  function getUsageInRange(startTime: number, endTime: number): TokenUsageRecord[] {
    return usageHistory.value.filter(
      record => record.timestamp >= startTime && record.timestamp <= endTime
    )
  }

  /**
   * Get usage for today
   */
  function getTodayUsage(): TokenUsageRecord[] {
    const startOfDay = new Date()
    startOfDay.setHours(0, 0, 0, 0)
    return getUsageInRange(startOfDay.getTime(), Date.now())
  }

  /**
   * Update pricing model
   * @param model - Model name
   * @param pricing - Pricing configuration
   */
  function updatePricing(model: string, pricing: ModelPricing): void {
    MODEL_PRICING[model] = pricing
  }

  // Initialize
  loadFromStorage()

  return {
    usageHistory,
    totalInputTokens,
    totalOutputTokens,
    totalTokens,
    totalCost,
    usageByModel,
    recordUsage,
    reset,
    exportData,
    getUsageInRange,
    getTodayUsage,
    updatePricing
  }
}
