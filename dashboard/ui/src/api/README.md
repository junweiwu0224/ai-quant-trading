# API Client Module

Comprehensive TypeScript API client for the AI Quant Trading platform backend.

## Overview

This module provides a complete, type-safe API client layer that encapsulates all backend endpoints with proper error handling, TypeScript types, and integration with Pinia stores.

## Architecture

```
src/api/
├── client.ts      # Core HTTP client with error handling
├── types.ts       # Shared TypeScript type definitions
├── decisions.ts   # Decision and portfolio management
├── market.ts      # Market data and quotes
├── research.ts    # Research, analysis, and backtesting
└── index.ts       # Central export point
```

## Core Features

### 1. Enhanced Error Handling

The `ApiError` class provides structured error information:

```typescript
import { ApiError, formatApiError } from '@/api'

try {
  await someApiCall()
} catch (err) {
  if (err instanceof ApiError) {
    console.error(`Status: ${err.status}`)
    console.error(`Message: ${err.message}`)
    console.error(`Payload:`, err.payload)
  }
}
```

### 2. Type-Safe Request/Response

All API functions are fully typed with TypeScript interfaces:

```typescript
import { getStockQuote, type Quote, type MarketCode } from '@/api'

const quote: Quote = await getStockQuote('600519', 'CN')
```

### 3. Automatic Query String Building

The `api.get()` method automatically constructs query strings from objects:

```typescript
// Automatically builds: /api/datahub/health?fast=true
await api.get('/api/datahub/health', { fast: true })
```

### 4. Retry and Timeout Support

Built-in support for request timeouts and retries (configurable):

```typescript
// The waitDecisionCommand helper includes polling with timeout
await api.waitDecisionCommand<Result>(commandId, 15000)
```

## Module Reference

### `client.ts` - Core Client

**Base API Object:**

```typescript
api.get<T>(path: string, params?: Record<string, any>): Promise<T>
api.post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T>
api.put<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T>
api.delete<T>(path: string, headers?: Record<string, string>): Promise<T>
```

**Account Management:**

```typescript
api.accountMe(): Promise<AccountState>
api.login(username: string, password: string): Promise<AccountState>
api.register(payload: RegisterPayload): Promise<AccountState>
api.logout(): Promise<{ success?: boolean }>
```

**Legacy Stock Methods** (use market.ts exports instead):

- `api.stockQuote(code, market)`
- `api.stockKline(code, period, limit, market)`
- `api.stockTimeline(code, market)`
- etc.

### `decisions.ts` - Decision Management

**Portfolio Operations:**

```typescript
getMarkets(): Promise<{ items: MarketInfo[] }>
getPortfolios(market?: string): Promise<{ items: DecisionPortfolio[] }>
getPortfolioById(portfolioId: string): Promise<{ portfolio, members, version, eligibility }>
createPortfolio(data: CreatePortfolioRequest): Promise<DecisionPortfolio>
addPortfolioMember(portfolioId: string, data: AddMemberRequest): Promise<DecisionMember>
removePortfolioMember(portfolioId: string, symbol: string): Promise<{ removed: boolean }>
```

**Decision Commands:**

```typescript
previewPortfolio(portfolioId: string, idempotencyKey?: string): Promise<DecisionCommand>
analyzePortfolio(portfolioId: string, idempotencyKey?: string): Promise<DecisionCommand>
validatePortfolio(portfolioId: string, idempotencyKey?: string): Promise<DecisionCommand>
getCommandStatus(commandId: string): Promise<DecisionCommand>
```

**Reports:**

```typescript
getReports(portfolioId?: string, limit?: number): Promise<{ items: DecisionReport[] }>
getReportById(reportId: string): Promise<DecisionReport>
exportReport(reportId: string, format: 'json' | 'markdown' | 'pdf'): Promise<Blob>
shareReport(reportId: string, ttlDays?: number): Promise<{ link: string; url: string }>
```

**Research Data:**

```typescript
getResearchData(market: string, symbol: string): Promise<ResearchData>
```

### `market.ts` - Market Data

**Data Health:**

```typescript
getDataHealth(fast?: boolean): Promise<DataHealth>
```

**Decision Matrix:**

```typescript
getDecisionMatrix(params?: {
  scope?: 'watchlist' | 'codes' | 'signal' | 'qlib'
  codes?: string
  limit?: number
  fast?: boolean
  force_fallback?: boolean
  max_wait_sec?: number
}): Promise<DecisionMatrix>
```

