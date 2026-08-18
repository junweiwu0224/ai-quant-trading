import type { AccountState, ApiEnvelope, DataHealth, DecisionMatrix, DecisionResearch, QuoteDetail, RegisterPayload, WatchlistItem } from '../types'

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function formatErrorValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(formatErrorValue).filter(Boolean).join('；')
  if (typeof value !== 'object') return ''

  const record = value as Record<string, unknown>
  const location = Array.isArray(record.loc) ? record.loc.filter((item) => item !== 'body').join('.') : ''
  const direct = ['message', 'msg', 'detail', 'error']
    .map((key) => formatErrorValue(record[key]))
    .find(Boolean)
  if (direct) return location ? `${location}：${direct}` : direct

  const nested = ['errors', 'issues', 'validation_errors', 'non_field_errors']
    .map((key) => formatErrorValue(record[key]))
    .find(Boolean)
  if (nested) return nested

  const entries = Object.entries(record)
    .map(([key, item]) => {
      const formatted = formatErrorValue(item)
      return formatted ? `${key}：${formatted}` : ''
    })
    .filter(Boolean)
  if (entries.length) return entries.join('；')
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

export function formatApiError(payload: unknown, status?: number): string {
  const message = formatErrorValue(payload)
  if (message && message !== '{}') return message
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 403) return '当前账号没有执行此操作的权限'
  if (status === 404) return '请求的资源不存在'
  if (status === 429) return '请求过于频繁，请稍后重试'
  return status ? `请求失败（${status}）` : '网络请求失败，请检查连接后重试'
}

function marketPath(path: string, market = 'CN'): string {
  const normalized = String(market || 'CN').trim().toUpperCase() || 'CN'
  return `${path}${path.includes('?') ? '&' : '?'}market=${encodeURIComponent(normalized)}`
}

export type DecisionCommand<T = unknown> = {
  id: string
  command_id?: string
  status: 'queued' | 'running' | 'completed' | 'rejected' | 'failed' | string
  result?: T
  error?: string
}

export type AIProviderProtocol = 'openai_compatible' | 'litellm' | 'local_cli' | string

export type AITaskStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'degraded'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled'
  | string

export interface AIProviderChannel {
  id: string
  name: string
  protocol?: AIProviderProtocol
  base_url?: string
  model?: string
  secret_ref?: string
  command?: string[]
  enabled?: boolean
  priority?: number
  retries?: number
  timeout_seconds?: number
  supports_json?: boolean
  supports_stream?: boolean
  secret_available?: boolean
  config_error?: string
  capabilities?: AIProviderCapabilities
  readiness?: AIProviderReadiness
  attempts?: AIProviderAttempt[]
  [key: string]: unknown
}

export interface AIProviderCapabilities {
  chat?: boolean
  structured_json?: boolean
  stream?: boolean
  structured_report?: boolean
  provider_trace?: boolean
  decision_effect?: 'none' | string
  human_review_only?: boolean
  [key: string]: unknown
}

export interface AIProviderReadiness {
  configuration?: string
  credential?: string
  configured?: boolean
  runtime?: string
  runtime_verified?: boolean
  overall?: string
  last_error_code?: string | null
  last_checked_at?: string | number | null
  ready?: boolean
  error?: string
  [key: string]: unknown
}

export interface AIProviderAttempt {
  attempt?: number | string
  provider?: string
  model?: string
  relation?: 'initial' | 'retry' | 'fallback' | string
  retry_index?: number
  fallback_from?: string | null
  fallback_to?: string | null
  status?: string
  duration_ms?: number | null
  error_code?: string | null
  error_message?: string | null
  recorded_at?: number | string | null
  [key: string]: unknown
}

export type AIChannelInput = Omit<AIProviderChannel, 'secret_available' | 'config_error'> & {
  id: string
  name: string
}

export interface AIWorkerStatus {
  owner_id?: string
  lease_name?: string
  healthy?: boolean
  available?: boolean
  [key: string]: unknown
}

export interface AIStatusResponse {
  success?: boolean
  runtime?: string
  providers?: AIProviderChannel[]
  capability_matrix?: Record<string, {
    provider?: string
    protocol?: string
    capabilities?: AIProviderCapabilities
    readiness?: AIProviderReadiness
    [key: string]: unknown
  }>
  worker?: AIWorkerStatus | Record<string, unknown>
  worker_enabled?: boolean
  decision_effect?: 'none' | string
  degradation_policy?: string
  [key: string]: unknown
}

export interface AIItemsResponse<T> {
  items: T[]
  [key: string]: unknown
}

export interface AIModelInfo {
  id: string
  model?: string
  provider?: string
  available?: boolean
  primary?: boolean
  [key: string]: unknown
}

export interface AISkillInfo {
  id: string
  name?: string
  description?: string
  kind?: string
  profiles?: string[]
  [key: string]: unknown
}

export interface AIContextSnapshot {
  market?: string
  instrument?: string
  symbol?: string
  as_of?: string
  blocks?: Record<string, unknown>
  evidence?: Array<Record<string, unknown>>
  quality_status?: string
  source?: string
  [key: string]: unknown
}

export interface AITaskInput {
  kind?: string
  profile?: string
  request?: Record<string, unknown>
  context?: AIContextSnapshot | Record<string, unknown>
  snapshot?: AIContextSnapshot | Record<string, unknown> | null
  idempotency_key?: string
  run_now?: boolean
  [key: string]: unknown
}

