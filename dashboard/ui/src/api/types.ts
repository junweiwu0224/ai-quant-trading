export type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'

export interface DataHealth {
  success: boolean
  status?: 'healthy' | 'degraded' | 'unavailable' | string
  markets?: Record<string, {
    status?: string
    research_status?: string
    provider?: string | null
    coverage?: number
    coverage_pct?: number
    data_state?: string
    data_state_label?: string
    capabilities?: string[]
    declared_capabilities?: string[]
    last_update?: string | null
    stale?: boolean
    freshness_status?: 'fresh' | 'stale' | 'not_checked' | 'unavailable' | string
    reason?: string
    manual_research?: boolean
  }>
  stock_count: number
  stock_daily: Record<string, unknown>
  watchlist_count: number
  source_health: Record<string, unknown>
  quality_summary: Record<string, unknown>
  quote: {
    running: boolean
    subscriptions: number
    temporary_subscriptions: number
    cache_count: number
    last_update_age_sec?: number
  }
  signal: {
    status: 'online' | 'stale' | 'offline'
    cache_age_hours?: number
    cache_age_label: string
    latest_date?: string
    provider: string
    model_version: string
    validation: {
      status: string
      confidence: string
      sample_days: number
      metrics: Record<string, unknown>
    }
  }
  providers?: Record<string, string>
}

export interface KLineBar {
  date: string
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
  amount?: number
}

export interface TechnicalIndicators {
  ma5?: number
  ma10?: number
  ma20?: number
  ma60?: number
  macd?: number
  signal?: number
  histogram?: number
  rsi?: number
  kdj_k?: number
  kdj_d?: number
  kdj_j?: number
  [key: string]: number | undefined
}

export interface Evidence {
  type: string
  content: string
  source: string
  timestamp: string
  confidence?: number
  metadata?: Record<string, unknown>
}
