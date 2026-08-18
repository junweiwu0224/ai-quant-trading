/**
 * Shared TypeScript types for API requests and responses
 */

// ==================== Common Types ====================

export interface ApiEnvelope<T = unknown> {
  success?: boolean
  data?: T
  error?: string
  message?: string
  [key: string]: unknown
}

export interface PaginatedResponse<T> {
  items: T[]
  total?: number
  page?: number
  pageSize?: number
  hasNext?: boolean
}

// ==================== Decision Types ====================

export interface Decision {
  id: string
  workspace_id?: string
  portfolio_id?: string
  symbol: string
  market: string
  type: 'buy' | 'sell' | 'hold'
  confidence: number
  reasoning: string[]
  created_at: string
  updated_at?: string
  price?: number
  target_price?: number
  stop_loss?: number
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

export interface DecisionPortfolio {
  id: string
  workspace_id: string
  market: string
  name: string
  created_at: string
  members?: DecisionMember[]
  version?: DecisionVersion
}

export interface DecisionMember {
  portfolio_id: string
  symbol: string
  name?: string
  added_at: string
}

export interface DecisionVersion {
  id: string
  portfolio_id: string
  strategies?: Array<Record<string, unknown>>
  thresholds?: Record<string, unknown>
  validation?: Record<string, unknown>
  risk_rules?: Record<string, unknown>
  created_at: string
}

export interface DecisionReport {
  id: string
  workspace_id: string
  portfolio_id: string
  version_id: string
  body: Record<string, unknown>
  report_hash: string
  created_at: string
}

export interface DecisionCommand {
  id: string
  command_id?: string
  workspace_id: string
  portfolio_id?: string
  command_type: string
  payload: Record<string, unknown>
  status: 'queued' | 'running' | 'completed' | 'rejected' | 'failed'
  result?: unknown
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

// ==================== Market Data Types ====================

export type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'

export interface MarketData {
  code: string
  name: string
  price: number
  change?: number
  change_pct?: number
  volume?: number
  amount?: number
  open?: number
  high?: number
  low?: number
  pre_close?: number
  timestamp?: string
  market: MarketCode
  industry?: string
  turnover_rate?: number
  volume_ratio?: number
}

export interface Quote {
  code: string
  name?: string
  price: number
  change?: number
  change_pct?: number
  timestamp: number
  volume?: number
  amount?: number
  bid?: number
  ask?: number
  bid_size?: number
  ask_size?: number
  turnover_rate?: number
  volume_ratio?: number
  industry?: string
}

export interface MarketInfo {
  code: MarketCode
  name: string
  timezone: string
  currency: string
  enabled: boolean
}

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
  quote: QuoteServiceHealth
  signal: SignalHealth
  providers?: Record<string, string>
}

export interface QuoteServiceHealth {
  running: boolean
  subscriptions: number
  temporary_subscriptions: number
  cache_count: number
  last_update_age_sec?: number
}

export interface SignalHealth {
  status: 'online' | 'stale' | 'offline'
  cache_age_hours?: number
  cache_age_label: string
  latest_date?: string
  provider: string
  model_version: string
  validation: SignalValidation
}

export interface SignalValidation {
  status: string
  confidence: string
  sample_days: number
  metrics: Record<string, unknown>
}

export interface DecisionMatrix {
  success: boolean
  scope: string
  items: DecisionMatrixItem[]
  summary: DecisionMatrixSummary
}

export interface DecisionMatrixItem {
  code: string
  name: string
  industry?: string
  price?: number
  change_pct?: number
  peg_next_year?: number
  growth_next_year_pct?: number
  upside_pct?: number
  report_count: number
  signal_rank?: number
  signal_score?: number
  signal_confidence?: string
  decision_score: number
  decision_label: string
  reason_tags: string[]
  risk_tags: string[]
  risk_level: string
  next_actions: string[]
  primary_action: string
  matrix_rank: number
}

export interface DecisionMatrixSummary {
  total: number
  valuation_coverage_pct?: number
  signal_coverage_pct?: number
  high_score: number
  peg_le_1: number
  signal_top_50: number
  signal_date?: string
  signal_provider: string
  signal_model_version: string
  signal_status: string
  high_risk: number
  actionable: number
}

// ==================== Research Types ====================

export interface KLineBar {
  date: string
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
  amount?: number
}

export interface ResearchData {
  symbol: string
  market: MarketInfo
  bars: KLineBar[]
  status: string
  source: string
  latest_date?: string
  updated_at?: string
  data_quality: DataQuality
  authoritative: boolean
  fallback_reason?: string
}

export interface DataQuality {
  status: 'available' | 'partial' | 'unavailable'
  bars?: number
  authoritative: boolean
  manual_research_only: boolean
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

// ==================== Request/Response Wrappers ====================

export interface CreateDecisionRequest {
  symbol: string
  market: string
  type: 'buy' | 'sell' | 'hold'
  confidence: number
  reasoning: string[]
  price?: number
  target_price?: number
  stop_loss?: number
  metadata?: Record<string, unknown>
}

export interface UpdateDecisionRequest {
  type?: 'buy' | 'sell' | 'hold'
  confidence?: number
  reasoning?: string[]
  price?: number
  target_price?: number
  stop_loss?: number
  status?: 'pending' | 'executed' | 'cancelled'
  metadata?: Record<string, unknown>
}

export interface CreatePortfolioRequest {
  market: string
  name: string
}

export interface AddMemberRequest {
  symbol: string
  name?: string
}

export interface CreateVersionRequest {
  strategies?: Array<Record<string, unknown>>
  thresholds?: Record<string, unknown>
  validation?: Record<string, unknown>
  risk_rules?: Record<string, unknown>
}

export interface MarketDataQuery {
  market: MarketCode
  symbol: string
  period?: 'daily' | 'weekly' | 'monthly' | '1min' | '5min' | '15min' | '30min' | '60min'
  count?: number
}

export interface SearchQuery {
  query: string
  market?: MarketCode
  limit?: number
}
