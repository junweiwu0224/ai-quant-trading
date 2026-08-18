/**
 * Research API client - handles research data, backtests, and analysis
 */

import { api, isAbortError } from './client'
import type {
  MarketCode,
  KLineBar,
  TechnicalIndicators,
  Evidence
} from './types'

export interface SourceState {
  source: 'news' | 'reports'
  status: 'available' | 'partial' | 'unavailable'
  error?: string
  provider?: string
  asOf?: string
}

type ResearchResponse = Record<string, unknown>

function finiteNumber(value: unknown): number | undefined {
  if (value === null || value === undefined || value === '') return undefined
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) ? number : undefined
}

function errorMessage(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) return value
  if (value instanceof Error && value.message) return value.message
  return fallback
}

// ==================== K-Line Data ====================

export async function getKLineData(
  market: MarketCode,
  symbol: string,
  period: 'daily' | 'weekly' | 'monthly' | '1min' | '5min' | '15min' | '30min' | '60min' = 'daily',
  count: number = 120,
  signal?: AbortSignal
): Promise<{ bars: KLineBar[]; source?: string; asOf?: string; error?: string; status?: string; coveragePct?: number }> {
  const response = await api.get<ResearchResponse>(
    `/api/stock/kline/${encodeURIComponent(symbol)}`,
    { market, period, count: count.toString() },
    signal,
  )

  const rawKlines = Array.isArray(response.klines)
    ? response.klines
    : Array.isArray(response.bars)
      ? response.bars
      : []
  const bars = rawKlines.flatMap((row): KLineBar[] => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return []
    const item = row as Record<string, unknown>
    const date = item.date ?? item.datetime ?? item.time
    if (date === null || date === undefined || date === '') return []
    return [{
      date: String(date),
      open: finiteNumber(item.open),
      close: finiteNumber(item.close),
      high: finiteNumber(item.high),
      low: finiteNumber(item.low),
      volume: finiteNumber(item.volume),
      amount: finiteNumber(item.amount)
    } as KLineBar]
  })

  return {
    bars,
    source: typeof response.source === 'string' ? response.source : undefined,
    asOf: typeof response.as_of === 'string' ? response.as_of : undefined,
    error: typeof response.error === 'string' ? response.error : undefined,
    status: typeof response.data_state === 'string' ? response.data_state : typeof response.status === 'string' ? response.status : undefined,
    coveragePct: finiteNumber(response.coverage_pct)
  }
}

// ==================== Technical Indicators ====================

export async function getTechnicalIndicators(
  market: MarketCode,
  symbol: string,
  signal?: AbortSignal
): Promise<TechnicalIndicators> {
  // Use multi-timeframe endpoint which includes technical indicators
  const response = await api.get<Record<string, unknown>>(
    `/api/stock/multi-timeframe/${encodeURIComponent(symbol)}`,
    { market },
    signal,
  )

  // Extract technical indicators from response
  const indicators: TechnicalIndicators = {}
  // Both CN and manual-research responses expose the daily analysis under
  // `daily`; the legacy `daily_indicators` shape is retained as a fallback.
  // Keep extraction market-neutral so a missing field stays missing instead
  // of becoming a fabricated zero.
  const daily = (response.daily || response.daily_indicators || {}) as Record<string, unknown>
  const ma5 = finiteNumber(daily.ma5)
  const ma10 = finiteNumber(daily.ma10)
  const ma20 = finiteNumber(daily.ma20)
  const ma60 = finiteNumber(daily.ma60)
  const rsi = finiteNumber(daily.rsi)
  const macd = finiteNumber(daily.macd ?? daily.dif)
  if (ma5 !== undefined) indicators.ma5 = ma5
  if (ma10 !== undefined) indicators.ma10 = ma10
  if (ma20 !== undefined) indicators.ma20 = ma20
  if (ma60 !== undefined) indicators.ma60 = ma60
  if (rsi !== undefined) indicators.rsi = rsi
  if (macd !== undefined) indicators.macd = macd

  return indicators
}

// ==================== Evidence Chain ====================

