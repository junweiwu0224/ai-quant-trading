/**
 * Research API client - handles research data, backtests, and analysis
 */

import { api } from './client'
import type {
  MarketCode,
  KLineBar,
  TechnicalIndicators,
  Evidence
} from './types'

// ==================== K-Line Data ====================

export async function getKLineData(
  market: MarketCode,
  symbol: string,
  period: 'daily' | 'weekly' | 'monthly' | '1min' | '5min' | '15min' | '30min' | '60min' = 'daily',
  count: number = 120
): Promise<{ bars: KLineBar[] }> {
  const response = await api.get<Record<string, unknown>>(
    `/api/stock/kline/${encodeURIComponent(symbol)}`,
    {
      market,
      period,
      count: count.toString()
    }
  )

  // Transform backend response to our format
  const klines = (response.klines_raw || []) as Array<Array<string | number>>
  const bars: KLineBar[] = klines.map((kline) => ({
    date: String(kline[0]),
    open: Number(kline[1]),
    close: Number(kline[2]),
    high: Number(kline[3]),
    low: Number(kline[4]),
    volume: Number(kline[5]),
    amount: kline.length > 6 ? Number(kline[6]) : undefined
  }))

  return { bars }
}

// ==================== Technical Indicators ====================

export async function getTechnicalIndicators(
  market: MarketCode,
  symbol: string
): Promise<TechnicalIndicators> {
  // Use multi-timeframe endpoint which includes technical indicators
  const response = await api.get<Record<string, unknown>>(
    `/api/stock/multi-timeframe/${encodeURIComponent(symbol)}`,
    { market }
  )

  // Extract technical indicators from response
  const indicators: TechnicalIndicators = {}

  if (response.daily) {
    const daily = response.daily as Record<string, unknown>
    if (daily.ma5) indicators.ma5 = Number(daily.ma5)
    if (daily.ma10) indicators.ma10 = Number(daily.ma10)
    if (daily.ma20) indicators.ma20 = Number(daily.ma20)
    if (daily.ma60) indicators.ma60 = Number(daily.ma60)
  }

  return indicators
}

// ==================== Evidence Chain ====================

export async function getEvidence(
  market: MarketCode,
  symbol: string
): Promise<{ evidence: Evidence[] }> {
  // Aggregate evidence from multiple sources
  const evidence: Evidence[] = []

  try {
    // Get stock news as evidence
    const news = await api.get<Record<string, unknown>>(
      `/api/stock/news/${encodeURIComponent(symbol)}`,
      { market }
    )

    if (news.items && Array.isArray(news.items)) {
      evidence.push(...news.items.map((item: Record<string, unknown>) => ({
        type: 'news',
        content: String(item.title || ''),
        source: String(item.source || 'news'),
        timestamp: String(item.date || new Date().toISOString()),
        metadata: item
      })))
    }
  } catch (err) {
    console.warn('Failed to fetch news evidence:', err)
  }

  try {
    // Get stock reports as evidence
    const reports = await api.get<Record<string, unknown>>(
      `/api/llm/reports/${encodeURIComponent(symbol)}`,
      { market, page_size: '5' }
    )

    if (reports.items && Array.isArray(reports.items)) {
      evidence.push(...reports.items.map((item: Record<string, unknown>) => ({
        type: 'report',
        content: String(item.title || ''),
        source: String(item.institution || 'analyst'),
        timestamp: String(item.date || new Date().toISOString()),
        confidence: item.rating ? Number(item.rating) : undefined,
        metadata: item
      })))
    }
  } catch (err) {
    console.warn('Failed to fetch report evidence:', err)
  }

  return { evidence }
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