export interface AITask {
  id: string
  workspace_id?: string
  kind?: string
  profile?: string
  status: AITaskStatus
  request?: Record<string, unknown>
  context_hash?: string
  schema_version?: string
  idempotency_key?: string
  report_id?: string | null
  report?: AIReportRecord | AIReport | null
  cancel_requested?: boolean
  error?: Record<string, unknown> | string | null
  created_at?: string
  started_at?: string | null
  completed_at?: string | null
  [key: string]: unknown
}

export interface AITaskSubmitResponse {
  task: AITask
  created?: boolean
  execution?: 'inline' | 'worker' | string
  [key: string]: unknown
}

export interface AIListTasksOptions {
  status?: string
  limit?: number
}

export interface AIRoleOpinion {
  role: string
  conclusion: string
  evidence?: string[]
  risks?: string[]
  unknowns?: string[]
  confidence?: number | null
  [key: string]: unknown
}

export interface AISynthesis {
  summary: string
  common_evidence?: string[]
  disagreements?: string[]
  risks?: string[]
  next_checks?: string[]
  [key: string]: unknown
}

export interface AIReport {
  schema_version?: string
  profile?: string
  status?: 'complete' | 'partial' | 'degraded' | 'unavailable' | string
  authoritative?: false | boolean
  decision_effect?: 'none' | string
  market?: string
  instrument?: string
  context_hash?: string
  quality_status?: string
  opinions?: AIRoleOpinion[]
  synthesis?: AISynthesis | null
  limitations?: string[]
  provenance?: Record<string, unknown>
  diagnostics?: Array<Record<string, unknown>>
  core_conclusion?: DSACoreConclusion | null
  data_perspective?: DSADataPerspective | null
  intelligence?: DSAIntelligence | null
  battle_plan?: DSABattlePlan | null
  phase_decision?: DSAPhaseDecision | null
  signal_attribution?: DSASignalAttribution | null
  agent_disagreement_explanation?: DSAAgentDisagreementExplanation | null
  [key: string]: unknown
}

export interface DSAReviewOnlyBlock {
  review_only: true
  authority: 'human_review_only'
  [key: string]: unknown
}

export interface DSACoreConclusion extends DSAReviewOnlyBlock {
  one_sentence?: string | null
  signal_type?: string | null
  time_sensitivity?: string | null
  position_advice?: { no_position?: string | null; has_position?: string | null } | null
}

export interface DSADataPerspective extends DSAReviewOnlyBlock {
  trend_status?: Record<string, unknown> | null
  price_position?: Record<string, unknown> | null
  volume_analysis?: Record<string, unknown> | null
  chip_structure?: Record<string, unknown> | null
}

export interface DSAIntelligence extends DSAReviewOnlyBlock {
  latest_news?: string | null
  risk_alerts?: string[]
  positive_catalysts?: string[]
  earnings_outlook?: string | null
  sentiment_summary?: string | null
}

export interface DSABattlePlan extends DSAReviewOnlyBlock {
  sniper_points?: Record<string, unknown> | null
  position_strategy?: Record<string, unknown> | null
  action_checklist?: string[]
}

export interface DSAPhaseDecision extends DSAReviewOnlyBlock {
  phase_context?: Record<string, unknown>
  action_window?: string | null
  immediate_action?: string | null
  watch_conditions?: string[]
  next_check_time?: string | null
  confidence_reason?: string | null
  data_limitations?: string[]
}

export interface DSASignalAttribution extends DSAReviewOnlyBlock {
  technical_indicators?: number | string | null
  news_sentiment?: number | string | null
  fundamentals?: number | string | null
  market_conditions?: number | string | null
  strongest_bullish_signal?: string | null
  strongest_bearish_signal?: string | null
}

export interface DSAAgentDisagreementExplanation extends DSAReviewOnlyBlock {
  base_opinions?: Array<Record<string, unknown>>
  risk_control_summary?: string | null
  degraded_events?: string[]
  data_quality?: string | null
  decision_path?: string
}

export interface AIReportRecord {
  id?: string
  task_id?: string
  workspace_id?: string
  status?: string
  body?: AIReport
  context_hash?: string
  provenance?: Record<string, unknown>
  usage?: Record<string, unknown>
  diagnostics?: Array<Record<string, unknown>>
  created_at?: string
  [key: string]: unknown
}

export interface AIEvent {
  id?: number
  task_id?: string
  event_type?: string
  type?: string
  payload?: Record<string, unknown> | unknown
  created_at?: string
  message?: string
  error?: unknown
  [key: string]: unknown
}

export type RunFlowStatus = 'pending' | 'running' | 'success' | 'failed' | 'degraded' | 'fallback' | 'retry' | 'timeout' | 'cancel_requested' | 'cancelled' | 'skipped' | 'unknown' | string
export type RunFlowSeverity = 'info' | 'success' | 'warning' | 'danger' | string

export interface RunFlowLane { id: string; label: string; order: number }
export interface RunFlowNode {
  id: string
  lane: string
  kind: string
  label: string
  status: RunFlowStatus
  provider?: string | null
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  attempts?: number | null
  message?: string | null
  metadata?: Record<string, unknown>
}
export interface RunFlowEdge {
  id: string
  from: string
  to: string
  kind: string
  status: RunFlowStatus
  label?: string | null
  message?: string | null
  metadata?: Record<string, unknown>
}
export interface RunFlowEvent {
  id: string
  timestamp?: string | null
  severity: RunFlowSeverity
  type: string
  node_id?: string | null
  title: string
  message?: string | null
  metadata?: Record<string, unknown>
}
export interface RunFlowSummary {
  elapsed_ms?: number | null
  bottleneck_node_id?: string | null
  failed_attempts: number
  fallback_count: number
  retry_count: number
  model?: string | null
  data_source_count: number
  event_count: number
}
export interface RunFlowSnapshot {
  task_id: string
  trace_id?: string | null
  instrument: string
  market?: string | null
  status: RunFlowStatus
  summary: RunFlowSummary
  lanes: RunFlowLane[]
  nodes: RunFlowNode[]
  edges: RunFlowEdge[]
  events: RunFlowEvent[]
  generated_at: string
  safety_boundary?: Record<string, unknown>
}

