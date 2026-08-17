import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export interface Decision {
  id: string
  symbol: string
  market: string
  type: 'buy' | 'sell' | 'hold'
  confidence: number
  reasoning: string[]
  createdAt: string
  price?: number
  targetPrice?: number
  stopLoss?: number
  status?: 'pending' | 'executed' | 'cancelled'
  metadata?: Record<string, unknown>
}

export interface DecisionFilters {
  symbol?: string
  market?: string
  type?: 'buy' | 'sell' | 'hold'
  status?: string
}

export const useDecisionStore = defineStore('decision', () => {
  const decisions = ref<Decision[]>([])
  const currentDecision = ref<Decision | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const recentDecisions = computed(() => {
    return [...decisions.value]
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 10)
  })

  const decisionsBySymbol = computed(() => {
    return (symbol: string) => {
      return decisions.value.filter(d => d.symbol === symbol)
    }
  })

  const decisionsByMarket = computed(() => {
    return (market: string) => {
      return decisions.value.filter(d => d.market === market)
    }
  })

  const pendingDecisions = computed(() => {
    return decisions.value.filter(d => d.status === 'pending')
  })

  async function fetchDecisions(filters?: DecisionFilters) {
    loading.value = true
    error.value = null
    try {
      // TODO: Replace with actual API call in Task 11
      // const response = await api.getDecisions(filters)
      // decisions.value = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 500))

      // Mock data for development
      const mockDecisions: Decision[] = [
        {
          id: '1',
          symbol: '600519.SH',
          market: 'CN',
          type: 'buy',
          confidence: 0.85,
          reasoning: ['Strong fundamentals', 'Technical breakout', 'Positive momentum'],
          createdAt: new Date().toISOString(),
          price: 1850.50,
          targetPrice: 2000,
          status: 'pending'
        }
      ]

      let filtered = mockDecisions
      if (filters?.symbol) {
        filtered = filtered.filter(d => d.symbol === filters.symbol)
      }
      if (filters?.market) {
        filtered = filtered.filter(d => d.market === filters.market)
      }
      if (filters?.type) {
        filtered = filtered.filter(d => d.type === filters.type)
      }

      decisions.value = filtered
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载决策失败'
      decisions.value = []
    } finally {
      loading.value = false
    }
  }

  async function fetchDecisionById(id: string) {
    loading.value = true
    error.value = null
    try {
      // TODO: Replace with actual API call in Task 11
      // const response = await api.getDecision(id)
      // currentDecision.value = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 300))

      const found = decisions.value.find(d => d.id === id)
      if (found) {
        currentDecision.value = found
      } else {
        throw new Error('决策未找到')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载决策详情失败'
      currentDecision.value = null
    } finally {
      loading.value = false
    }
  }

  async function createDecision(data: Omit<Decision, 'id' | 'createdAt'>) {
    loading.value = true
    error.value = null
    try {
      // TODO: Replace with actual API call in Task 11
      // const response = await api.createDecision(data)
      // const newDecision = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 500))

      const newDecision: Decision = {
        ...data,
        id: Math.random().toString(36).substring(7),
        createdAt: new Date().toISOString()
      }

      decisions.value = [newDecision, ...decisions.value]
      currentDecision.value = newDecision

      return newDecision
    } catch (err) {
      error.value = err instanceof Error ? err.message : '创建决策失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateDecision(id: string, data: Partial<Decision>) {
    loading.value = true
    error.value = null
    try {
      // TODO: Replace with actual API call in Task 11
      // const response = await api.updateDecision(id, data)
      // const updatedDecision = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 400))

      const index = decisions.value.findIndex(d => d.id === id)
      if (index === -1) {
        throw new Error('决策未找到')
      }

      const updatedDecision = { ...decisions.value[index], ...data }
      decisions.value = [
        ...decisions.value.slice(0, index),
        updatedDecision,
        ...decisions.value.slice(index + 1)
      ]

      if (currentDecision.value?.id === id) {
        currentDecision.value = updatedDecision
      }

      return updatedDecision
    } catch (err) {
      error.value = err instanceof Error ? err.message : '更新决策失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteDecision(id: string) {
    loading.value = true
    error.value = null
    try {
      // TODO: Replace with actual API call in Task 11
      // await api.deleteDecision(id)

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 300))

      decisions.value = decisions.value.filter(d => d.id !== id)

      if (currentDecision.value?.id === id) {
        currentDecision.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除决策失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  function setCurrentDecision(decision: Decision | null) {
    currentDecision.value = decision
  }

  function clearError() {
    error.value = null
  }

  return {
    decisions,
    currentDecision,
    loading,
    error,
    recentDecisions,
    decisionsBySymbol,
    decisionsByMarket,
    pendingDecisions,
    fetchDecisions,
    fetchDecisionById,
    createDecision,
    updateDecision,
    deleteDecision,
    setCurrentDecision,
    clearError
  }
})
