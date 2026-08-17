export type ApiState = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

export interface ApiEnvelope<T> {
  success?: boolean
  data?: T
  error?: string
  detail?: string
  [key: string]: unknown
}

export interface AccountUser {
  id: string
  username: string
  display_name?: string
  email?: string
  role?: string
  avatar_color?: string
  [key: string]: unknown
}

export interface AccountWorkspace {
  id: string
  user_id?: string
  name?: string
  slug?: string
  settings?: Record<string, unknown>
  [key: string]: unknown
}

export interface AccountState {
  authenticated: boolean
  user?: AccountUser
  workspace?: AccountWorkspace
  permissions?: Record<string, boolean>
  session?: Record<string, unknown>
  [key: string]: unknown
}

export interface RegisterPayload {
  username: string
  password: string
  invite_code: string
  display_name?: string
  email?: string
}

export interface WatchlistItem {
  code: string
  name?: string
  industry?: string
  sector?: string
  price?: number | null
  change_pct?: number | null
  data_date?: string | null
  source?: string
}

export interface DataHealth {
  success?: boolean
  stock_count?: number
  watchlist_count?: number
  source_health?: Record<string, unknown>
  quality_summary?: Record<string, unknown>
  quote?: { running?: boolean; cache_count?: number; last_update_age_sec?: number | null }
  signal?: { status?: string; provider?: string; latest_date?: string; total?: number; validation?: Record<string, unknown> }
  qlib?: { status?: string; cache_age_label?: string }
  providers?: Record<string, string>
}

export interface DecisionMatrix {
  items?: Array<Record<string, unknown>>
  summary?: Record<string, unknown>
  selected_codes?: string[]
  scope?: string
  signal_health?: Record<string, unknown>
  source_health?: Record<string, unknown>
  error?: string
  success?: boolean
}

export interface DecisionItem {
  id?: string
  symbol?: string
  action?: string
  score?: number | null
  previous_action?: string | null
  reason_codes?: string[]
  valid?: boolean
  stale?: boolean
  risk_veto?: boolean
  confirmed?: boolean
  contributions?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface DecisionReportBody {
  report_type?: string
  run_id?: string
  portfolio_id?: string
  portfolio_version_id?: string
  input_hash?: string
  version_hash?: string
  source?: string
  quality_status?: string
  market?: string
  market_capabilities?: Record<string, unknown>
  strategy_weights?: Array<Record<string, unknown>>
  evidence?: Record<string, unknown>
  validation?: {
    status?: string
    validation_hash?: string | null
    evidence_id?: string | null
    result?: Record<string, unknown> | null
  }
  eligibility?: {
    status?: string
    checks?: Record<string, boolean>
    reasons?: string[]
  }
  trigger?: string
  created_at?: string
  decisions?: DecisionItem[]
}

export interface DecisionReport {
  id: string
  decision_run_id?: string
  report_type?: string
  body?: DecisionReportBody
  report_hash?: string
  created_at?: string
  share_url?: string
  share_expires_at?: string
  ai_commentary?: Array<Record<string, unknown>>
  ai_commentary_status?: string
  delivery_attempts?: Array<Record<string, unknown>>
}

export interface DecisionShareResponse {
  url: string
  link?: {
    expires_at?: string
  }
}

export interface SharedDecisionReport {
  report: DecisionReportBody
  report_hash?: string
  expires_at?: string
  ai_commentary?: Array<Record<string, unknown>>
  ai_commentary_status?: string
  delivery_attempts?: Array<Record<string, unknown>>
}

export interface QuoteDetail {
  code?: string
  name?: string
  price?: number | null
  change_pct?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  pre_close?: number | null
  volume?: number | null
  amount?: number | null
  [key: string]: unknown
}

export interface ResearchBar {
  date: string
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  volume?: number | null
}

export interface DecisionResearch {
  symbol: string
  market?: Record<string, unknown>
  bars: ResearchBar[]
  status: string
  source?: string
  latest_date?: string | null
  updated_at?: string | null
  authoritative?: boolean
  fallback_reason?: string
  data_quality?: {
    status?: string
    bars?: number
    authoritative?: boolean
    manual_research_only?: boolean
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface LegacyLink {
  label: string
  description: string
  href: string
  group: string
  status?: string
}
