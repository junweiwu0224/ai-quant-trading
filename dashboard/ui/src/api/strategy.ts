/**
 * Strategy API - Mock implementation for strategy workbench
 *
 * IMPORTANT: This is CLIENT-SIDE SIMULATION ONLY
 * All strategy data is mocked for demonstration purposes
 */

import { api } from './client'

// ==================== Types ====================

export interface Strategy {
  id: string
  name: string
  type: 'momentum' | 'mean_reversion' | 'arbitrage' | 'ml_based' | 'custom'
  description: string
  code: string
  status: 'active' | 'draft' | 'archived'
  created_at: string
  updated_at: string
  last_backtest?: string
}

export interface BacktestConfig {
  strategy_id: string
  start_date: string
  end_date: string
  initial_capital: number
  commission_rate: number
  slippage_rate: number
  benchmark?: string
}

export interface StrategyBacktestResult {
  strategy_id: string
  config: BacktestConfig
  metrics: {
    total_return: number
    annualized_return: number
    sharpe_ratio: number
    max_drawdown: number
    win_rate: number
    profit_factor: number
    total_trades: number
  }
  equity_curve: Array<{ date: string; value: number }>
  completed_at: string
}

// ==================== Mock Data ====================

const mockStrategies: Strategy[] = [
  {
    id: 's1',
    name: '双均线策略',
    type: 'momentum',
    description: '基于5日和20日均线的经典趋势跟踪策略',
    code: `# 双均线策略
def initialize(context):
    context.short_window = 5
    context.long_window = 20
    context.symbol = '000300.SH'

def handle_data(context, data):
    short_ma = data.history(context.symbol, 'close', context.short_window).mean()
    long_ma = data.history(context.symbol, 'close', context.long_window).mean()

    current_position = context.portfolio.positions.get(context.symbol, 0)

    if short_ma > long_ma and current_position == 0:
        order_target_percent(context.symbol, 1.0)
    elif short_ma < long_ma and current_position > 0:
        order_target_percent(context.symbol, 0)`,
    status: 'active',
    created_at: '2024-01-15T00:00:00Z',
    updated_at: '2024-08-10T00:00:00Z',
    last_backtest: '2024-08-10T15:30:00Z'
  },
  {
    id: 's2',
    name: '均值回归策略',
    type: 'mean_reversion',
    description: '基于布林带的均值回归策略',
    code: `# 布林带均值回归策略
def initialize(context):
    context.window = 20
    context.num_std = 2
    context.symbol = '000300.SH'

def handle_data(context, data):
    prices = data.history(context.symbol, 'close', context.window)
    mean = prices.mean()
    std = prices.std()

    upper_band = mean + context.num_std * std
    lower_band = mean - context.num_std * std
    current_price = data.current(context.symbol, 'close')

    if current_price < lower_band:
        order_target_percent(context.symbol, 1.0)
    elif current_price > upper_band:
        order_target_percent(context.symbol, 0)`,
    status: 'active',
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-08-12T00:00:00Z',
    last_backtest: '2024-08-12T10:20:00Z'
  },
  {
    id: 's3',
    name: 'RSI超买超卖',
    type: 'mean_reversion',
    description: '基于RSI指标的反转策略',
    code: `# RSI策略
def initialize(context):
    context.rsi_period = 14
    context.oversold = 30
    context.overbought = 70
    context.symbol = '000300.SH'

def handle_data(context, data):
    rsi = calculate_rsi(data, context.symbol, context.rsi_period)
    current_position = context.portfolio.positions.get(context.symbol, 0)

    if rsi < context.oversold and current_position == 0:
        order_target_percent(context.symbol, 1.0)
    elif rsi > context.overbought and current_position > 0:
        order_target_percent(context.symbol, 0)`,
    status: 'draft',
    created_at: '2024-03-10T00:00:00Z',
    updated_at: '2024-08-15T00:00:00Z'
  },
  {
    id: 's4',
    name: '多因子选股',
    type: 'ml_based',
    description: '结合动量、价值、质量因子的机器学习选股策略',
    code: `# 多因子ML策略
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def initialize(context):
    context.model = RandomForestClassifier(n_estimators=100)
    context.factors = ['momentum_20d', 'pe_ratio', 'roe']
    context.rebalance_days = 20

def handle_data(context, data):
    if context.trading_day % context.rebalance_days != 0:
        return

    # 获取因子数据
    factor_data = get_factor_data(data, context.factors)

    # 预测
    predictions = context.model.predict_proba(factor_data)

    # 选择top 10股票
    top_stocks = predictions.argsort()[-10:]

    # 等权重配置
    for symbol in top_stocks:
        order_target_percent(symbol, 0.1)`,
    status: 'draft',
    created_at: '2024-04-05T00:00:00Z',
    updated_at: '2024-08-16T00:00:00Z'
  },
  {
    id: 's5',
    name: '网格交易策略',
    type: 'arbitrage',
    description: '在价格区间内设置网格，低买高卖',
    code: `# 网格交易策略
def initialize(context):
    context.symbol = '000300.SH'
    context.grid_size = 0.02  # 2%网格
    context.num_grids = 10
    context.base_price = None

def handle_data(context, data):
    current_price = data.current(context.symbol, 'close')

    if context.base_price is None:
        context.base_price = current_price

    # 计算当前所在网格
    price_change = (current_price - context.base_price) / context.base_price
    grid_level = int(price_change / context.grid_size)

    # 网格交易逻辑
    target_position = 0.5 - grid_level * 0.05
    target_position = max(0, min(1.0, target_position))

    order_target_percent(context.symbol, target_position)`,
    status: 'archived',
    created_at: '2024-02-20T00:00:00Z',
    updated_at: '2024-07-30T00:00:00Z',
    last_backtest: '2024-07-30T14:00:00Z'
  }
]

