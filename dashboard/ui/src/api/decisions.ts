/**
 * Decision API client - handles all decision-related endpoints
 */

import { api } from './client'
import type {
  Decision,
  DecisionFilters,
  DecisionPortfolio,
  DecisionMember,
  DecisionVersion,
  DecisionReport,
  DecisionCommand,
  CreateDecisionRequest,
  UpdateDecisionRequest,
  CreatePortfolioRequest,
  AddMemberRequest,
  CreateVersionRequest,
  MarketInfo,
  ResearchData
} from './types'

// ==================== Portfolio Management ====================

export async function getMarkets(): Promise<{ items: MarketInfo[] }> {
  return api.get<{ items: MarketInfo[] }>('/api/decisions/markets')
}

export async function getPortfolios(market?: string): Promise<{ items: DecisionPortfolio[] }> {
  const params = market ? { market } : {}
  return api.get<{ items: DecisionPortfolio[] }>('/api/decisions/portfolios', params)
}

export async function getPortfolioById(portfolioId: string): Promise<{
  portfolio: DecisionPortfolio
  members: DecisionMember[]
  version: DecisionVersion | null
  eligibility: Record<string, unknown>
}> {
  return api.get(`/api/decisions/portfolios/${encodeURIComponent(portfolioId)}`)
}

export async function createPortfolio(data: CreatePortfolioRequest): Promise<DecisionPortfolio> {
  return api.post<DecisionPortfolio>('/api/decisions/portfolios', data)
}

export async function addPortfolioMember(
  portfolioId: string,
  data: AddMemberRequest
): Promise<DecisionMember> {
  return api.post<DecisionMember>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/members`,
    data
  )
}

export async function removePortfolioMember(
  portfolioId: string,
  symbol: string
): Promise<{ removed: boolean; symbol: string }> {
  return api.delete(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/members/${encodeURIComponent(symbol)}`
  )
}

export async function createVersion(
  portfolioId: string,
  data: CreateVersionRequest
): Promise<DecisionVersion> {
  return api.post<DecisionVersion>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/versions`,
    data
  )
}

// ==================== Decision Commands ====================

export async function previewPortfolio(
  portfolioId: string,
  idempotencyKey?: string
): Promise<DecisionCommand> {
  return api.post<DecisionCommand>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/preview`,
    {},
    idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  )
}

export async function analyzePortfolio(
  portfolioId: string,
  idempotencyKey?: string
): Promise<DecisionCommand> {
  return api.post<DecisionCommand>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/analyze`,
    {},
    idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  )
}

export async function validatePortfolio(
  portfolioId: string,
  idempotencyKey?: string
): Promise<DecisionCommand> {
  return api.post<DecisionCommand>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/validate`,
    {},
    idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  )
}

export async function getCommandStatus(commandId: string): Promise<DecisionCommand> {
  return api.get<DecisionCommand>(`/api/decisions/commands/${encodeURIComponent(commandId)}`)
}

export async function enableAutoPush(
  portfolioId: string,
  idempotencyKey?: string
): Promise<DecisionCommand> {
  return api.post<DecisionCommand>(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/auto-push`,
    {},
    idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  )
}

export async function disableAutoPush(
  portfolioId: string,
  idempotencyKey?: string
): Promise<DecisionCommand> {
  return api.delete(
    `/api/decisions/portfolios/${encodeURIComponent(portfolioId)}/auto-push`,
    idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  )
}

// ==================== Reports ====================

export async function getReports(
  portfolioId?: string,
  limit: number = 50
): Promise<{ items: DecisionReport[] }> {
  const params: Record<string, string | number> = { limit }
  if (portfolioId) params.portfolio_id = portfolioId
  return api.get<{ items: DecisionReport[] }>('/api/decisions/reports', params)
}

export async function getReportById(reportId: string): Promise<DecisionReport> {
  return api.get<DecisionReport>(`/api/decisions/reports/${encodeURIComponent(reportId)}`)
}

export async function exportReport(
  reportId: string,
  format: 'json' | 'markdown' | 'pdf' = 'json'
): Promise<Blob> {
  const response = await fetch(
    `/api/decisions/reports/${encodeURIComponent(reportId)}/export?format=${format}`,
    {
      credentials: 'include',
      headers: { Accept: 'application/json, text/markdown, application/pdf' }
    }
  )
  if (!response.ok) {
    throw new Error(`导出报告失败: ${response.status}`)
  }
  return response.blob()
}

export async function shareReport(
  reportId: string,
  ttlDays: number = 7
): Promise<{ link: string; url: string }> {
  return api.post<{ link: string; url: string }>(
    `/api/decisions/reports/${encodeURIComponent(reportId)}/share?ttl_days=${ttlDays}`,
    {}
  )
}

// ==================== Research Data ====================

export async function getResearchData(market: string, symbol: string): Promise<ResearchData> {
  return api.get<ResearchData>(
    `/api/decisions/research/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`
  )
}

// ==================== Decision Status ====================

export async function getDecisionStatus(): Promise<{
  worker_enabled: boolean
  worker_automation_enabled: boolean
  worker_process_ready: boolean
  auto_push_enabled: boolean
  worker_readiness: Record<string, unknown>
  markets: MarketInfo[]
}> {
  return api.get('/api/decisions/status')
}

export async function getWorkerReadiness(): Promise<Record<string, unknown>> {
  return api.get('/api/decisions/worker/readiness')
}
