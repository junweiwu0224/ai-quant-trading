import { isAbortError } from '../api/client'

export type RetryOptions = {
  maxRetries?: number
  delayMs?: number
  shouldRetry?: (error: unknown, attempt: number) => boolean
}

const defaultShouldRetry = (error: unknown, attempt: number) => {
  if (isAbortError(error)) return false
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status: number }).status
    return status === 408 || status === 429 || status >= 500
  }
  return attempt < 2
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const { maxRetries = 2, delayMs = 1000, shouldRetry = defaultShouldRetry } = options
  let lastError: unknown
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error
      if (attempt < maxRetries && shouldRetry(error, attempt)) {
        await new Promise(resolve => setTimeout(resolve, delayMs * (attempt + 1)))
        continue
      }
      throw error
    }
  }
  throw lastError
}