export interface AIEventQueryOptions {
  after_id?: number
  afterId?: number
}

export interface AIEventStreamOptions extends AIEventQueryOptions {
  signal?: AbortSignal
  onEvent?: (event: AIEvent) => void | Promise<void>
}

export interface AIChatPayload {
  message: string
  session_id?: string
  context?: AIContextSnapshot | Record<string, unknown>
  skills?: string[]
}

export interface AIChatMessage {
  id?: string
  session_id?: string
  role?: 'user' | 'assistant' | 'system' | string
  content?: string
  metadata?: Record<string, unknown>
  created_at?: string
  [key: string]: unknown
}

export interface AISession {
  id: string
  workspace_id?: string
  title?: string
  skills?: string[]
  message_count?: number
  messages?: AIChatMessage[]
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface AISessionInput {
  title?: string
  skills?: string[]
  session_id?: string
}

export interface AIArtifactRequest {
  context?: AIContextSnapshot | Record<string, unknown>
  [key: string]: unknown
}

export interface AIChatResponse {
  session?: AISession | null
  message?: AIChatMessage | null
  diagnostics?: Array<Record<string, unknown>> | Record<string, unknown>
  error?: Record<string, unknown> | string
  [key: string]: unknown
}

export interface AIStreamEvent<T = unknown> extends Record<string, unknown> {
  type?: string
  event_type?: string
  payload?: T
  result?: unknown
  data?: unknown
  error?: unknown
  message?: unknown
}

export type AIStreamTerminal = 'done' | 'error' | 'timeout' | null

export interface AIStreamResult<T = AIStreamEvent> {
  events: T[]
  terminal: AIStreamTerminal
  result?: unknown
  error?: unknown
}

export interface AIStreamOptions<T = AIStreamEvent> {
  signal?: AbortSignal
  onEvent?: (event: T) => void | Promise<void>
}

export interface AIChatStreamOptions extends AIStreamOptions<AIStreamEvent> {}

export interface AIListResponse<T> {
  items: T[]
  [key: string]: unknown
}

export interface AIDeleteSessionResponse {
  deleted: boolean
  [key: string]: unknown
}

function withQuery(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value))
  })
  const query = params.toString()
  return query ? `${path}${path.includes('?') ? '&' : '?'}${query}` : path
}

export function isAbortError(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && 'name' in error && (error as { name?: unknown }).name === 'AbortError')
}

/** Parse the JSON payload carried by one SSE data field. */
export function parseAiSseData(data: string): AIStreamEvent | null {
  const raw = String(data || '').trim()
  if (!raw) return null
  if (raw === '[DONE]' || raw.toLowerCase() === 'done') return { type: 'done' }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { type: 'error', error: 'invalid_sse_json', data: raw }
  }

  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    return parsed as AIStreamEvent
  }
  if (typeof parsed === 'string' && ['done', 'error', 'timeout'].includes(parsed.toLowerCase())) {
    return { type: parsed.toLowerCase() }
  }
  return { type: 'message', data: parsed }
}

// Upper-case alias keeps the helper discoverable for callers using SSE terminology.
export const parseSSEData = parseAiSseData

function parseSseFrame(frame: string): AIStreamEvent | null {
  let eventName = ''
  const dataLines: string[] = []
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator >= 0 ? line.slice(0, separator) : line
    const value = separator >= 0 ? line.slice(separator + 1).replace(/^ /, '') : ''
    if (field === 'event') eventName = value
    if (field === 'data') dataLines.push(value)
  }
  const parsed = parseAiSseData(dataLines.join('\n'))
  if (!parsed && ['done', 'error', 'timeout'].includes(eventName.toLowerCase())) return { type: eventName }
  if (!parsed || !eventName || parsed.type || parsed.event_type) return parsed
  return { ...parsed, type: eventName }
}

function streamEventType(event: AIStreamEvent): string {
  return String(event.type || event.event_type || event.event || '').trim().toLowerCase()
}

function streamTerminal(event: AIStreamEvent): AIStreamTerminal {
  const type = streamEventType(event)
  return type === 'done' || type === 'error' || type === 'timeout' ? type : null
}

/** Consume a fetch Response carrying standard SSE frames. */
export async function consumeAiSse<T extends AIStreamEvent = AIStreamEvent>(
  response: Response,
  options: AIStreamOptions<T> = {},
): Promise<AIStreamResult<T>> {
  const events: T[] = []
  let terminal: AIStreamTerminal = null
  let result: unknown
  let error: unknown
  const body = response.body
  if (!body) return { events, terminal, result, error }

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = async (frame: string): Promise<boolean> => {
    const parsed = parseSseFrame(frame)
    if (!parsed) return false
    const event = parsed as T
    events.push(event)
    await options.onEvent?.(event)
    const currentTerminal = streamTerminal(parsed)
    if (!currentTerminal) return false
    terminal = currentTerminal
    if (currentTerminal === 'done') {
      result = parsed.result
      if (result === undefined && parsed.payload && typeof parsed.payload === 'object' && 'result' in parsed.payload) {
        result = (parsed.payload as Record<string, unknown>).result
      }
    } else {
      error = parsed.error ?? parsed.message ?? parsed.payload
    }
    return true
  }

  try {
    let finished = false
    while (!finished) {
      const chunk = await reader.read()
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done })
      let separatorIndex = -1
      let separatorLength = 0
      while ((separatorIndex = buffer.search(/\r?\n\r?\n/)) >= 0) {
        const separator = buffer.slice(separatorIndex).match(/^\r?\n\r?\n/)
        separatorLength = separator ? separator[0].length : 2
        const frame = buffer.slice(0, separatorIndex)
        buffer = buffer.slice(separatorIndex + separatorLength)
        if (await dispatch(frame)) {
          finished = true
          break
        }
      }
      if (chunk.done || finished) {
        if (!finished) {
          buffer += decoder.decode()
          if (buffer.trim()) await dispatch(buffer)
        }
        break
      }
    }
  } finally {
    reader.releaseLock()
  }

  return { events, terminal, result, error }
}

