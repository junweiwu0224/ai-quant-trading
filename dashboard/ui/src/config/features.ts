/**
 * Feature flags configuration
 * Centralized feature toggles for the application
 */

// LIVE TRADING DISABLED
// This platform is for research and learning purposes only.
// Real broker connections and live trading are permanently disabled.
export const LIVE_TRADING_ENABLED = false

export const FEATURES = {
  // Trading features
  liveTrading: LIVE_TRADING_ENABLED,
  brokerConnection: false,
  realMoneyTransactions: false,

  // Allowed features
  paperTrading: true,
  backtesting: true,
  research: true,
  simulation: true,
} as const

export const WARNINGS = {
  liveTradingDisabled: '实盘交易功能已禁用',
  platformPurpose: '本系统为研究与学习平台，不支持真实券商连接和实盘交易。',
  simulationOnly: '所有交易相关功能仅供模拟演示，不涉及真实资金。',
} as const
