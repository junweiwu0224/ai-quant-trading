/**
 * Portfolio Optimization API - Mock implementation
 */

import { api } from './client'

// ==================== Types ====================

export interface PortfolioPosition {
  symbol: string
  name: string
  weight: number
  value: number
  shares: number
}

export interface RiskMetrics {
  beta: number
  sharpe_ratio: number
  max_drawdown: number
  var_95: number
  volatility: number
  alpha: number
}

export interface OptimizationSuggestion {
  type: 'rebalance' | 'add' | 'reduce' | 'hold'
  symbol: string
  name: string
  current_weight: number
  suggested_weight: number
  reason: string
  priority: 'high' | 'medium' | 'low'
}

export interface CorrelationData {
  symbols: string[]
  matrix: number[][]
}

export interface PortfolioAnalysis {
  positions: PortfolioPosition[]
  risk_metrics: RiskMetrics
  suggestions: OptimizationSuggestion[]
  correlation: CorrelationData
  total_value: number
  updated_at: string
}

// ==================== Mock Data ====================

const mockAnalysis: PortfolioAnalysis = {
  positions: [
    { symbol: '600519.SH', name: '贵州茅台', weight: 30.7, value: 172530, shares: 100 },
    { symbol: '000858.SZ', name: '五粮液', weight: 14.5, value: 81200, shares: 500 },
    { symbol: '601318.SH', name: '中国平安', weight: 8.4, value: 47200, shares: 1000 },
    { symbol: '000333.SZ', name: '美的集团', weight: 12.8, value: 71840, shares: 800 },
    { symbol: '600036.SH', name: '招商银行', weight: 10.2, value: 57240, shares: 1500 }
  ],
  risk_metrics: {
    beta: 0.92,
    sharpe_ratio: 1.35,
    max_drawdown: -12.4,
    var_95: -8200,
    volatility: 18.6,
    alpha: 2.8
  },
  suggestions: [
    {
      type: 'reduce',
      symbol: '600519.SH',
      name: '贵州茅台',
      current_weight: 30.7,
      suggested_weight: 25.0,
      reason: '持仓过于集中，建议降低单一股票权重',
      priority: 'high'
    },
    {
      type: 'add',
      symbol: '300750.SZ',
      name: '宁德时代',
      current_weight: 0,
      suggested_weight: 8.0,
      reason: '增加新能源板块配置，优化行业分布',
      priority: 'medium'
    },
    {
      type: 'rebalance',
      symbol: '000858.SZ',
      name: '五粮液',
      current_weight: 14.5,
      suggested_weight: 12.0,
      reason: '白酒板块权重偏高，建议适当降低',
      priority: 'low'
    }
  ],
  correlation: {
    symbols: ['600519.SH', '000858.SZ', '601318.SH', '000333.SZ', '600036.SH'],
    matrix: [
      [1.00, 0.78, 0.32, 0.15, 0.28],
      [0.78, 1.00, 0.29, 0.18, 0.31],
      [0.32, 0.29, 1.00, 0.42, 0.65],
      [0.15, 0.18, 0.42, 1.00, 0.38],
      [0.28, 0.31, 0.65, 0.38, 1.00]
    ]
  },
  total_value: 561800,
  updated_at: new Date().toISOString()
}

// ==================== API Functions ====================

export async function getPortfolioAnalysis(): Promise<PortfolioAnalysis> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<PortfolioAnalysis>('/api/portfolio/analysis')

  await new Promise(resolve => setTimeout(resolve, 600))
  return mockAnalysis
}

export async function optimizePortfolio(
  constraints?: Record<string, unknown>
): Promise<OptimizationSuggestion[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<OptimizationSuggestion[]>('/api/portfolio/optimize', constraints)

  await new Promise(resolve => setTimeout(resolve, 800))
  return mockAnalysis.suggestions
}
