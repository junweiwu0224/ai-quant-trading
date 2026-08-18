import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type WorkspaceQueryState = {
  tab: string | null
  filters: Record<string, string | number | boolean>
  sort: string | null
  page: number
  selected: string[]
  timeframe: string | null
}

export type ResearchContextValue = {
  market: string | null
  symbol: string | null
  name: string | null
  strategy: string | null
  backtestRequest: Record<string, unknown> | null
  backtestResult: Record<string, unknown> | null
  researchSnapshot: Record<string, unknown> | null
  riskStatus: Record<string, unknown> | null
  eligibility: Record<string, unknown> | null
  query: WorkspaceQueryState
  freshness: 'live' | 'delayed' | 'stale' | 'unavailable' | null
  source: string | null
  lastUpdatedAt: string | null
}

type Instrument = { market: string; symbol: string; name?: string }

const STORAGE_KEY = 'quant-research-context'
const supportedMarkets = new Set(['CN', 'HK', 'US', 'JP', 'KR', 'TW'])

function emptyQuery(): WorkspaceQueryState {
  return { tab: null, filters: {}, sort: null, page: 1, selected: [], timeframe: null }
}

function emptyContext(): ResearchContextValue {
  return {
    market: null,
    symbol: null,
    name: null,
    strategy: null,
    backtestRequest: null,
    backtestResult: null,
    researchSnapshot: null,
    riskStatus: null,
    eligibility: null,
    query: emptyQuery(),
    freshness: null,
    source: null,
    lastUpdatedAt: null,
  }
}

function normalizeInstrument(instrument: Instrument): Instrument {
  const market = instrument.market.trim().toUpperCase()
  const symbol = instrument.symbol.trim()
  if (!supportedMarkets.has(market) || !symbol) throw new Error('研究对象市场或代码无效')
  return { market, symbol, name: instrument.name?.trim() || undefined }
}

function readStoredContext(): ResearchContextValue {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyContext()
    const parsed = JSON.parse(raw) as Partial<ResearchContextValue>
    if (!parsed.market || !parsed.symbol) return emptyContext()
    return { ...emptyContext(), ...parsed, query: { ...emptyQuery(), ...(parsed.query || {}) } }
  } catch {
    return emptyContext()
  }
}

export const useResearchContextStore = defineStore('researchContext', () => {
  const context = ref<ResearchContextValue>(readStoredContext())
  const hasInstrument = computed(() => Boolean(context.value.market && context.value.symbol))

  function persist() {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(context.value))
  }

  function setInstrument(instrument: Instrument) {
    const normalized = normalizeInstrument(instrument)
    const changed = context.value.market !== normalized.market || context.value.symbol !== normalized.symbol
    context.value.market = normalized.market
    context.value.symbol = normalized.symbol
    context.value.name = normalized.name || null
    context.value.lastUpdatedAt = new Date().toISOString()
    if (changed) clearDerivedState(false)
    persist()
  }

  function setQuery(next: Partial<WorkspaceQueryState>) {
    context.value.query = {
      ...context.value.query,
      ...next,
      filters: next.filters ? { ...context.value.query.filters, ...next.filters } : context.value.query.filters,
      selected: next.selected ? [...next.selected] : context.value.query.selected,
    }
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function clearQuery() {
    context.value.query = emptyQuery()
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setFreshness(freshness: ResearchContextValue['freshness'], source?: string | null) {
    context.value.freshness = freshness
    if (source !== undefined) context.value.source = source
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setStrategy(strategy: string | null) {
    context.value.strategy = strategy?.trim() || null
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setBacktest(request: Record<string, unknown>, result: Record<string, unknown>) {
    context.value.backtestRequest = request
    context.value.backtestResult = result
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setResearchSnapshot(snapshot: Record<string, unknown> | null) {
    context.value.researchSnapshot = snapshot
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setRiskStatus(status: Record<string, unknown> | null) {
    context.value.riskStatus = status
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function setEligibility(eligibility: Record<string, unknown> | null) {
    context.value.eligibility = eligibility
    context.value.lastUpdatedAt = new Date().toISOString()
    persist()
  }

  function clearDerivedState(shouldPersist = true) {
    context.value.backtestRequest = null
    context.value.backtestResult = null
    context.value.researchSnapshot = null
    context.value.riskStatus = null
    context.value.eligibility = null
    if (shouldPersist) persist()
  }

  function clear() {
    context.value = emptyContext()
    sessionStorage.removeItem(STORAGE_KEY)
  }

  return {
    context,
    hasInstrument,
    setInstrument,
    setQuery,
    clearQuery,
    setFreshness,
    setStrategy,
    setBacktest,
    setResearchSnapshot,
    setRiskStatus,
    setEligibility,
    clearDerivedState,
    clear,
  }
})