const mockBacktestResult: StrategyBacktestResult = {
  strategy_id: 's1',
  config: {
    strategy_id: 's1',
    start_date: '2023-01-01',
    end_date: '2024-08-17',
    initial_capital: 1000000,
    commission_rate: 0.0003,
    slippage_rate: 0.0001,
    benchmark: '000300.SH'
  },
  metrics: {
    total_return: 32.5,
    annualized_return: 19.8,
    sharpe_ratio: 1.65,
    max_drawdown: -15.2,
    win_rate: 56.8,
    profit_factor: 1.82,
    total_trades: 45
  },
  equity_curve: [
    { date: '2023-01-01', value: 1000000 },
    { date: '2023-03-01', value: 1050000 },
    { date: '2023-06-01', value: 1120000 },
    { date: '2023-09-01', value: 1180000 },
    { date: '2023-12-01', value: 1250000 },
    { date: '2024-03-01', value: 1280000 },
    { date: '2024-06-01', value: 1310000 },
    { date: '2024-08-17', value: 1325000 }
  ],
  completed_at: new Date().toISOString()
}

// ==================== API Functions ====================

export async function getStrategies(): Promise<Strategy[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<Strategy[]>('/api/strategy/list')

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 500))
  return mockStrategies
}

export async function getStrategyById(id: string): Promise<Strategy | null> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<Strategy>(`/api/strategy/${id}`)

  await new Promise(resolve => setTimeout(resolve, 300))
  return mockStrategies.find(s => s.id === id) || null
}

export async function createStrategy(strategy: Omit<Strategy, 'id' | 'created_at' | 'updated_at'>): Promise<Strategy> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<Strategy>('/api/strategy/create', strategy)

  await new Promise(resolve => setTimeout(resolve, 800))

  const newStrategy: Strategy = {
    ...strategy,
    id: 's' + Math.random().toString(36).substring(7),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }

  return newStrategy
}

export async function runStrategyBacktest(config: BacktestConfig): Promise<StrategyBacktestResult> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<StrategyBacktestResult>('/api/strategy/backtest', config)

  await new Promise(resolve => setTimeout(resolve, 2000))

  return {
    ...mockBacktestResult,
    strategy_id: config.strategy_id,
    config
  }
}
