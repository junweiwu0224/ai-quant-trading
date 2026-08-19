import { api } from './client'

export interface PortfolioOptimizationMethod {
  name: string
  label: string
  description: string
}

export interface PortfolioOptimizationRequest {
  codes: string[]
  start_date: string
  end_date: string
  method: string
  risk_free: number
}

export interface PortfolioOptimizationResult {
  success: boolean
  weights: Record<string, number>
  expected_return: number | null
  expected_volatility: number | null
  sharpe_ratio: number | null
  method: string
}

export async function getPortfolioMethods(): Promise<PortfolioOptimizationMethod[]> {
  const response = await api.get<{ methods: PortfolioOptimizationMethod[] }>('/api/portfolio-opt/methods')
  return response.methods || []
}

export async function optimizePortfolio(request: PortfolioOptimizationRequest): Promise<PortfolioOptimizationResult> {
  return api.post<PortfolioOptimizationResult>('/api/portfolio-opt/optimize', request)
}