export async function getEvidence(
  market: MarketCode,
  symbol: string,
  signal?: AbortSignal
): Promise<{ evidence: Evidence[]; sources: SourceState[]; evidence_snapshot_id?: string }> {
  // Aggregate evidence from multiple sources
  const evidence: Evidence[] = []
  const sources: SourceState[] = []

  try {
    // Get stock news as evidence
    const news = await api.get<Record<string, unknown>>(
      `/api/stock/news/${encodeURIComponent(symbol)}`,
      { market },
      signal
    )

    const newsItems = Array.isArray(news.news) ? news.news : []
    if (news.success === false) {
      sources.push({ source: 'news', status: 'unavailable', error: errorMessage(news.error, '新闻数据不可用') })
    } else {
      evidence.push(...newsItems.map((item: Record<string, unknown>) => ({
        type: 'news',
        content: String(item.title || ''),
        source: String(item.source || 'news'),
        timestamp: String(item.date || new Date().toISOString()),
        metadata: item
      })))
      sources.push({
        source: 'news',
        status: newsItems.length ? 'available' : 'partial',
        provider: typeof news.provider === 'string' ? news.provider : undefined,
        asOf: typeof news.as_of === 'string' ? news.as_of : undefined
      })
    }
  } catch (err) {
    if (isAbortError(err)) throw err
    sources.push({ source: 'news', status: 'unavailable', error: errorMessage(err, '新闻数据不可用') })
  }

  try {
    // Get stock reports as evidence
    const reports = await api.get<Record<string, unknown>>(
      `/api/llm/reports/${encodeURIComponent(symbol)}`,
      { market, page_size: '5' },
      signal
    )

    if (reports.success === false) {
      sources.push({ source: 'reports', status: 'unavailable', error: errorMessage(reports.error, '研报数据不可用') })
    } else {
      const reportItems = Array.isArray(reports.items)
        ? reports.items
        : Array.isArray(reports.reports)
          ? reports.reports
          : []
      evidence.push(...reportItems.map((item: Record<string, unknown>) => ({
        type: 'report',
        content: String(item.title || ''),
        source: String(item.institution || item.org || 'analyst'),
        timestamp: String(item.date || new Date().toISOString()),
        confidence: item.rating ? Number(item.rating) : undefined,
        metadata: item
      })))
      sources.push({
        source: 'reports',
        status: reportItems.length ? 'available' : 'partial',
        provider: typeof reports.provider === 'string' ? reports.provider : undefined,
        asOf: typeof reports.as_of === 'string' ? reports.as_of : undefined,
      })
    }
  } catch (err) {
    if (isAbortError(err)) throw err
    sources.push({ source: 'reports', status: 'unavailable', error: errorMessage(err, '研报数据不可用') })
  }

  return { evidence, sources }
}

// ==================== Backtest Drafts ====================

// TODO(Task11-Fix): Backtest drafts are CLIENT-SIDE ONLY placeholders.
// These functions use localStorage because backend draft persistence is not implemented.
// Expected backend endpoints (when implemented):
//   - GET /api/backtest/drafts - List all drafts
//   - GET /api/backtest/drafts/:id - Get draft by ID
//   - POST /api/backtest/drafts - Create new draft
//   - PUT /api/backtest/drafts/:id - Update draft
//   - DELETE /api/backtest/drafts/:id - Delete draft
// Expected response format: { id, name, strategy, symbols, start_date, end_date, initial_capital, parameters, created_at, updated_at }
// Migration: When backend is ready, replace localStorage calls with API calls using the api client.

export interface BacktestDraft {
  id: string
  name: string
  strategy: string
  symbols: string[]
  start_date: string
  end_date: string
  initial_capital: number
  parameters: Record<string, unknown>
  created_at: string
  updated_at: string
}

export async function getBacktestDraft(id: string): Promise<BacktestDraft> {
  const stored = localStorage.getItem(`backtest_draft_${id}`)
  if (!stored) {
    throw new Error('回测草稿未找到')
  }
  return JSON.parse(stored)
}

export async function saveBacktestDraft(data: Omit<BacktestDraft, 'id' | 'created_at' | 'updated_at'>): Promise<BacktestDraft> {
  const draft: BacktestDraft = {
    ...data,
    id: Math.random().toString(36).substring(7),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
  localStorage.setItem(`backtest_draft_${draft.id}`, JSON.stringify(draft))
  return draft
}

export async function listBacktestDrafts(): Promise<BacktestDraft[]> {
  const drafts: BacktestDraft[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith('backtest_draft_')) {
      const stored = localStorage.getItem(key)
      if (stored) {
        try {
          drafts.push(JSON.parse(stored))
        } catch (err) {
          console.warn('Failed to parse backtest draft:', err)
        }
      }
    }
  }
  return drafts.sort((a, b) =>
    new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  )
}

export async function deleteBacktestDraft(id: string): Promise<void> {
  localStorage.removeItem(`backtest_draft_${id}`)
}

// ==================== Backtest Execution ====================

export interface BacktestRequest {
  strategy: string
  symbols: string[]
  start_date: string
  end_date: string
  initial_capital: number
  parameters?: Record<string, unknown>
}

export interface BacktestResult {
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  trades: number
  equity_curve: Array<{ date: string; value: number }>
  trades_detail: Array<Record<string, unknown>>
}

export async function runBacktest(request: BacktestRequest): Promise<BacktestResult> {
  return api.post<BacktestResult>('/api/backtest/run', request)
}

// ==================== Stock Analysis ====================

export async function getStockMultiTimeframe(
  symbol: string,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/multi-timeframe/${encodeURIComponent(symbol)}`, { market })
}

export async function getStockChips(
  symbol: string,
  days: number = 120,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/chips/${encodeURIComponent(symbol)}`, {
    days: days.toString(),
    market
  })
}

export async function getStockDragonTiger(
  symbol: string,
  days: number = 90,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/dragon-tiger/${encodeURIComponent(symbol)}`, {
    days: days.toString(),
    market
  })
}

export async function getStockIndustryComparison(
  symbol: string,
  market: MarketCode = 'CN'
): Promise<Record<string, unknown>> {
  return api.get(`/api/stock/industry-comparison/${encodeURIComponent(symbol)}`, { market })
}
