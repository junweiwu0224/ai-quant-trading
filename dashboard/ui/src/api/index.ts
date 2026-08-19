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
