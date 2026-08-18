import { api } from './client'

export interface PaperAccount {
  initial_capital?: number
  current_value?: number
  cash?: number
  position_value?: number
  profit_loss?: number
  return_percent?: number
  updated_at?: string
  [key: string]: unknown
}

export interface PaperHolding {
  symbol: string
  name?: string
  shares?: number
  cost_basis?: number
  current_price?: number
  profit_loss?: number
  profit_loss_percent?: number
  weight?: number
  [key: string]: unknown
}

export interface PaperTrade {
  id: string
  timestamp: string
  symbol: string
  action: 'buy' | 'sell'
  price?: number
  shares: number
  status: string
  total_amount?: number
  [key: string]: unknown
}

export interface PaperTradeRequest {
  symbol: string
  action: 'buy' | 'sell'
  shares: number
  strategyName?: string
  signalReason?: string
}

type Envelope<T> = { success?: boolean; data?: T; error?: string; message?: string }
function unwrap<T>(response: Envelope<T>): T {
  if (response.success === false) throw new Error(response.error || response.message || '模拟盘请求失败')
  if (response.data === undefined) throw new Error(response.error || '模拟盘没有返回数据')
  return response.data
}

export async function getPaperAccount(): Promise<PaperAccount> {
  const status = await api.paperStatus() as Record<string, any>
  const config = (status.config || {}) as Record<string, any>
  const initial = Number(config.initial_cash ?? config.initial_capital ?? 0)
  const equity = status.equity == null ? undefined : Number(status.equity)
  const cash = status.cash == null ? undefined : Number(status.cash)
  const positionValue = equity != null && cash != null ? equity - cash : undefined
  const performance = await api.paperPerformance().catch(() => null) as Envelope<Record<string, any>> | null
  const metrics = performance?.data || {}
  const currentValue = equity ?? Number(metrics.total_equity)
  const profitLoss = Number.isFinite(currentValue) && initial > 0 ? currentValue - initial : undefined
  return {
    initial_capital: initial,
    current_value: Number.isFinite(currentValue) ? currentValue : undefined,
    cash,
    position_value: positionValue,
    profit_loss: profitLoss,
    return_percent: profitLoss != null && initial > 0 ? profitLoss / initial * 100 : undefined,
    updated_at: new Date().toISOString(),
    running: Boolean(status.running),
    trade_count: status.trade_count,
  }
}

export async function getPaperHoldings(): Promise<PaperHolding[]> {
  const response = await api.get<Envelope<Array<Record<string, unknown>>>>('/api/paper/positions')
  return unwrap(response).map((position) => ({
    ...position,
    symbol: String(position.code || ''),
    shares: Number(position.volume || 0),
    cost_basis: Number(position.avg_price || 0),
    current_price: Number(position.current_price || 0),
    profit_loss: Number(position.unrealized_pnl || 0),
    profit_loss_percent: Number(position.unrealized_pnl_pct || 0),
  }))
}

export async function getPaperTrades(limit: number = 20): Promise<PaperTrade[]> {
  const response = await api.get<Envelope<{ items?: Array<Record<string, unknown>> }>>(`/api/paper/trades-v2?page=1&page_size=${Math.max(1, Math.min(500, limit))}`)
  return (unwrap(response).items || []).map((trade) => ({
    ...trade,
    id: String(trade.trade_id || trade.order_id || ''),
    timestamp: String(trade.created_at || ''),
    symbol: String(trade.code || ''),
    action: trade.direction === 'sell' || trade.direction === 'short' ? 'sell' : 'buy',
    price: trade.price == null ? undefined : Number(trade.price),
    shares: Number(trade.volume || 0),
    status: 'filled',
    total_amount: trade.price == null ? undefined : Number(trade.price) * Number(trade.volume || 0),
  }))
}

export async function createPaperTrade(request: PaperTradeRequest): Promise<PaperTrade> {
  if (!Number.isInteger(request.shares) || request.shares <= 0) throw new Error('交易数量必须是大于 0 的整数')
  const response = await api.post<Envelope<Record<string, unknown>>>('/api/paper/orders', {
    code: request.symbol.trim(),
    direction: request.action === 'buy' ? 'long' : 'short',
    order_type: 'market',
    volume: request.shares,
    strategy_name: request.strategyName || 'manual',
    signal_reason: request.signalReason || '研究工作流手动确认',
  })
  const order = unwrap(response)
  return {
    id: String(order.order_id || order.id || ''),
    timestamp: String(order.created_at || new Date().toISOString()),
    symbol: String(order.code || request.symbol),
    action: request.action,
    price: typeof order.filled_price === 'number' ? order.filled_price : undefined,
    shares: Number(order.volume || request.shares),
    status: String(order.status || 'pending'),
    total_amount: typeof order.filled_price === 'number' ? order.filled_price * Number(order.volume || request.shares) : undefined,
    raw: order,
  }
}
