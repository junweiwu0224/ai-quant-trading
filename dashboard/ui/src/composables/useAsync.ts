import { ref, type Ref } from 'vue'
import { formatApiError } from '../api/client'

export function useAsync<T>(fn: () => Promise<T>) {
  const busy = ref(false)
  const error = ref('')
  const data: Ref<T | null> = ref(null)

  const run = async (...args: Parameters<typeof fn>) => {
    busy.value = true
    error.value = ''
    try {
      data.value = await fn(...args)
      return data.value
    } catch (e) {
      const message = e instanceof Error ? e.message : formatApiError(e)
      error.value = message
      throw e
    } finally {
      busy.value = false
    }
  }

  return { busy, error, data, run }
}
