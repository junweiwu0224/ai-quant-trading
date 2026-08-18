/**
 * Market data API client - handles market data, quotes, and health endpoints
 */

import { api } from './client'
import type {
  MarketCode,
  MarketData,
  Quote,
  DataHealth,
  DecisionMatrix,
  ApiEnvelope
} from './types'

// ==================== Market Data Health ====================

export async function getDataHealth(fast: boolean = false): Promise<DataHealth> {
  return api.get<DataHealth>('/api/datahub/health', { fast: fast ? 'true' : 'false' })
}

export interface MarketCapability {
  code: MarketCode
  name_zh: string
  name_en: string
  status: 'active' | 'limited' | 'unavailable'
  capabilities: string[]
  provider: string | null
  reason: string | null
  trading_hours: {
    open: string
    close: string
    lunch_start: string | null
    lunch_end: string | null
  }
  timezone: string
  currency: string
  data_state?: 'configured' | 'not_integrated' | string
  data_state_label?: string
  runtime_status?: string
  runtime_state_label?: string
  freshness_status?: string
  daily_granularities?: string[]
  intraday_granularities?: string[]
  provider_details?: Array<{
    name: string
    status: string
    granularities: string[]
    purpose: string
    qualifies_for_intraday_auto_push: boolean
    qualifies_for_daily_auto_push: boolean
    qualification_reasons?: string[]
    last_checked_at?: string | null
    freshness_status?: string
    [key: string]: unknown
  }>
  target_providers?: string[]
  manual_research?: boolean
  scheduled_daily_report?: boolean
  intraday_auto_push?: boolean
  qualification_reasons?: string[]
  generated_at?: string | null
  source_status?: string
  freshness?: string | null
  adapter?: Record<string, unknown>
}

export interface MarketsResponse {
  success: boolean
  markets: MarketCapability[]
  total: number
  active_count: number
  generated_at: string
}

export async function getMarketCapabilities(): Promise<MarketsResponse> {
  return api.get<MarketsResponse>('/api/market/capabilities')
}

// ==================== Decision Matrix ====================

export interface DecisionMatrixParams {
  scope?: 'watchlist' | 'codes' | 'signal' | 'qlib'
  codes?: string
  limit?: number
  fast?: boolean
  force_fallback?: boolean
  max_wait_sec?: number
}

export async function getDecisionMatrix(params: DecisionMatrixParams = {}): Promise<DecisionMatrix> {
  const queryParams: Record<string, string | number> = {}
  if (params.scope) queryParams.scope = params.scope
  if (params.codes) queryParams.codes = params.codes
  if (params.limit) queryParams.limit = params.limit
  if (params.fast !== undefined) queryParams.fast = params.fast ? 'true' : 'false'
  if (params.force_fallback !== undefined) queryParams.force_fallback = params.force_fallback ? 'true' : 'false'
  if (params.max_wait_sec !== undefined) queryParams.max_wait_sec = params.max_wait_sec

  return api.get<DecisionMatrix>('/api/datahub/decision-matrix', queryParams)
}

// ==================== Stock Data ====================

export interface QuoteResponse extends Quote {
  success?: boolean
  available?: boolean
  data_state?: string
  error?: string
}

export async function getStockQuote(
  code: string,
  market: MarketCode = 'CN'
): Promise<QuoteResponse> {
  const response = await api.get<QuoteResponse>(`/api/stock/detail/${encodeURIComponent(code)}`, { market })
  if (response.success === false || response.available === false) {
    throw new Error(response.error || `${market} 当前行情不可用`)
  }
  return response
}

export async function getStockKline(
  code: string,
  period: string = 'daily',
  count: number = 120,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/kline/${encodeURIComponent(code)}`, {
    period,
    count: count.toString(),
    market
  })
}

export async function getStockTimeline(
  code: string,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/timeline/${encodeURIComponent(code)}`, { market })
}

export async function getStockCapitalFlow(
  code: string,
  days: number = 20,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/capital-flow/${encodeURIComponent(code)}`, {
    days: days.toString(),
    market
  })
}

export async function getStockNews(
  code: string,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/news/${encodeURIComponent(code)}`, { market })
}

// ==================== Realtime Quotes ====================

export async function getQuoteServiceStatus(): Promise<{
  running: boolean
  subscriptions: number
  cache_count: number
  update_count: number
  interval: number
  last_update: number | null
  connections: number
}> {
  return api.get('/quotes/status')
}

export async function subscribeQuotes(codes: string[]): Promise<{
  message: string
  total: number
}> {
  return api.post('/quotes/subscribe', codes)
}

export async function unsubscribeQuotes(codes: string[]): Promise<{
  message: string
  total: number
}> {
  return api.post('/quotes/unsubscribe', codes)
}

// ==================== Market Overview ====================

export async function getMarketRadar(market: MarketCode = 'CN'): Promise<ApiEnvelope<Record<string, unknown>>> {
  return api.get('/api/market/radar', { fast: 'true', market })
}

export async function getMarketBreadth(market: MarketCode = 'CN'): Promise<Record<string, unknown>> {
  return api.get('/api/market/breadth', { market })
}

export async function getMarketSectors(fast: boolean = true, market: MarketCode = 'CN'): Promise<Record<string, unknown>> {
  return api.get('/api/market/sectors', {
    type: 'industry',
    fast: fast ? 'true' : 'false',
    market
  })
}

export async function getMarketHeatmap(fast: boolean = true, market: MarketCode = 'CN'): Promise<Record<string, unknown>> {
  return api.get('/api/market/heatmap', { fast: fast ? 'true' : 'false', market })
}

export async function getMarketHotspot(market: MarketCode = 'CN'): Promise<Record<string, unknown>> {
  return api.get('/api/market/hotspot', { market })
}

export async function getMarketNews(market: MarketCode = 'CN'): Promise<Record<string, unknown>> {
  return api.get('/api/market/news', { market })
}

// ==================== Watchlist ====================

export async function getWatchlist(): Promise<string[]> {
  return api.get<string[]>('/api/watchlist')
}

export async function addToWatchlist(code: string): Promise<Record<string, unknown>> {
  return api.post('/api/watchlist', { code })
}

export async function removeFromWatchlist(code: string): Promise<Record<string, unknown>> {
  return api.delete(`/api/watchlist/${encodeURIComponent(code)}`)
}

// ==================== Search ====================

export async function searchSymbols(
  query: string,
  market?: MarketCode
): Promise<Array<{ code: string; name: string; market: string }>> {
  const params: Record<string, string> = { q: query }
  if (market) params.market = market

  try {
    const response = await api.get<{ results?: Array<{ code: string; name: string; market?: string }>; success?: boolean }>('/api/stock/search', params)
    return (response.results || []).map((item) => ({ code: item.code, name: item.name, market: item.market || market || 'CN' }))
  } catch {
    return []
  }
}
