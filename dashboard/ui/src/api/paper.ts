/**
 * Paper Trading API - Mock implementation for simulated trading
 *
 * IMPORTANT: This is CLIENT-SIDE SIMULATION ONLY
 * All trades are virtual and do not involve real money or broker connections
 */

import { api } from './client'

// ==================== Types ====================

export interface PaperAccount {
  initial_capital: number
  current_value: number
  cash: number
  position_value: number
  profit_loss: number
  return_percent: number
  updated_at: string
}

export interface PaperHolding {
  symbol: string
  name: string
  shares: number
  cost_basis: number
  current_price: number
  profit_loss: number
  profit_loss_percent: number
  weight: number
}

export interface PaperTrade {
  id: string
  timestamp: string
  symbol: string
  action: 'buy' | 'sell'
  price: number
  shares: number
  status: 'completed' | 'pending' | 'failed'
  total_amount: number
}

export interface PaperTradeRequest {
  symbol: string
  action: 'buy' | 'sell'
  shares: number
}

// ==================== Mock Data ====================

const mockAccount: PaperAccount = {
  initial_capital: 1000000,
  current_value: 1085200,
  cash: 523400,
  position_value: 561800,
  profit_loss: 85200,
  return_percent: 8.52,
  updated_at: new Date().toISOString()
}

const mockHoldings: PaperHolding[] = [
  {
    symbol: '600519.SH',
    name: '贵州茅台',
    shares: 100,
    cost_basis: 1680.50,
    current_price: 1725.30,
    profit_loss: 4480,
    profit_loss_percent: 2.67,
    weight: 30.7
  },
  {
    symbol: '000858.SZ',
    name: '五粮液',
    shares: 500,
    cost_basis: 158.20,
    current_price: 162.40,
    profit_loss: 2100,
    profit_loss_percent: 2.66,
    weight: 14.5
  },
  {
    symbol: '601318.SH',
    name: '中国平安',
    shares: 1000,
    cost_basis: 45.80,
    current_price: 47.20,
    profit_loss: 1400,
    profit_loss_percent: 3.06,
    weight: 8.4
  }
]

const mockTrades: PaperTrade[] = [
  {
    id: 't1',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    symbol: '600519.SH',
    action: 'buy',
    price: 1725.30,
    shares: 10,
    status: 'completed',
    total_amount: 17253
  },
  {
    id: 't2',
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    symbol: '000858.SZ',
    action: 'sell',
    price: 162.40,
    shares: 50,
    status: 'completed',
    total_amount: 8120
  },
  {
    id: 't3',
    timestamp: new Date(Date.now() - 86400000).toISOString(),
    symbol: '601318.SH',
    action: 'buy',
    price: 47.20,
    shares: 200,
    status: 'completed',
    total_amount: 9440
  }
]

// ==================== API Functions ====================

export async function getPaperAccount(): Promise<PaperAccount> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<PaperAccount>('/api/paper/account')

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 500))
  return mockAccount
}

export async function getPaperHoldings(): Promise<PaperHolding[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<PaperHolding[]>('/api/paper/holdings')

  await new Promise(resolve => setTimeout(resolve, 400))
  return mockHoldings
}

export async function getPaperTrades(limit: number = 20): Promise<PaperTrade[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<PaperTrade[]>('/api/paper/trades', { limit: limit.toString() })

  await new Promise(resolve => setTimeout(resolve, 300))
  return mockTrades.slice(0, limit)
}

export async function createPaperTrade(request: PaperTradeRequest): Promise<PaperTrade> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<PaperTrade>('/api/paper/trade', request)

  // SAFETY: This is mock only - no real trading occurs
  await new Promise(resolve => setTimeout(resolve, 800))

  const trade: PaperTrade = {
    id: 't' + Math.random().toString(36).substring(7),
    timestamp: new Date().toISOString(),
    symbol: request.symbol,
    action: request.action,
    price: 100 + Math.random() * 50, // Mock price
    shares: request.shares,
    status: 'completed',
    total_amount: request.shares * (100 + Math.random() * 50)
  }

  return trade
}
