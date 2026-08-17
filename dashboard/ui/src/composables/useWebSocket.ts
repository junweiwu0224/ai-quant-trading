import { ref, computed, onUnmounted } from 'vue'
import type { MarketCode } from '../stores/market'

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface WSMessage {
  type: 'quote' | 'notification' | 'alert' | 'ping' | 'pong'
  data: any
  timestamp: string
}

export interface QuoteUpdate {
  symbol: string
  market: string
  price: number
  change: number
  volume: number
  timestamp: string
}

export interface NotificationMessage {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  timestamp: string
}

export interface SubscriptionCallback {
  (data: any): void
}

// Singleton WebSocket instance
let wsInstance: WebSocket | null = null
let wsUrl: string | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let pingInterval: ReturnType<typeof setInterval> | null = null

const MAX_RECONNECT_ATTEMPTS = 10
const BASE_RECONNECT_DELAY = 1000 // 1 second
const MAX_RECONNECT_DELAY = 30000 // 30 seconds
const PING_INTERVAL = 30000 // 30 seconds

/**
 * WebSocket connection management composable
 * Provides a singleton WebSocket connection with auto-reconnect
 */
export function useWebSocket() {
  const state = ref<ConnectionState>('disconnected')
  const error = ref<string | null>(null)
  const lastMessage = ref<WSMessage | null>(null)

  // Subscription management
  const subscriptions = new Map<string, Set<SubscriptionCallback>>()

  const isConnected = computed(() => state.value === 'connected')
  const isConnecting = computed(() => state.value === 'connecting')
  const isDisconnected = computed(() => state.value === 'disconnected')
  const hasError = computed(() => state.value === 'error')

  /**
   * Calculate exponential backoff delay
   */
  function getReconnectDelay(): number {
    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts),
      MAX_RECONNECT_DELAY
    )
    // Add jitter to prevent thundering herd
    return delay + Math.random() * 1000
  }

  /**
   * Start ping/pong keepalive
   */
  function startPingInterval() {
    if (pingInterval) {
      clearInterval(pingInterval)
    }

    pingInterval = setInterval(() => {
      if (wsInstance && wsInstance.readyState === WebSocket.OPEN) {
        send({ type: 'ping', timestamp: new Date().toISOString() })
      }
    }, PING_INTERVAL)
  }

  /**
   * Stop ping/pong keepalive
   */
  function stopPingInterval() {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
  }

  /**
   * Handle incoming WebSocket message
   */
  function handleMessage(event: MessageEvent) {
    try {
      const message: WSMessage = JSON.parse(event.data)
      lastMessage.value = message

      // Handle pong responses
      if (message.type === 'pong') {
        return
      }

      // Dispatch to subscribers
      const callbacks = subscriptions.get(message.type)
      if (callbacks) {
        callbacks.forEach(callback => {
          try {
            callback(message.data)
          } catch (err) {
            console.error(`Error in subscription callback for ${message.type}:`, err)
          }
        })
      }

      // Dispatch to 'all' subscribers
      const allCallbacks = subscriptions.get('*')
      if (allCallbacks) {
        allCallbacks.forEach(callback => {
          try {
            callback(message)
          } catch (err) {
            console.error('Error in wildcard subscription callback:', err)
          }
        })
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err)
      error.value = 'Failed to parse message'
    }
  }

  /**
   * Handle WebSocket connection open
   */
  function handleOpen() {
    state.value = 'connected'
    error.value = null
    reconnectAttempts = 0
    startPingInterval()
  }

  /**
   * Handle WebSocket connection close
   */
  function handleClose(event: CloseEvent) {
    stopPingInterval()

    if (state.value === 'disconnected') {
      // Intentional disconnect, don't reconnect
      return
    }

    state.value = 'disconnected'

    // Attempt to reconnect
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      const delay = getReconnectDelay()

      reconnectTimer = setTimeout(() => {
        reconnectAttempts++
        if (wsUrl) {
          connect(wsUrl)
        }
      }, delay)
    } else {
      error.value = 'Maximum reconnection attempts reached'
      state.value = 'error'
    }
  }

  /**
   * Handle WebSocket error
   */
  function handleError(event: Event) {
    console.error('WebSocket error:', event)
    error.value = 'Connection error'
    state.value = 'error'
  }

  /**
   * Connect to WebSocket server
   * @param url - WebSocket URL (e.g., 'ws://localhost:8000/ws')
   */
  function connect(url: string): void {
    // If already connected to this URL, do nothing
    if (wsInstance && wsInstance.readyState === WebSocket.OPEN && wsUrl === url) {
      return
    }

    // Disconnect existing connection
    if (wsInstance) {
      disconnect()
    }

    wsUrl = url
    state.value = 'connecting'
    error.value = null

    try {
      wsInstance = new WebSocket(url)

      wsInstance.addEventListener('open', handleOpen)
      wsInstance.addEventListener('message', handleMessage)
      wsInstance.addEventListener('close', handleClose)
      wsInstance.addEventListener('error', handleError)
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      error.value = err instanceof Error ? err.message : 'Connection failed'
      state.value = 'error'
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  function disconnect(): void {
    // Clear reconnect timer
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    stopPingInterval()

    // Set state before closing to prevent auto-reconnect
    state.value = 'disconnected'
    reconnectAttempts = 0

    if (wsInstance) {
      wsInstance.removeEventListener('open', handleOpen)
      wsInstance.removeEventListener('message', handleMessage)
      wsInstance.removeEventListener('close', handleClose)
      wsInstance.removeEventListener('error', handleError)

      if (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING) {
        wsInstance.close(1000, 'Client disconnect')
      }

      wsInstance = null
    }

    wsUrl = null
  }

  /**
   * Subscribe to a message channel
   * @param channel - Channel name (message type) or '*' for all messages
   * @param callback - Callback function to handle messages
   */
  function subscribe(channel: string, callback: SubscriptionCallback): void {
    if (!subscriptions.has(channel)) {
      subscriptions.set(channel, new Set())
    }
    subscriptions.get(channel)!.add(callback)
  }

  /**
   * Unsubscribe from a message channel
   * @param channel - Channel name (message type) or '*' for all messages
   * @param callback - The callback function to remove (optional - removes all if not provided)
   */
  function unsubscribe(channel: string, callback?: SubscriptionCallback): void {
    if (!callback) {
      // Remove all callbacks for this channel
      subscriptions.delete(channel)
      return
    }

    const callbacks = subscriptions.get(channel)
    if (callbacks) {
      callbacks.delete(callback)
      if (callbacks.size === 0) {
        subscriptions.delete(channel)
      }
    }
  }

  /**
   * Send a message to the WebSocket server
   * @param message - Message object to send
   */
  function send(message: any): void {
    if (!wsInstance || wsInstance.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket is not connected. Cannot send message.')
      return
    }

    try {
      wsInstance.send(JSON.stringify(message))
    } catch (err) {
      console.error('Failed to send WebSocket message:', err)
      error.value = 'Failed to send message'
    }
  }

  /**
   * Subscribe to quote updates for symbols
   * @param symbols - Array of symbol codes
   * @param market - Market code
   */
  function subscribeQuotes(symbols: string[], market: MarketCode): void {
    send({
      type: 'subscribe',
      channel: 'quotes',
      symbols,
      market,
      timestamp: new Date().toISOString()
    })
  }

  /**
   * Unsubscribe from quote updates
   * @param symbols - Array of symbol codes
   * @param market - Market code
   */
  function unsubscribeQuotes(symbols: string[], market: MarketCode): void {
    send({
      type: 'unsubscribe',
      channel: 'quotes',
      symbols,
      market,
      timestamp: new Date().toISOString()
    })
  }

  /**
   * Get current connection state
   */
  function getState(): ConnectionState {
    return state.value
  }

  /**
   * Clear error state
   */
  function clearError(): void {
    error.value = null
    if (state.value === 'error') {
      state.value = 'disconnected'
    }
  }

  // Cleanup on component unmount
  onUnmounted(() => {
    disconnect()
  })

  return {
    state,
    error,
    lastMessage,
    isConnected,
    isConnecting,
    isDisconnected,
    hasError,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    send,
    subscribeQuotes,
    unsubscribeQuotes,
    getState,
    clearError
  }
}
