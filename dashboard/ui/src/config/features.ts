/**
 * Feature flags configuration
 * Centralized feature toggles for the application
 */

export const WARNINGS = {
  liveTradingDisabled: '实盘交易功能已禁用',
  platformPurpose: '本系统为研究与学习平台，不支持真实券商连接和实盘交易。',
  simulationOnly: '所有交易相关功能仅供模拟演示，不涉及真实资金。',
} as const
