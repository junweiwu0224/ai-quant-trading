/**
 * Demo utility to generate sample token usage data for testing
 */
import { useTokenUsage } from '../composables/useTokenUsage'

export function generateSampleTokenData() {
  const tokenUsage = useTokenUsage()

  // Clear existing data first
  tokenUsage.reset()

  const models = [
    'gpt-4',
    'gpt-3.5-turbo',
    'claude-3-opus',
    'claude-3-sonnet',
    'claude-3-haiku'
  ]

  const now = Date.now()
  const dayMs = 86400000 // 24 hours in milliseconds

  // Generate data for last 7 days
  for (let day = 7; day >= 0; day--) {
    const recordsPerDay = Math.floor(Math.random() * 5) + 3 // 3-7 records per day

    for (let i = 0; i < recordsPerDay; i++) {
      const model = models[Math.floor(Math.random() * models.length)]
      const inputTokens = Math.floor(Math.random() * 2000) + 500 // 500-2500
      const outputTokens = Math.floor(Math.random() * 1000) + 200 // 200-1200

      // Add timestamp variation within the day
      const timestamp = now - (day * dayMs) + Math.floor(Math.random() * dayMs)

      // Temporarily store the generated record
      const record = {
        id: `${timestamp}-${Math.random().toString(36).substring(7)}`,
        timestamp,
        inputTokens,
        outputTokens,
        model,
        cost: 0 // Will be calculated by recordUsage
      }

      // Use recordUsage to properly calculate cost and store
      tokenUsage.recordUsage(inputTokens, outputTokens, model)

      // Update the timestamp of the last record (hack to backdate it)
      const lastIndex = tokenUsage.usageHistory.value.length - 1
      if (lastIndex >= 0) {
        tokenUsage.usageHistory.value[lastIndex].timestamp = timestamp
      }
    }
  }

  return {
    recordsGenerated: tokenUsage.usageHistory.value.length,
    totalTokens: tokenUsage.totalTokens.value,
    totalCost: tokenUsage.totalCost.value
  }
}

export function clearTokenData() {
  const tokenUsage = useTokenUsage()
  tokenUsage.reset()
}
