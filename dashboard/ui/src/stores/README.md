# Pinia Stores

This directory contains Pinia store modules for application-wide state management.

## Available Stores

### 1. Decision Store (`decision.ts`)
Manages trading decision data and CRUD operations.

**State:**
- `decisions`: Array of all decisions
- `currentDecision`: Active decision being viewed/edited
- `loading`: Boolean loading state
- `error`: Error message or null

**Actions:**
- `fetchDecisions(filters?)`: Load decision list with optional filters
- `fetchDecisionById(id)`: Load single decision details
- `createDecision(data)`: Create new decision
- `updateDecision(id, data)`: Update existing decision
- `deleteDecision(id)`: Remove decision
- `setCurrentDecision(decision)`: Set active decision
- `clearError()`: Clear error state

**Getters:**
- `recentDecisions`: Last 10 decisions sorted by date
- `decisionsBySymbol(symbol)`: Filter decisions by stock symbol
- `decisionsByMarket(market)`: Filter decisions by market
- `pendingDecisions`: All pending decisions

**Types:**
```typescript
interface Decision {
  id: string
  symbol: string
  market: string
  type: 'buy' | 'sell' | 'hold'
  confidence: number
  reasoning: string[]
  createdAt: string
  price?: number
  targetPrice?: number
  stopLoss?: number
  status?: 'pending' | 'executed' | 'cancelled'
}
```

### 2. Market Store (`market.ts`)
Manages market selection, stock symbols, and real-time market data.

**State:**
- `selectedMarket`: Current market (CN/HK/US/JP/KR/TW)
- `selectedSymbol`: Current stock symbol
- `marketData`: Map of symbol → market data
- `quotes`: Map of symbol → real-time quotes
- `loading`: Boolean loading state
- `error`: Error message or null

**Actions:**
- `setMarket(market)`: Change active market
- `setSymbol(symbol)`: Change active stock symbol
- `fetchMarketData(market, symbol)`: Load market data for symbol
- `fetchMultipleMarketData(market, symbols)`: Batch load market data
- `updateQuote(symbol, quote)`: Update real-time quote
- `updateMultipleQuotes(quotes)`: Batch update quotes
- `getMarketData(symbol)`: Get cached market data
- `getQuote(symbol)`: Get cached quote
- `clearMarketData(symbol?)`: Clear cache for symbol or all
- `clearError()`: Clear error state

**Getters:**
- `currentMarket`: Market info for selected market
- `currentStock`: Combined data for selected symbol
- `hasData(symbol)`: Check if market data is cached
- `hasQuote(symbol)`: Check if quote is cached
- `marketDataList`: All data for current market

**Types:**
```typescript
type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'

interface MarketData {
  symbol: string
  name: string
  price: number
  change: number
  changePct: number
  volume: number
  timestamp: string
  market: MarketCode
}

interface Quote {
  symbol: string
  price: number
  change: number
  changePct: number
  timestamp: string
}
```

### 3. UI Store (`ui.ts`)
Manages UI state including sidebar, theme, notifications, and modals.

**State:**
- `sidebarCollapsed`: Sidebar collapse state
- `mobileMenuOpen`: Mobile menu visibility
- `theme`: Theme mode ('light' | 'dark' | 'system')
- `notifications`: Array of toast notifications
- `modals`: Array of modal states
- `loading`: Global loading state
- `loadingMessage`: Loading message text
- `viewportWidth`: Current viewport width
- `viewportHeight`: Current viewport height

**Actions:**
- `toggleSidebar()`: Toggle sidebar collapsed state
- `setSidebarCollapsed(collapsed)`: Set sidebar state
- `toggleMobileMenu()`: Toggle mobile menu
- `setMobileMenuOpen(open)`: Set mobile menu state
- `setTheme(theme)`: Change theme mode
- `applyTheme()`: Apply current theme to DOM
- `addNotification(message, options)`: Add toast notification
- `removeNotification(id)`: Dismiss notification
- `clearNotifications()`: Clear all notifications
- `showSuccess/Error/Warning/Info(message, title?, duration?)`: Convenience methods
- `openModal(id, component?, props?)`: Open modal
- `closeModal(id)`: Close modal
- `removeModal(id)`: Remove modal from stack
- `closeAllModals()`: Close all modals
- `setLoading(isLoading, message?)`: Set global loading state
- `updateViewport()`: Update viewport dimensions

**Getters:**
- `isMobile`: Viewport < 768px
- `isTablet`: Viewport 768-1024px
- `isDesktop`: Viewport >= 1024px
- `activeNotifications`: Non-expired notifications
- `visibleModals`: Currently visible modals
- `hasActiveModal`: Whether any modal is visible
- `isDarkMode`: Computed dark mode state

**Types:**
```typescript
type NotificationType = 'success' | 'error' | 'warning' | 'info'
type ThemeMode = 'light' | 'dark' | 'system'

interface Notification {
  id: string
  type: NotificationType
  message: string
  title?: string
  duration?: number
  dismissible?: boolean
  timestamp: number
}
```

### 4. App Store (`app.ts`)
Existing store for global app state (authentication, workspace, etc.)

## Usage

```typescript
import { useDecisionStore, useMarketStore, useUIStore } from '@/stores'

// In a component
const decisionStore = useDecisionStore()
const marketStore = useMarketStore()
const uiStore = useUIStore()

// Fetch decisions
await decisionStore.fetchDecisions({ market: 'CN' })

// Select market and symbol
marketStore.setMarket('CN')
marketStore.setSymbol('600519.SH')
await marketStore.fetchMarketData('CN', '600519.SH')

// Show notification
uiStore.showSuccess('Decision created successfully')
```

## API Integration

All stores currently use placeholder mock data. API integration will be implemented in Task 11 (API Client). The stores are structured to easily replace mock calls with real API endpoints.

## WebSocket Updates

Real-time quote updates via WebSocket will be integrated in Task 12. The `updateQuote` and `updateMultipleQuotes` actions in the market store are ready for WebSocket data.
