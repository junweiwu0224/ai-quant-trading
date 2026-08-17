/**
 * Alpha Factors API - Mock implementation for factor research
 *
 * IMPORTANT: This is CLIENT-SIDE SIMULATION ONLY
 * All factor data is mocked for demonstration purposes
 */

import { api } from './client'

// ==================== Types ====================

export interface AlphaFactor {
  id: string
  name: string
  category: 'momentum' | 'value' | 'quality' | 'volatility' | 'size' | 'custom'
  description: string
  formula: string
  ic: number // Information Coefficient
  ir: number // Information Ratio
  sharpe: number
  status: 'active' | 'testing' | 'inactive'
  created_at: string
  updated_at: string
}

export interface FactorPerformance {
  factor_id: string
  period: string
  return: number
  sharpe: number
  max_drawdown: number
  win_rate: number
  avg_holding_days: number
}

export interface FactorBacktest {
  factor_id: string
  start_date: string
  end_date: string
  initial_capital: number
  final_value: number
  total_return: number
  annualized_return: number
  sharpe_ratio: number
  max_drawdown: number
  trades_count: number
}

// ==================== Mock Data ====================

const mockFactors: AlphaFactor[] = [
  {
    id: 'f1',
    name: '动量因子-20日',
    category: 'momentum',
    description: '基于20日收益率的动量因子，捕捉短期趋势',
    formula: '(close - close.shift(20)) / close.shift(20)',
    ic: 0.082,
    ir: 1.24,
    sharpe: 1.85,
    status: 'active',
    created_at: '2024-01-15T00:00:00Z',
    updated_at: '2024-08-10T00:00:00Z'
  },
  {
    id: 'f2',
    name: 'PE估值因子',
    category: 'value',
    description: '市盈率倒数，偏好低估值股票',
    formula: '1 / PE_TTM',
    ic: 0.065,
    ir: 0.98,
    sharpe: 1.52,
    status: 'active',
    created_at: '2024-01-20T00:00:00Z',
    updated_at: '2024-08-12T00:00:00Z'
  },
  {
    id: 'f3',
    name: 'ROE质量因子',
    category: 'quality',
    description: '净资产收益率，衡量盈利质量',
    formula: 'ROE_TTM',
    ic: 0.058,
    ir: 0.87,
    sharpe: 1.38,
    status: 'active',
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-08-11T00:00:00Z'
  },
  {
    id: 'f4',
    name: '波动率反转因子',
    category: 'volatility',
    description: '基于60日波动率的反转策略',
    formula: '-1 * rolling_std(returns, 60)',
    ic: 0.045,
    ir: 0.72,
    sharpe: 1.15,
    status: 'testing',
    created_at: '2024-03-10T00:00:00Z',
    updated_at: '2024-08-15T00:00:00Z'
  },
  {
    id: 'f5',
    name: '市值因子',
    category: 'size',
    description: '偏好小市值股票，捕捉小盘溢价',
    formula: '-1 * log(market_cap)',
    ic: 0.038,
    ir: 0.65,
    sharpe: 1.08,
    status: 'active',
    created_at: '2024-02-15T00:00:00Z',
    updated_at: '2024-08-09T00:00:00Z'
  },
  {
    id: 'f6',
    name: '成交量动量',
    category: 'momentum',
    description: '基于成交量变化的动量因子',
    formula: '(volume - volume.shift(10)) / volume.shift(10)',
    ic: 0.052,
    ir: 0.81,
    sharpe: 1.28,
    status: 'active',
    created_at: '2024-03-01T00:00:00Z',
    updated_at: '2024-08-13T00:00:00Z'
  },
  {
    id: 'f7',
    name: 'PB估值因子',
    category: 'value',
    description: '市净率倒数，偏好低PB股票',
    formula: '1 / PB',
    ic: 0.061,
    ir: 0.92,
    sharpe: 1.45,
    status: 'active',
    created_at: '2024-01-25T00:00:00Z',
    updated_at: '2024-08-14T00:00:00Z'
  },
  {
    id: 'f8',
    name: '毛利率因子',
    category: 'quality',
    description: '毛利率指标，衡量盈利能力',
    formula: 'gross_profit_margin',
    ic: 0.048,
    ir: 0.75,
    sharpe: 1.22,
    status: 'testing',
    created_at: '2024-04-01T00:00:00Z',
    updated_at: '2024-08-16T00:00:00Z'
  },
  {
    id: 'f9',
    name: '反转因子-5日',
    category: 'momentum',
    description: '短期反转因子，捕捉超跌反弹',
    formula: '-1 * (close - close.shift(5)) / close.shift(5)',
    ic: 0.042,
    ir: 0.68,
    sharpe: 1.12,
    status: 'inactive',
    created_at: '2024-03-20T00:00:00Z',
    updated_at: '2024-08-05T00:00:00Z'
  },
  {
    id: 'f10',
    name: '换手率因子',
    category: 'volatility',
    description: '基于换手率的流动性因子',
    formula: 'turnover_rate_20d',
    ic: 0.035,
    ir: 0.58,
    sharpe: 0.95,
    status: 'testing',
    created_at: '2024-04-10T00:00:00Z',
    updated_at: '2024-08-17T00:00:00Z'
  }
]

const mockPerformance: Record<string, FactorPerformance> = {
  f1: {
    factor_id: 'f1',
    period: '2023-01 to 2024-08',
    return: 28.5,
    sharpe: 1.85,
    max_drawdown: -12.3,
    win_rate: 58.2,
    avg_holding_days: 15
  },
  f2: {
    factor_id: 'f2',
    period: '2023-01 to 2024-08',
    return: 22.8,
    sharpe: 1.52,
    max_drawdown: -15.6,
    win_rate: 54.5,
    avg_holding_days: 22
  }
}

// ==================== API Functions ====================

export async function getAlphaFactors(): Promise<AlphaFactor[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<AlphaFactor[]>('/api/alpha/factors')

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 600))
  return mockFactors
}

export async function getFactorById(id: string): Promise<AlphaFactor | null> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<AlphaFactor>(`/api/alpha/factors/${id}`)

  await new Promise(resolve => setTimeout(resolve, 300))
  return mockFactors.find(f => f.id === id) || null
}

export async function getFactorPerformance(id: string): Promise<FactorPerformance | null> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<FactorPerformance>(`/api/alpha/factors/${id}/performance`)

  await new Promise(resolve => setTimeout(resolve, 400))
  return mockPerformance[id] || null
}

export async function runFactorBacktest(factorId: string, startDate: string, endDate: string): Promise<FactorBacktest> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<FactorBacktest>('/api/alpha/backtest', { factorId, startDate, endDate })

  await new Promise(resolve => setTimeout(resolve, 1000))

  // Mock backtest result
  const backtest: FactorBacktest = {
    factor_id: factorId,
    start_date: startDate,
    end_date: endDate,
    initial_capital: 1000000,
    final_value: 1285000,
    total_return: 28.5,
    annualized_return: 18.2,
    sharpe_ratio: 1.85,
    max_drawdown: -12.3,
    trades_count: 156
  }

  return backtest
}
