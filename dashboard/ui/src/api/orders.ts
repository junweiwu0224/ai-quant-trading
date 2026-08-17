/**
 * Conditional Orders API
 *
 * LIVE TRADING DISABLED
 * This API module is for UI demonstration only.
 * No real broker connections or order executions occur.
 */

import { api } from './client'
import type { ApiEnvelope } from './types'

export type ConditionType = 'price' | 'time' | 'technical' | 'composite'
export type OrderStatus = 'active' | 'triggered' | 'expired' | 'cancelled' | 'error'
export type OrderAction = 'buy' | 'sell'

export interface ConditionalOrder {
  id: string
  symbol: string
  name?: string
  conditionType: ConditionType
  condition: string
  triggerPrice?: number
  action: OrderAction
  quantity: number
  status: OrderStatus
  createdAt: string
  triggeredAt?: string
  executedAt?: string
  lastCheckAt?: string
  errorMessage?: string
  metadata?: Record<string, unknown>
}

export interface OrderExecution {
  orderId: string
  symbol: string
  action: OrderAction
  quantity: number
  price: number
  executedAt: string
  success: boolean
  message?: string
}

export interface OrderMonitoring {
  activeOrders: number
  lastCheckAt: string
  nextCheckAt: string
  status: 'running' | 'paused' | 'error'
}

/**
 * Fetch all conditional orders
 */
export async function getConditionalOrders(): Promise<ConditionalOrder[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/orders/conditional')

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 300))
  return mockConditionalOrders()
}

/**
 * Fetch order execution history
 */
export async function getOrderHistory(): Promise<OrderExecution[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/orders/history')

  await new Promise(resolve => setTimeout(resolve, 250))
  return mockOrderHistory()
}

/**
 * Get order monitoring status
 */
export async function getMonitoringStatus(): Promise<OrderMonitoring> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/orders/monitoring')

  await new Promise(resolve => setTimeout(resolve, 200))
  return mockMonitoringStatus()
}

/**
 * Create conditional order (DISABLED)
 */
export async function createConditionalOrder(order: Partial<ConditionalOrder>): Promise<ConditionalOrder> {
  // LIVE TRADING DISABLED - This function throws an error
  throw new Error('实盘交易功能已禁用，无法创建条件单')
}

/**
 * Cancel conditional order (DISABLED)
 */
export async function cancelConditionalOrder(orderId: string): Promise<void> {
  // LIVE TRADING DISABLED - This function throws an error
  throw new Error('实盘交易功能已禁用，无法取消条件单')
}

/**
 * Update conditional order (DISABLED)
 */
export async function updateConditionalOrder(orderId: string, updates: Partial<ConditionalOrder>): Promise<ConditionalOrder> {
  // LIVE TRADING DISABLED - This function throws an error
  throw new Error('实盘交易功能已禁用，无法修改条件单')
}

// ==================== Mock Data ====================

function mockConditionalOrders(): ConditionalOrder[] {
  return [
    {
      id: 'ord_001',
      symbol: '600519.SH',
      name: '贵州茅台',
      conditionType: 'price',
      condition: '价格 <= 1580',
      triggerPrice: 1580,
      action: 'buy',
      quantity: 100,
      status: 'active',
      createdAt: '2024-01-15T09:30:00Z',
      lastCheckAt: '2024-01-17T14:23:15Z',
    },
    {
      id: 'ord_002',
      symbol: '000858.SZ',
      name: '五粮液',
      conditionType: 'price',
      condition: '价格 >= 145',
      triggerPrice: 145,
      action: 'sell',
      quantity: 200,
      status: 'active',
      createdAt: '2024-01-14T10:15:00Z',
      lastCheckAt: '2024-01-17T14:23:15Z',
    },
    {
      id: 'ord_003',
      symbol: '000001.SZ',
      name: '平安银行',
      conditionType: 'technical',
      condition: 'RSI < 30',
      action: 'buy',
      quantity: 1000,
      status: 'triggered',
      createdAt: '2024-01-10T11:00:00Z',
      triggeredAt: '2024-01-16T10:45:00Z',
      executedAt: '2024-01-16T10:45:30Z',
      lastCheckAt: '2024-01-16T10:45:00Z',
    },
    {
      id: 'ord_004',
      symbol: '600036.SH',
      name: '招商银行',
      conditionType: 'time',
      condition: '每日 14:45 开盘价 > 35',
      action: 'sell',
      quantity: 500,
      status: 'expired',
      createdAt: '2024-01-05T09:00:00Z',
      lastCheckAt: '2024-01-15T14:45:00Z',
    },
    {
      id: 'ord_005',
      symbol: '601318.SH',
      name: '中国平安',
      conditionType: 'composite',
      condition: 'MA5 突破 MA20 且 成交量 > 均量',
      action: 'buy',
      quantity: 300,
      status: 'active',
      createdAt: '2024-01-12T13:20:00Z',
      lastCheckAt: '2024-01-17T14:23:15Z',
    },
    {
      id: 'ord_006',
      symbol: '300750.SZ',
      name: '宁德时代',
      conditionType: 'price',
      condition: '价格 <= 155',
      triggerPrice: 155,
      action: 'buy',
      quantity: 50,
      status: 'cancelled',
      createdAt: '2024-01-08T09:45:00Z',
      lastCheckAt: '2024-01-13T11:30:00Z',
    },
    {
      id: 'ord_007',
      symbol: '002594.SZ',
      name: '比亚迪',
      conditionType: 'price',
      condition: '价格 >= 220',
      triggerPrice: 220,
      action: 'sell',
      quantity: 100,
      status: 'error',
      createdAt: '2024-01-16T10:00:00Z',
      lastCheckAt: '2024-01-17T09:30:00Z',
      errorMessage: '数据源连接失败',
    },
  ]
}

function mockOrderHistory(): OrderExecution[] {
  return [
    {
      orderId: 'ord_003',
      symbol: '000001.SZ',
      action: 'buy',
      quantity: 1000,
      price: 11.25,
      executedAt: '2024-01-16T10:45:30Z',
      success: true,
      message: '条件触发，成功执行买入',
    },
    {
      orderId: 'ord_008',
      symbol: '601398.SH',
      action: 'sell',
      quantity: 2000,
      price: 5.18,
      executedAt: '2024-01-15T14:30:15Z',
      success: true,
      message: '价格触发条件满足，执行卖出',
    },
    {
      orderId: 'ord_009',
      symbol: '600519.SH',
      action: 'buy',
      quantity: 50,
      price: 1625.00,
      executedAt: '2024-01-12T10:15:00Z',
      success: false,
      message: '账户余额不足',
    },
  ]
}

function mockMonitoringStatus(): OrderMonitoring {
  return {
    activeOrders: 4,
    lastCheckAt: new Date(Date.now() - 125000).toISOString(),
    nextCheckAt: new Date(Date.now() + 175000).toISOString(),
    status: 'running',
  }
}
