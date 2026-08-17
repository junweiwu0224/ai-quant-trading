/**
 * API client module exports
 *
 * Central export point for all API client functions and types.
 * Import from here for a clean, organized API surface.
 */

// Core client and error handling
export { api, ApiError, formatApiError } from './client'

// Type exports
export type * from './types'

// Decision API
export * from './decisions'

// Market data API
export * from './market'

// Research API
export * from './research'

// Paper trading API
export * from './paper'

// Portfolio optimization API
export * from './portfolio'

// Risk monitoring API
export * from './risk'

// Alpha factors API
export * from './alpha'

// Strategy workbench API
export * from './strategy'

// Agent operations API
export * from './agent'

// Conditional orders API (LIVE TRADING DISABLED)
export * from './orders'

// AI Runtime API
export * from './aiRuntime'

// Re-export commonly used types for convenience
export type {
  Decision,
  DecisionFilters,
  DecisionPortfolio,
  MarketData,
  Quote,
  MarketCode,
  DataHealth,
  DecisionMatrix
} from './types'