**Stock Data:**

```typescript
getStockQuote(code: string, market?: MarketCode): Promise<Quote>
getStockKline(code: string, period?: string, count?: number, market?: MarketCode): Promise<Record<string, unknown>>
getStockTimeline(code: string, market?: MarketCode): Promise<Record<string, unknown>>
getStockCapitalFlow(code: string, days?: number, market?: MarketCode): Promise<Record<string, unknown>>
getStockNews(code: string, market?: MarketCode): Promise<Record<string, unknown>>
```

**Realtime Quotes:**

```typescript
getQuoteServiceStatus(): Promise<{ running: boolean; subscriptions: number; ... }>
subscribeQuotes(codes: string[]): Promise<{ message: string; total: number }>
unsubscribeQuotes(codes: string[]): Promise<{ message: string; total: number }>
```

**Market Overview:**

```typescript
getMarketRadar(): Promise<ApiEnvelope<Record<string, unknown>>>
getMarketBreadth(): Promise<Record<string, unknown>>
getMarketSectors(fast?: boolean): Promise<Record<string, unknown>>
getMarketHeatmap(fast?: boolean): Promise<Record<string, unknown>>
getMarketHotspot(): Promise<Record<string, unknown>>
getMarketNews(): Promise<Record<string, unknown>>
```

**Watchlist:**

```typescript
getWatchlist(): Promise<string[]>
addToWatchlist(code: string): Promise<Record<string, unknown>>
removeFromWatchlist(code: string): Promise<Record<string, unknown>>
```

### `research.ts` - Research & Analysis

**K-Line Data:**

```typescript
getKLineData(
  market: MarketCode,
  symbol: string,
  period?: 'daily' | 'weekly' | 'monthly' | '1min' | '5min' | '15min' | '30min' | '60min',
  count?: number
): Promise<{ bars: KLineBar[] }>
```

**Technical Analysis:**

```typescript
getTechnicalIndicators(market: MarketCode, symbol: string): Promise<TechnicalIndicators>
getEvidence(market: MarketCode, symbol: string): Promise<{ evidence: Evidence[] }>
```

**Backtest Execution:**

```typescript
runBacktest(request: BacktestRequest): Promise<BacktestResult>
```

**Stock Analysis:**

```typescript
getStockMultiTimeframe(symbol: string, market?: MarketCode): Promise<Record<string, unknown>>
getStockChips(symbol: string, days?: number, market?: MarketCode): Promise<Record<string, unknown>>
getStockDragonTiger(symbol: string, days?: number, market?: MarketCode): Promise<Record<string, unknown>>
getStockIndustryComparison(symbol: string, market?: MarketCode): Promise<Record<string, unknown>>
```

### `types.ts` - Type Definitions

Key type exports:

```typescript
// Core types
export type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'
export interface ApiEnvelope<T = unknown>
export interface PaginatedResponse<T>

// Decision types
export interface Decision
export interface DecisionFilters
export interface DecisionPortfolio
export interface DecisionMember
export interface DecisionVersion
export interface DecisionReport
export interface DecisionCommand

// Market data types
export interface MarketData
export interface Quote
export interface MarketInfo
export interface DataHealth
export interface DecisionMatrix
export interface DecisionMatrixItem

// Research types
export interface KLineBar
export interface ResearchData
export interface TechnicalIndicators
export interface Evidence
export interface BacktestRequest
export interface BacktestResult
```

## Usage Examples

### Example 1: Fetch Decision Matrix

```typescript
import { getDecisionMatrix } from '@/api'

// Get watchlist with fast mode (skip external valuation)
const matrix = await getDecisionMatrix({
  scope: 'watchlist',
  fast: true,
  limit: 30
})

console.log(`Total stocks: ${matrix.summary.total}`)
console.log(`High score count: ${matrix.summary.high_score}`)

for (const item of matrix.items) {
  console.log(`${item.name}: ${item.decision_label} (${item.decision_score})`)
}
```

### Example 2: Create Portfolio and Analyze

