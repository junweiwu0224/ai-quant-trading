import { computed, type Ref } from 'vue'

export function usePaperFormat(status: Ref<Record<string, any> | null>) {
  function payloadData(value: any): any {
    return value?.data ?? value
  }

  function number(value: unknown, digits = 2) {
    if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
    return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
  }

  function percent(value: unknown) {
    if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
    const numeric = Number(value)
    const percentage = Math.abs(numeric) <= 1 ? numeric * 100 : numeric
    return `${percentage.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })}%`
  }

  const LABELS: Record<string, string> = {
    ready: '就绪', running: '运行中', paused: '已暂停', stopping: '停止请求中',
    halted: '已停止', blocked: '已阻断', passed: '通过', failed: '失败',
    pending: '等待中', reconciling: '对账中', completed: '已完成',
    recovered: '已恢复', unavailable: '不可用',
  }

  function stateLabel(value: unknown, fallback: string) {
    if (value === null || value === undefined || value === '') return fallback
    const key = String(value).toLowerCase()
    return LABELS[key] || String(value)
  }

  function stateTone(value: unknown) {
    const text = String(value || '').toLowerCase()
    if (['ready', 'running', 'passed', 'completed', 'recovered', 'success'].some(s => text.includes(s))) return 'good'
    if (['failed', 'blocked', 'error', 'halted'].some(s => text.includes(s))) return 'bad'
    return 'warn'
  }

  function statusClass(value: unknown) {
    return stateTone(value)
  }

  function strategyContext() {
    return status.value?.config?.strategy || status.value?.strategy || '未提供'
  }

  const executionRunId = computed(() => status.value?.execution_run_id ?? status.value?.executionContext?.execution_run_id ?? null)
  const accountId = computed(() => status.value?.account_id ?? status.value?.account?.id ?? null)
  const accountLabel = computed(() => status.value?.account?.name ?? status.value?.account?.label ?? null)
  const finalRiskStatus = computed(() => status.value?.final_risk_status ?? status.value?.riskGate?.status ?? null)
  const reconciliationStatus = computed(() => status.value?.reconciliation_status ?? status.value?.reconciliation?.status ?? null)
  const recoveryStatus = computed(() => status.value?.recovery_status ?? status.value?.recovery?.status ?? null)
  const workerStatus = computed(() => status.value?.worker_status ?? status.value?.worker?.status ?? null)
  const compatibilityMode = computed(() => !executionRunId.value)

  return {
    payloadData, number, percent, stateLabel, stateTone, statusClass, strategyContext,
    executionRunId, accountId, accountLabel, finalRiskStatus, reconciliationStatus,
    recoveryStatus, workerStatus, compatibilityMode,
  }
}