async function requestAiStream<T extends AIStreamEvent>(
  path: string,
  body: unknown,
  options: AIStreamOptions<T> = {},
  method: 'GET' | 'POST' = 'POST',
): Promise<AIStreamResult<T>> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      credentials: 'include',
      headers: { Accept: 'text/event-stream', ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}) },
      ...(method === 'POST' ? { body: JSON.stringify(body) } : {}),
      signal: options.signal,
    })
  } catch (error) {
    if (isAbortError(error)) throw error
    throw new ApiError(formatApiError(null), 0, error)
  }

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || ''
    const raw = await response.text()
    let payload: unknown = raw
    if (contentType.includes('json') || /^[\[{]/.test(raw.trim())) {
      try {
        payload = raw ? JSON.parse(raw) : null
      } catch {
        payload = raw
      }
    }
    throw new ApiError(formatApiError(payload, response.status), response.status, payload)
  }
  return consumeAiSse<T>(response, options)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    const headers = new Headers({
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    })
    new Headers(init?.headers).forEach((value, key) => headers.set(key, value))
    response = await fetch(path, {
      ...init,
      credentials: 'include',
      headers,
    })
  } catch (error) {
    if (isAbortError(error)) throw error
    throw new ApiError(formatApiError(null), 0, error)
  }

  const contentType = response.headers.get('content-type') || ''
  const raw = await response.text()
  let payload: unknown = raw
  if (contentType.includes('json') || /^[\[{]/.test(raw.trim())) {
    try {
      payload = raw ? JSON.parse(raw) : null
    } catch {
      payload = raw
    }
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/account/me')) {
      window.dispatchEvent(new CustomEvent('quant-auth-expired'))
    }
    throw new ApiError(formatApiError(payload, response.status), response.status, payload)
  }
  return payload as T
}

