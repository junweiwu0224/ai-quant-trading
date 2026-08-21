<script setup lang="ts">
import { Ban, ShieldAlert, RefreshCw, RotateCcw, Play } from 'lucide-vue-next'
import { usePaperFormat } from '../../composables/usePaperFormat'
import { computed, toRef } from 'vue'

const props = defineProps<{
  status: Record<string, any> | null
  loading: boolean
}>()

const statusRef = toRef(props, 'status')
const { stateLabel, stateTone, executionRunId, accountId, accountLabel, finalRiskStatus, reconciliationStatus, recoveryStatus, workerStatus, compatibilityMode } = usePaperFormat(statusRef)
const statusDisplay = computed(() => {
  if (!props.status) return '未知'
  return props.status.running ? '运行中' : '已停止'
})
</script>

<template>
  <section class="panel execution-context-panel" :aria-busy="loading">
    <div class="panel-head">
      <div>
        <h2>执行上下文与安全边界</h2>
        <p>状态仅来自 `/api/paper/status` 及现有兼容接口；缺少 V2 字段时明确显示未绑定。</p>
      </div>
      <span class="tag" :class="stateTone(statusDisplay)">{{ statusDisplay }}</span>
    </div>
    <div class="context-grid">
      <div class="context-item">
        <span>执行运行</span>
        <strong>{{ executionRunId || '未绑定' }}</strong>
        <small>{{ compatibilityMode ? '兼容模式：legacy status 未提供 V2 run' : '后端返回的运行标识' }}</small>
      </div>
      <div class="context-item">
        <span>账户</span>
        <strong>{{ accountLabel || accountId || '未绑定' }}</strong>
        <small>{{ accountId ? `账户 ID：${accountId}` : '后端未提供账户上下文' }}</small>
      </div>
    </div>
    <div class="state-list" aria-label="执行状态">
      <div class="state-row">
        <span><ShieldAlert :size="15" />最终风控</span>
        <span class="tag" :class="stateTone(finalRiskStatus)">{{ stateLabel(finalRiskStatus, '未提供') }}</span>
      </div>
      <div class="state-row">
        <span><RefreshCw :size="15" />对账</span>
        <span class="tag" :class="stateTone(reconciliationStatus)">{{ stateLabel(reconciliationStatus, '未提供') }}</span>
      </div>
      <div class="state-row">
        <span><RotateCcw :size="15" />恢复</span>
        <span class="tag" :class="stateTone(recoveryStatus)">{{ stateLabel(recoveryStatus, '未提供') }}</span>
      </div>
      <div class="state-row">
        <span><Play :size="15" />Worker</span>
        <span class="tag" :class="stateTone(workerStatus)">{{ stateLabel(workerStatus, '未提供') }}</span>
      </div>
    </div>
    <div class="execution-boundary" role="status">
      <Ban :size="16" />
      <span><strong>Live 已禁用</strong>：当前没有 Live permit、Broker 连接或真实执行权。</span>
    </div>
  </section>
</template>
