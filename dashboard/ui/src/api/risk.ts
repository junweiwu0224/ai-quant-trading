/**
 * Risk Monitoring API - Mock implementation
 */

import { api } from './client'

// ==================== Types ====================

export interface RiskDashboard {
  risk_score: number // 0-100, higher = more risk
  concentration_risk: number // 0-100
  volatility: number // percentage
  var_95: number // Value at Risk 95%
  liquidity_risk: 'low' | 'medium' | 'high'
  market_exposure: number // beta-weighted exposure
  updated_at: string
}

export interface AlertRule {
  id: string
  name: string
  condition: string
  status: 'active' | 'inactive' | 'triggered'
  trigger_count: number
  last_triggered?: string
  actions: string[]
}

export interface RiskBreakdown {
  category: string
  value: number
  percentage: number
  risk_level: 'low' | 'medium' | 'high'
}

export interface RiskHistoryPoint {
  date: string
  risk_score: number
  var_95: number
  volatility: number
}

export interface RiskMonitorData {
  dashboard: RiskDashboard
  alert_rules: AlertRule[]
  breakdowns: {
    by_sector: RiskBreakdown[]
    by_position: RiskBreakdown[]
  }
  history: RiskHistoryPoint[]
}

// ==================== Mock Data ====================

const mockRiskData: RiskMonitorData = {
  dashboard: {
    risk_score: 42,
    concentration_risk: 58,
    volatility: 18.6,
    var_95: -8200,
    liquidity_risk: 'low',
    market_exposure: 0.92,
    updated_at: new Date().toISOString()
  },
  alert_rules: [
    {
      id: 'r1',
      name: '单日跌幅预警',
      condition: '单日组合跌幅 > 5%',
      status: 'active',
      trigger_count: 3,
      last_triggered: new Date(Date.now() - 86400000 * 7).toISOString(),
      actions: ['邮件通知', '短信通知']
    },
    {
      id: 'r2',
      name: '集中度预警',
      condition: '单一持仓权重 > 30%',
      status: 'triggered',
      trigger_count: 1,
      last_triggered: new Date(Date.now() - 3600000).toISOString(),
      actions: ['站内通知']
    },
    {
      id: 'r3',
      name: 'VaR 超限预警',
      condition: 'VaR(95%) < -10000',
      status: 'active',
      trigger_count: 0,
      actions: ['邮件通知', '微信通知']
    },
    {
      id: 'r4',
      name: '波动率预警',
      condition: '30日波动率 > 25%',
      status: 'inactive',
      trigger_count: 2,
      last_triggered: new Date(Date.now() - 86400000 * 30).toISOString(),
      actions: ['站内通知']
    }
  ],
  breakdowns: {
    by_sector: [
      { category: '消费', value: 254730, percentage: 45.3, risk_level: 'high' },
      { category: '金融', value: 104440, percentage: 18.6, risk_level: 'low' },
      { category: '制造', value: 71840, percentage: 12.8, risk_level: 'medium' },
      { category: '科技', value: 56240, percentage: 10.0, risk_level: 'medium' },
      { category: '其他', value: 74550, percentage: 13.3, risk_level: 'low' }
    ],
    by_position: [
      { category: '600519.SH', value: 172530, percentage: 30.7, risk_level: 'high' },
      { category: '000858.SZ', value: 81200, percentage: 14.5, risk_level: 'medium' },
      { category: '000333.SZ', value: 71840, percentage: 12.8, risk_level: 'medium' },
      { category: '600036.SH', value: 57240, percentage: 10.2, risk_level: 'low' },
      { category: '601318.SH', value: 47200, percentage: 8.4, risk_level: 'low' }
    ]
  },
  history: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (29 - i) * 86400000).toISOString().split('T')[0],
    risk_score: 35 + Math.random() * 20,
    var_95: -7000 - Math.random() * 3000,
    volatility: 15 + Math.random() * 8
  }))
}

// ==================== API Functions ====================

export async function getRiskMonitor(): Promise<RiskMonitorData> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<RiskMonitorData>('/api/risk/monitor')

  await new Promise(resolve => setTimeout(resolve, 550))
  return mockRiskData
}

export async function createAlertRule(
  rule: Omit<AlertRule, 'id' | 'trigger_count' | 'last_triggered'>
): Promise<AlertRule> {
  // TODO: Replace with real API call when backend is ready
  // return api.post<AlertRule>('/api/risk/alerts', rule)

  await new Promise(resolve => setTimeout(resolve, 400))
  return {
    ...rule,
    id: 'r' + Math.random().toString(36).substring(7),
    trigger_count: 0
  }
}

export async function updateAlertRule(
  id: string,
  updates: Partial<AlertRule>
): Promise<AlertRule> {
  // TODO: Replace with real API call when backend is ready
  // return api.patch<AlertRule>(`/api/risk/alerts/${id}`, updates)

  await new Promise(resolve => setTimeout(resolve, 400))
  const existing = mockRiskData.alert_rules.find(r => r.id === id)
  if (!existing) throw new Error('Alert rule not found')
  return { ...existing, ...updates }
}
