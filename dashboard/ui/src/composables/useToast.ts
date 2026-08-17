import { useUIStore } from '../stores/ui'

/**
 * Toast notification composable
 * Provides a simple interface to show toast notifications using the UI store
 */
export function useToast() {
  const uiStore = useUIStore()

  /**
   * Show a success toast
   * @param message - The message to display
   * @param duration - Optional duration in milliseconds (default: 5000)
   * @returns Notification ID
   */
  function success(message: string, duration?: number): string {
    return uiStore.showSuccess(message, undefined, duration)
  }

  /**
   * Show an error toast
   * @param message - The message to display
   * @param duration - Optional duration in milliseconds (default: 8000)
   * @returns Notification ID
   */
  function error(message: string, duration?: number): string {
    return uiStore.showError(message, undefined, duration)
  }

  /**
   * Show a warning toast
   * @param message - The message to display
   * @param duration - Optional duration in milliseconds (default: 5000)
   * @returns Notification ID
   */
  function warning(message: string, duration?: number): string {
    return uiStore.showWarning(message, undefined, duration)
  }

  /**
   * Show an info toast
   * @param message - The message to display
   * @param duration - Optional duration in milliseconds (default: 5000)
   * @returns Notification ID
   */
  function info(message: string, duration?: number): string {
    return uiStore.showInfo(message, undefined, duration)
  }

  /**
   * Manually dismiss a toast notification
   * @param id - The notification ID returned from success/error/warning/info
   */
  function dismiss(id: string): void {
    uiStore.removeNotification(id)
  }

  return {
    success,
    error,
    warning,
    info,
    dismiss
  }
}