export const api = {
  accountMe() {
    return request<AccountState>('/api/account/me')
  },
  login(username: string, password: string) {
    return request<AccountState>('/api/account/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  },
  register(payload: RegisterPayload) {
    return request<AccountState>('/api/account/register', { method: 'POST', body: JSON.stringify(payload) })
  },
  logout() {
    return request<{ success?: boolean }>('/api/account/logout', { method: 'POST', body: JSON.stringify({}) })
  },
  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>, signal?: AbortSignal) {
    const url = params ? withQuery(path, params) : path
    return request<T>(url, signal ? { signal } : undefined)
  },
  post<T>(path: string, body: unknown, headers?: Record<string, string>) {
    return request<T>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: headers ? { ...headers, 'Content-Type': 'application/json' } : undefined
    })
  },
  waitDecisionCommand<T>(commandId: string, timeoutMs = 15000): Promise<DecisionCommand<T>> {
    const startedAt = Date.now()
    const poll = async (): Promise<DecisionCommand<T>> => {
      const command = await request<DecisionCommand<T>>(`/api/decisions/commands/${encodeURIComponent(commandId)}`)
      if (['completed', 'rejected', 'failed'].includes(command.status)) {
        if (command.status === 'failed') throw new ApiError(command.error || '决策命令执行失败', 500, command)
        return command
      }
      if (Date.now() - startedAt >= timeoutMs) return command
      await new Promise((resolve) => window.setTimeout(resolve, 250))
      return poll()
    }
    return poll()
  },
  delete<T>(path: string, headers?: Record<string, string>) {
    return request<T>(path, {
      method: 'DELETE',
      headers: headers ? { ...headers, 'Content-Type': 'application/json' } : undefined
    })
  },
  put<T>(path: string, body: unknown, headers?: Record<string, string>) {
    return request<T>(path, {
      method: 'PUT',
      body: JSON.stringify(body),
      headers: headers ? { ...headers, 'Content-Type': 'application/json' } : undefined
    })
  },
  health() {
    return request<DataHealth>('/api/datahub/health?fast=true')
  },
  watchlist() {
    return request<WatchlistItem[]>('/api/watchlist')
  },
  addWatchlist(code: string) {
    return request<Record<string, unknown>>('/api/watchlist', { method: 'POST', body: JSON.stringify({ code }) })
  },
  removeWatchlist(code: string) {
    return request<Record<string, unknown>>(`/api/watchlist/${encodeURIComponent(code)}`, { method: 'DELETE' })
  },
  decisionMatrix(scope = 'watchlist') {
    return request<DecisionMatrix>(`/api/datahub/decision-matrix?scope=${encodeURIComponent(scope)}&fast=true&limit=30`)
  },
  marketRadar(market = 'CN') {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/market/radar?fast=true&market=${encodeURIComponent(market)}`)
  },
  marketSnapshot(market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/snapshot?market=${encodeURIComponent(market)}&limit=50`, { signal })
  },
  marketBreadth(market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/breadth?market=${encodeURIComponent(market)}`, { signal })
  },
  marketSectors(fast = true, market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/sectors?type=industry&fast=${fast ? 'true' : 'false'}&market=${encodeURIComponent(market)}`, { signal })
  },
  marketHeatmap(fast = true, market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/heatmap?fast=${fast ? 'true' : 'false'}&market=${encodeURIComponent(market)}`, { signal })
  },
  marketHotspot(market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/hotspot?market=${encodeURIComponent(market)}`, { signal })
  },
  marketNews(market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/market/news?market=${encodeURIComponent(market)}`, { signal })
  },
  iwencai(query: string, market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>('/api/llm/iwencai', { method: 'POST', body: JSON.stringify({ query, market }), signal })
  },
  signalTop(limit = 20, market = 'CN', signal?: AbortSignal) {
    return request<Record<string, unknown>>(`/api/signals/top?limit=${limit}&market=${encodeURIComponent(market)}`, { signal })
  },
  signalHealth() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/signals/health?fast=true')
  },
  signalValidation() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/signals/validation')
  },
  stockQuote(code: string, market = 'CN') {
    return request<QuoteDetail>(marketPath(`/api/stock/detail/${encodeURIComponent(code)}`, market))
  },
  stockKline(code: string, period = 'daily', limit = 120, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/kline/${encodeURIComponent(code)}?period=${encodeURIComponent(period)}&count=${limit}`, market))
  },
  stockTimeline(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/timeline/${encodeURIComponent(code)}`, market))
  },
  stockTimelineMulti(code: string, days = 5, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/timeline-multi/${encodeURIComponent(code)}?days=${days}`, market))
  },
  stockCapitalFlow(code: string, days = 20, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/capital-flow/${encodeURIComponent(code)}?days=${days}`, market))
  },
  stockOrderBook(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/order-book/${encodeURIComponent(code)}`, market))
  },
  stockProfitTrend(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/profit-trend/${encodeURIComponent(code)}`, market))
  },
  stockShareholders(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/shareholders/${encodeURIComponent(code)}`, market))
  },
  stockDividends(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/dividends/${encodeURIComponent(code)}`, market))
  },
  stockAnnouncements(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/announcements/${encodeURIComponent(code)}`, market))
  },
  stockIndustryComparison(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/industry-comparison/${encodeURIComponent(code)}`, market))
  },
  stockCompare(codes: string[], period = 'daily', count = 60, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/compare?codes=${encodeURIComponent(codes.join(','))}&period=${encodeURIComponent(period)}&count=${count}`, market))
  },
  stockDrawings(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/drawings/${encodeURIComponent(code)}`, market))
  },
  saveStockDrawing(code: string, body: unknown, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/drawings/${encodeURIComponent(code)}`, market), { method: 'POST', body: JSON.stringify(body) })
  },
  deleteStockDrawing(drawingId: number | string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/drawings/${encodeURIComponent(String(drawingId))}`, market), { method: 'DELETE' })
  },
  deleteAllStockDrawings(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/drawings/${encodeURIComponent(code)}/all`, market), { method: 'DELETE' })
  },
  stockMultiTimeframe(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/multi-timeframe/${encodeURIComponent(code)}`, market))
  },
  stockNews(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/news/${encodeURIComponent(code)}`, market))
  },
  stockNorthbound(code: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/northbound/${encodeURIComponent(code)}`, market))
  },
  stockChips(code: string, days = 120, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/chips/${encodeURIComponent(code)}?days=${days}`, market))
  },
  stockDragonTiger(code: string, days = 90, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/stock/dragon-tiger/${encodeURIComponent(code)}?days=${days}`, market))
  },
  stockReports(code: string, pageSize = 10, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/llm/reports/${encodeURIComponent(code)}?page_size=${pageSize}`, market))
  },
  analyzeReport(body: unknown, market = 'CN') {
    return request<Record<string, unknown>>(marketPath('/api/llm/reports/analyze', market), { method: 'POST', body: JSON.stringify(body) })
  },
  decisionResearch(market: string, symbol: string) {
    return request<DecisionResearch>(`/api/decisions/research/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`)
  },
  aiStatus() {
    return request<AIStatusResponse>('/api/ai/status')
  },
  aiChannels() {
    return request<AIItemsResponse<AIProviderChannel>>('/api/ai/channels')
  },
  saveAiChannel(channelOrId: AIChannelInput | string, maybeChannel?: AIChannelInput | string) {
    let channel: AIChannelInput
    let channelId = ''
    if (typeof channelOrId === 'string') {
      channelId = channelOrId
      if (!maybeChannel || typeof maybeChannel === 'string') throw new TypeError('AI channel payload is required')
      channel = maybeChannel
    } else {
      channel = channelOrId
      if (typeof maybeChannel === 'string') channelId = maybeChannel
    }
    const path = channelId ? `/api/ai/channels/${encodeURIComponent(channelId)}` : '/api/ai/channels'
    return request<AIItemsResponse<AIProviderChannel>>(path, {
      method: channelId ? 'PUT' : 'POST',
      body: JSON.stringify(channel),
    })
  },
  aiModels() {
    return request<AIItemsResponse<AIModelInfo>>('/api/ai/models')
  },
  aiSkills() {
    return request<AIItemsResponse<AISkillInfo>>('/api/ai/skills')
  },
  aiTasks(options: AIListTasksOptions | string = {}, limit?: number) {
    const query = typeof options === 'string' ? { status: options, limit } : options
    return request<AIItemsResponse<AITask>>(withQuery('/api/ai/tasks', {
      status: query.status,
      limit: query.limit,
    }))
  },
  createAiTask(payload: AITaskInput) {
    return request<AITaskSubmitResponse>('/api/ai/tasks', { method: 'POST', body: JSON.stringify(payload) })
  },
  runAiTask(taskId: string) {
    return request<AITask>(`/api/ai/tasks/${encodeURIComponent(taskId)}/run`, { method: 'POST' })
  },
  cancelAiTask(taskId: string) {
    return request<AITask>(`/api/ai/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
  },
  aiTask(taskId: string) {
    return request<AITask>(`/api/ai/tasks/${encodeURIComponent(taskId)}`)
  },
  aiTaskEvents(taskId: string, options: AIEventQueryOptions | number = {}) {
    const afterId = typeof options === 'number' ? options : (options.after_id ?? options.afterId)
    return request<AIItemsResponse<AIEvent>>(withQuery(`/api/ai/tasks/${encodeURIComponent(taskId)}/events`, {
      after_id: afterId,
    }))
  },
  aiTaskEventsStream(taskId: string, options: AIEventStreamOptions = {}) {
    const afterId = options.after_id ?? options.afterId
    return requestAiStream<AIEvent>(withQuery(`/api/ai/tasks/${encodeURIComponent(taskId)}/events`, {
      stream: true,
      after_id: afterId,
    }), undefined, options, 'GET')
  },
  aiTaskFlow(taskId: string) {
    return request<RunFlowSnapshot>(`/api/ai/tasks/${encodeURIComponent(taskId)}/flow`)
  },
  aiReports(limit?: number) {
    return request<AIItemsResponse<AIReportRecord>>(withQuery('/api/ai/reports', { limit }))
  },
  aiReport(reportId: string) {
    return request<AIReportRecord>(`/api/ai/reports/${encodeURIComponent(reportId)}`)
  },
  aiReportFlow(reportId: string) {
    return request<RunFlowSnapshot>(`/api/ai/reports/${encodeURIComponent(reportId)}/flow`)
  },
  aiSessions(limit?: number) {
    return request<AIItemsResponse<AISession>>(withQuery('/api/ai/chat/sessions', { limit }))
  },
  createAiSession(payload: AISessionInput = {}) {
    return request<AISession>('/api/ai/chat/sessions', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiSession(sessionId: string) {
    return request<AISession>(`/api/ai/chat/sessions/${encodeURIComponent(sessionId)}`)
  },
  updateAiSession(sessionId: string, payload: AISessionInput = {}) {
    return request<AISession>(`/api/ai/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'PUT', body: JSON.stringify(payload) })
  },
  deleteAiSession(sessionId: string) {
    return request<AIDeleteSessionResponse>(`/api/ai/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
  },
  aiChat(payload: AIChatPayload) {
    return request<AIChatResponse>('/api/ai/chat', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiChatStream(payload: AIChatPayload, options: AIChatStreamOptions = {}) {
    return requestAiStream<AIStreamEvent>('/api/ai/chat/stream', payload, options)
  },
  aiResearch(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/research', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiScreening(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/screening', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiInterpret(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/interpret', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiStrategy(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/strategy', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiDiagnose(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/diagnose', { method: 'POST', body: JSON.stringify(payload) })
  },
  aiReportAnalysis(payload: AIArtifactRequest = {}) {
    return request<AITaskSubmitResponse>('/api/ai/reports/analyze', { method: 'POST', body: JSON.stringify(payload) })
  },
  revokeShareLink(linkId: string) {
    return request<{ revoked: boolean }>(`/api/decisions/share-links/${encodeURIComponent(linkId)}`, { method: 'DELETE' })
  },
  valuation(code: string, market = 'CN') {
    return request<ApiEnvelope<Record<string, unknown>>>(marketPath(`/api/valuation/stock/${encodeURIComponent(code)}`, market)).then((payload) => {
      const body = payload as ApiEnvelope<Record<string, unknown>>
      const data = body?.data
      return data && typeof data === 'object' ? { ...body, ...data } : body
    })
  },
  valuationHealth() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/valuation/health')
  },
  valuationPeers(code: string, limit = 8, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/valuation/peers/${encodeURIComponent(code)}?limit=${limit}`, market))
  },
  alerts() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/alerts/rules')
  },
  alertConditions() {
    return request<{ conditions?: Record<string, string> }>('/api/alerts/conditions')
  },
  createAlertRule(body: unknown) {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/alerts/rules', { method: 'POST', body: JSON.stringify(body) })
  },
  updateAlertRule(ruleId: number | string, body: unknown) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/alerts/rules/${encodeURIComponent(String(ruleId))}`, { method: 'PUT', body: JSON.stringify(body) })
  },
  deleteAlertRule(ruleId: number | string) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/alerts/rules/${encodeURIComponent(String(ruleId))}`, { method: 'DELETE' })
  },
  reloadAlertRules() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/alerts/reload', { method: 'POST', body: JSON.stringify({}) })
  },
  alertHistory() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/alerts/history')
  },
  decisionMarkets() {
    return request<{ items: Array<Record<string, unknown>> }>('/api/decisions/markets')
  },
  strategies() {
    return request<unknown[]>('/api/strategy/list')
  },
  strategy(name: string) {
    return request<Record<string, unknown>>(`/api/strategy/${encodeURIComponent(name)}`)
  },
  createStrategy(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy', { method: 'POST', body: JSON.stringify(body) })
  },
  updateStrategy(name: string, body: unknown) {
    return request<Record<string, unknown>>(`/api/strategy/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify(body) })
  },
  deleteStrategy(name: string) {
    return request<Record<string, unknown>>(`/api/strategy/${encodeURIComponent(name)}`, { method: 'DELETE' })
  },
  resetStrategy(name: string) {
    return request<Record<string, unknown>>(`/api/strategy/${encodeURIComponent(name)}/reset`, { method: 'POST', body: JSON.stringify({}) })
  },
  strategyTemplate() {
    return request<{ code: string }>('/api/strategy/template')
  },
  validateStrategyCode(code: string) {
    return request<{ valid: boolean; error?: string }>('/api/strategy/validate-code', { method: 'POST', body: JSON.stringify({ code }) })
  },
  optimizeStrategy(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy/optimize', { method: 'POST', body: JSON.stringify(body) })
  },
  ensembleBacktest(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy/ensemble-backtest', { method: 'POST', body: JSON.stringify(body) })
  },
  exportStrategies(name = '') {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/system/strategies/export${name ? `?name=${encodeURIComponent(name)}` : ''}`)
  },
  importStrategies(body: unknown) {
    return request<Record<string, unknown>>('/api/system/strategies/import', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestStrategies() {
    return request<Array<Record<string, unknown>>>('/api/backtest/strategies')
  },
  backtestStocks(query = '') {
    return request<Array<Record<string, unknown>>>(`/api/backtest/stocks?q=${encodeURIComponent(query)}`)
  },
  backtestRun(body: unknown) {
    return request<Record<string, unknown>>('/api/backtest/run', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestMonteCarlo(body: unknown) {
    return request<Record<string, unknown>>('/api/backtest/monte-carlo', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestOutOfSample(body: unknown) {
    return request<Record<string, unknown>>('/api/backtest/out-of-sample', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestCompare(body: unknown) {
    return request<Array<Record<string, unknown>>>('/api/backtest/compare', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestMonthlyReturns(body: unknown) {
    return request<Array<Record<string, unknown>>>('/api/backtest/monthly-returns', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestDrawdown(body: unknown) {
    return request<Array<Record<string, unknown>>>('/api/backtest/drawdown', { method: 'POST', body: JSON.stringify(body) })
  },
  backtestAnalysis(path: string, body: unknown) {
    return request<Record<string, unknown>>(`/api/backtest/analysis/${path}`, { method: 'POST', body: JSON.stringify(body) })
  },
  backtestBenchmarks() {
    return request<Array<Record<string, unknown>>>('/api/backtest/benchmarks')
  },
  strategyVersions(name: string) {
    return request<unknown[]>(`/api/strategy-version/versions/${encodeURIComponent(name)}`)
  },
  saveStrategyVersion(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy-version/versions/save', { method: 'POST', body: JSON.stringify(body) })
  },
  rollbackStrategyVersion(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy-version/versions/rollback', { method: 'POST', body: JSON.stringify(body) })
  },
  strategyRecords(name = '') {
    return request<Array<Record<string, unknown>>>(`/api/strategy-version/records${name ? `?strategy_name=${encodeURIComponent(name)}` : ''}`)
  },
  saveStrategyRecord(body: unknown) {
    return request<Record<string, unknown>>('/api/strategy-version/records/save', { method: 'POST', body: JSON.stringify(body) })
  },
  deleteStrategyRecord(recordId: number | string) {
    return request<Record<string, unknown>>(`/api/strategy-version/records/${encodeURIComponent(String(recordId))}`, { method: 'DELETE' })
  },
  systemStatus() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/system/status')
  },
  markets() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/market-rules/list')
  },
  brokerTypes() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/broker/types')
  },
  brokerConfig() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/broker')
  },
  paperPositions() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/paper/positions')
  },
  paperRisk() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/paper/risk/events')
  },
  agents() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/agentic/agents')
  },
  agentOperations() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/agentic/operations')
  },
  dailyBriefs() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/agentic/briefs/daily')
  },
  factors() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/factor/list')
  },
  alphaHealth() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/alpha/health')
  },
  conversations() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/llm/conversations')
  },
  screenerPresets() {
    return request<{ presets?: Array<Record<string, unknown>> }>('/api/screener/presets')
  },
  screenerFields() {
    return request<{ fields?: Array<Record<string, unknown>> }>('/api/screener/fields')
  },
  runScreener(body: unknown) {
    return request<Record<string, unknown>>('/api/screener/run', { method: 'POST', body: JSON.stringify(body) })
  },
  runScreenerPreset(body: unknown) {
    return request<Record<string, unknown>>('/api/screener/run-preset', { method: 'POST', body: JSON.stringify(body) })
  },
  portfolioSnapshot() {
    return request<Record<string, unknown>>('/api/portfolio/snapshot')
  },
  portfolioRisk() {
    return request<Record<string, unknown>>('/api/portfolio/risk/advanced')
  },
  portfolioIndustryDistribution() {
    return request<Array<Record<string, unknown>>>('/api/portfolio/industry-distribution')
  },
  portfolioTrades() {
    return request<Record<string, unknown>>('/api/portfolio/trades')
  },
  closePortfolioPosition(body: unknown) {
    return request<Record<string, unknown>>('/api/portfolio/close', { method: 'POST', body: JSON.stringify(body) })
  },
  closeAllPortfolioPositions(body: unknown = {}) {
    return request<Record<string, unknown>>('/api/portfolio/close-all', { method: 'POST', body: JSON.stringify(body) })
  },
  updatePortfolioStopLoss(body: unknown) {
    return request<Record<string, unknown>>('/api/portfolio/stoploss', { method: 'POST', body: JSON.stringify(body) })
  },
  paperStatus() {
    return request<Record<string, unknown>>('/api/paper/status')
  },
  startPaper(body: unknown) {
    return request<Record<string, unknown>>('/api/paper/start', { method: 'POST', body: JSON.stringify(body) })
  },
  stopPaper() {
    return request<Record<string, unknown>>('/api/paper/stop', { method: 'POST', body: JSON.stringify({}) })
  },
  resetPaper() {
    return request<Record<string, unknown>>('/api/paper/reset', { method: 'POST', body: JSON.stringify({}) })
  },
  paperOrders(query = 'status=pending&page_size=100') {
    return request<Record<string, unknown>>(`/api/paper/orders?${query}`)
  },
  createPaperOrder(body: unknown) {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/paper/orders', { method: 'POST', body: JSON.stringify(body) })
  },
  cancelPaperOrder(orderId: string) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/paper/orders/${encodeURIComponent(orderId)}`, { method: 'DELETE' })
  },
  updatePaperPositionRisk(code: string, body: unknown) {
    return request<Record<string, unknown>>(`/api/paper/positions/${encodeURIComponent(code)}/stop-loss`, { method: 'PUT', body: JSON.stringify(body) })
  },
  closePaperPosition(code: string, volume?: number) {
    const query = volume ? `?volume=${encodeURIComponent(String(volume))}` : ''
    return request<Record<string, unknown>>(`/api/paper/positions/${encodeURIComponent(code)}/close${query}`, { method: 'POST', body: JSON.stringify({}) })
  },
  paperPerformance() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/paper/performance')
  },
  paperDailyPerformance(days = 60) {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>(`/api/paper/performance/daily?days=${days}`)
  },
  paperEquityCurve() {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>('/api/paper/equity-curve-v2')
  },
  paperDrawdown(days = 60) {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>(`/api/paper/drawdown?days=${days}`)
  },
  paperTrades(query = 'page=1&page_size=50') {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/paper/trades-v2?${query}`)
  },
  paperTradeStats(days = 30) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/paper/trades-v2/stats?days=${days}`)
  },
  paperRiskEvents() {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>('/api/paper/risk/events')
  },
  paperRiskRules() {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/paper/risk/rules')
  },
  agentHealth() {
    return request<Record<string, unknown>>('/api/agentic/health')
  },
  conditionalRules() {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>('/api/conditional-orders/rules')
  },
  conditionalEvents() {
    return request<ApiEnvelope<Array<Record<string, unknown>>>>('/api/conditional-orders/events')
  },
  createConditionalRule(body: unknown) {
    return request<ApiEnvelope<Record<string, unknown>>>('/api/conditional-orders/rules', { method: 'POST', body: JSON.stringify(body) })
  },
  updateConditionalRule(ruleId: number | string, body: unknown) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/conditional-orders/rules/${encodeURIComponent(String(ruleId))}`, { method: 'PUT', body: JSON.stringify(body) })
  },
  deleteConditionalRule(ruleId: number | string) {
    return request<ApiEnvelope<Record<string, unknown>>>(`/api/conditional-orders/rules/${encodeURIComponent(String(ruleId))}`, { method: 'DELETE' })
  },
  brokerTypeCatalog() {
    return request<Array<Record<string, unknown>>>('/api/broker/types')
  },
  brokerGatewayInfo() {
    return request<Record<string, unknown>>('/api/broker/gateway-info')
  },
  alphaModelStatus() {
    return request<Record<string, unknown>>('/api/alpha/model-status')
  },
  alphaTrainGlobal(body: unknown = {}) {
    return request<Record<string, unknown>>('/api/alpha/train-global', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaScreenAi(topN = 20) {
    return request<Record<string, unknown>>(`/api/alpha/screen-ai?top_n=${encodeURIComponent(String(topN))}`)
  },
  alphaFormulaCatalog() {
    return request<Record<string, unknown>>('/api/alpha/formula/catalog')
  },
  alphaPredict(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/predict', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaKlineSignals(query: string, market = 'CN') {
    return request<Record<string, unknown>>(marketPath(`/api/alpha/kline-signals?${query}`, market))
  },
  alphaPerformance(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/performance', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaFactorEval(body: unknown) {
    return request<Array<Record<string, unknown>>>('/api/alpha/factor-eval', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaFactorImportance(query: string) {
    return request<Array<Record<string, unknown>>>(`/api/alpha/factor-importance?${query}`)
  },
  alphaTrainingMetrics(query: string) {
    return request<Record<string, unknown>>(`/api/alpha/training-metrics?${query}`)
  },
  alphaShap(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/shap', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaWalkForward(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/walk-forward', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaCompare(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/compare', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaFactorCorrelation(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/factor-correlation', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaFactorDecay(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/factor-decay', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaMine(body: unknown) {
    return request<Array<Record<string, unknown>>>('/api/alpha/mine', { method: 'POST', body: JSON.stringify(body) })
  },
  alphaOptimize(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/optimize', { method: 'POST', body: JSON.stringify(body) })
  },
  formulaEvaluate(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/formula/evaluate', { method: 'POST', body: JSON.stringify(body) })
  },
  formulaScreen(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/formula/screen', { method: 'POST', body: JSON.stringify(body) })
  },
  basketPlan(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/basket/plan', { method: 'POST', body: JSON.stringify(body) })
  },
  basketBacktest(body: unknown) {
    return request<Record<string, unknown>>('/api/alpha/basket/backtest', { method: 'POST', body: JSON.stringify(body) })
  },
  factorList() {
    return request<Record<string, unknown>>('/api/factor/list')
  },
  factorAnalyze(body: unknown) {
    return request<Record<string, unknown>>('/api/factor/analyze', { method: 'POST', body: JSON.stringify(body) })
  },
  factorCorrelation(body: unknown) {
    return request<Record<string, unknown>>('/api/factor/correlation', { method: 'POST', body: JSON.stringify(body) })
  },
}
