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

export async function getStockQuote(
  code: string,
  market: MarketCode = 'CN'
): Promise<Quote> {
  return api.get<Quote>(`/api/stock/detail/${encodeURIComponent(code)}`, { market })
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

export async function getMarketRadar(): Promise<ApiEnvelope<Record<string, unknown>>> {
  return api.get('/api/market/radar', { fast: 'true' })
}

export async function getMarketBreadth(): Promise<Record<string, unknown>> {
  return api.get('/api/market/breadth')
}

export async function getMarketSectors(fast: boolean = true): Promise<Record<string, unknown>> {
  return api.get('/api/market/sectors', {
    type: 'industry',
    fast: fast ? 'true' : 'false'
  })
}

export async function getMarketHeatmap(fast: boolean = true): Promise<Record<string, unknown>> {
  return api.get('/api/market/heatmap', { fast: fast ? 'true' : 'false' })
}

export async function getMarketHotspot(): Promise<Record<string, unknown>> {
  return api.get('/api/market/hotspot')
}

export async function getMarketNews(): Promise<Record<string, unknown>> {
  return api.get('/api/market/news')
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

// TODO(Task11-Fix): This endpoint is unverified in the backend.
// Expected endpoint: GET /api/search?q={query}&market={market}
// Expected response: Array<{ code: string; name: string; market: string }>
// Backend implementation status: NOT FOUND during review
// When backend is ready, this should work as-is. Until then, may return 404.
export async function searchSymbols(
  query: string,
  market?: MarketCode
): Promise<Array<{ code: string; name: string; market: string }>> {
  const params: Record<string, string> = { q: query }
  if (market) params.market = market

  try {
    return await api.get('/api/search', params)
  } catch (err) {
    // Fallback to empty results if endpoint not implemented
    console.warn('Search endpoint not available:', err)
    return []
  }
}
