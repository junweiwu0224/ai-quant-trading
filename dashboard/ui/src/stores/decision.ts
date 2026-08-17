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
  portfolio_id?: string
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
      const { getReports } = await import('../api/decisions')

      // Fetch reports (which contain decisions)
      const response = await getReports(filters?.portfolio_id, 50)

      // Transform reports to decision format
      // Note: The backend uses reports, not standalone decisions
      // This is a placeholder transformation - adjust based on actual report structure
      const transformedDecisions: Decision[] = response.items.map((report) => {
        const body = report.body || {}
        return {
          id: report.id,
          symbol: String(body.symbol || ''),
          market: String(body.market || 'CN'),
          type: String(body.decision_type || 'hold') as 'buy' | 'sell' | 'hold',
          confidence: Number(body.confidence || 0),
          reasoning: Array.isArray(body.reasoning) ? body.reasoning : [],
          createdAt: report.created_at,
          status: 'executed' as const,
          metadata: body
        }
      })

      // Apply filters
      let filtered = transformedDecisions
      if (filters?.symbol) {
        filtered = filtered.filter(d => d.symbol.includes(filters.symbol!))
      }
      if (filters?.market) {
        filtered = filtered.filter(d => d.market === filters.market)
      }
      if (filters?.type) {
        filtered = filtered.filter(d => d.type === filters.type)
      }
      if (filters?.status) {
        filtered = filtered.filter(d => d.status === filters.status)
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
      const { getReportById } = await import('../api/decisions')

      const report = await getReportById(id)
      const body = report.body || {}

      const decision: Decision = {
        id: report.id,
        symbol: String(body.symbol || ''),
        market: String(body.market || 'CN'),
        type: String(body.decision_type || 'hold') as 'buy' | 'sell' | 'hold',
        confidence: Number(body.confidence || 0),
        reasoning: Array.isArray(body.reasoning) ? body.reasoning : [],
        createdAt: report.created_at,
        status: 'executed' as const,
        metadata: body
      }

      currentDecision.value = decision
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载决策详情失败'
      currentDecision.value = null
    } finally {
      loading.value = false
    }
  }

  // TODO(Task11-Fix): createDecision is CLIENT-SIDE ONLY and does not persist to backend.
  // The backend does not have a direct "create decision" endpoint.
  // Backend workflow: Decisions are generated through portfolio analysis and saved as reports.
  // Expected workflow alternatives:
  //   1. POST /api/portfolio/analysis - Triggers decision generation via agentic workflow
  //   2. GET /api/decisions/reports - Retrieves decisions as reports (already implemented in fetchDecisions)
  // Current behavior: Generates local ID, stores in memory only, marks as 'pending'
  // Migration: When direct decision creation is needed, implement backend endpoint or use portfolio analysis workflow
  async function createDecision(data: Omit<Decision, 'id' | 'createdAt'>) {
    loading.value = true
    error.value = null
    try {
      const newDecision: Decision = {
        ...data,
        id: Math.random().toString(36).substring(7),
        createdAt: new Date().toISOString(),
        status: 'pending'
      }

      // Store locally until backend workflow is triggered
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
      // Note: Backend reports are immutable
      // Updates are only allowed for locally-created pending decisions

      const index = decisions.value.findIndex(d => d.id === id)
      if (index === -1) {
        throw new Error('决策未找到')
      }

      const existing = decisions.value[index]
      if (existing.status !== 'pending') {
        throw new Error('只能更新待处理的决策')
      }

      const updatedDecision = { ...existing, ...data }
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
      // Note: Backend reports are immutable and cannot be deleted
      // Only allow deletion of locally-created pending decisions

      const existing = decisions.value.find(d => d.id === id)
      if (existing && existing.status !== 'pending') {
        throw new Error('无法删除已执行的决策')
      }

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