```typescript
import { createPortfolio, addPortfolioMember, analyzePortfolio, getCommandStatus } from '@/api'

// Create portfolio
const portfolio = await createPortfolio({
  market: 'CN',
  name: 'My Research Portfolio'
})

// Add members
await addPortfolioMember(portfolio.id, { symbol: '600519', name: '贵州茅台' })
await addPortfolioMember(portfolio.id, { symbol: '000858', name: '五粮液' })

// Trigger analysis
const command = await analyzePortfolio(portfolio.id)

// Poll for completion
let status = command
while (status.status === 'queued' || status.status === 'running') {
  await new Promise(resolve => setTimeout(resolve, 1000))
  status = await getCommandStatus(command.id)
}

if (status.status === 'completed') {
  console.log('Analysis complete:', status.result)
}
```

### Example 3: Fetch K-Line Data and Technical Indicators

```typescript
import { getKLineData, getTechnicalIndicators } from '@/api'

const symbol = '600519'
const market = 'CN'

// Get daily K-line data
const { bars } = await getKLineData(market, symbol, 'daily', 120)
console.log(`Fetched ${bars.length} bars`)
console.log(`Latest close: ${bars[bars.length - 1].close}`)

// Get technical indicators
const indicators = await getTechnicalIndicators(market, symbol)
console.log(`MA20: ${indicators.ma20}`)
console.log(`MA60: ${indicators.ma60}`)
```

### Example 4: Real-time Quote Subscription

```typescript
import { subscribeQuotes, getQuoteServiceStatus } from '@/api'

// Subscribe to quotes
await subscribeQuotes(['600519', '000858', '000001'])

// Check service status
const status = await getQuoteServiceStatus()
console.log(`Quote service running: ${status.running}`)
console.log(`Active subscriptions: ${status.subscriptions}`)
```

### Example 5: Error Handling

```typescript
import { getStockQuote, ApiError, formatApiError } from '@/api'

try {
  const quote = await getStockQuote('INVALID_CODE', 'CN')
} catch (err) {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      console.error('Stock not found')
    } else if (err.status === 401) {
      console.error('Please log in')
      // Redirect to login
    } else {
      console.error(`API error: ${err.message}`)
    }
  } else {
    console.error('Unexpected error:', err)
  }
}
```

## Integration with Pinia Stores

The API client is designed to work seamlessly with Pinia stores. Stores handle state management, loading states, and error handling:

```typescript
// In a store
import { getDecisionMatrix } from '@/api/market'

export const useMarketStore = defineStore('market', () => {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const matrix = ref<DecisionMatrix | null>(null)

  async function fetchMatrix() {
    loading.value = true
    error.value = null
    try {
      matrix.value = await getDecisionMatrix({ scope: 'watchlist', fast: true })
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch matrix'
    } finally {
      loading.value = false
    }
  }

  return { loading, error, matrix, fetchMatrix }
})
```

## Backend Endpoint Mapping

| Frontend Module | Backend Router | FastAPI Path |
|----------------|----------------|--------------|
| `decisions.ts` | `routers/decisions.py` | `/api/decisions/*` |
| `market.ts` | `routers/datahub.py`, `routers/realtime_quotes.py` | `/api/datahub/*`, `/api/realtime/*` |
| `research.ts` | `routers/stock_detail.py` | `/api/stock/*` |
| `client.ts` (AI) | `routers/ai.py` | `/api/ai/*` |

## Notes

### Decision Creation

The backend uses a portfolio-based workflow for decisions. Direct decision CRUD is not supported. Instead:

- Create a portfolio
- Add members to the portfolio
- Run analysis commands
- Fetch generated reports

### Market Parameter

Most stock-related endpoints accept a `market` parameter. Default is `'CN'` (A-shares). Supported values:

- `'CN'` - China A-shares
- `'HK'` - Hong Kong
- `'US'` - United States
- `'JP'` - Japan
- `'KR'` - Korea
- `'TW'` - Taiwan

## Error Handling Strategy

1. **Network Errors**: Caught and wrapped in `ApiError` with status 0
2. **HTTP Errors**: Automatically parsed from response body and formatted
3. **401 Unauthorized**: Triggers global `quant-auth-expired` event
4. **Validation Errors**: FastAPI validation errors are automatically formatted

## Testing

To test API integration:

```bash
# 1. Start backend server
cd /path/to/project
python dashboard/app.py

# 2. Build frontend
cd dashboard/ui
npm run build

# 3. Run dev server
npm run dev
```

The frontend will proxy API requests to `http://localhost:8000` automatically via Vite config.

## Future Enhancements

- [ ] Request caching layer
- [ ] Optimistic updates
- [ ] Batch request support
- [ ] WebSocket integration for real-time updates
- [ ] Request deduplication
- [ ] Automatic retry with exponential backoff
