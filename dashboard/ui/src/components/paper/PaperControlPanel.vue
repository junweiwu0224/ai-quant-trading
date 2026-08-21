<script setup lang="ts">
import { Check, RotateCcw, Square, X } from 'lucide-vue-next'
import { ref, computed } from 'vue'
import { api } from '../../api/client'
import { usePaperFormat } from '../../composables/usePaperFormat'

const props = defineProps<{
  status: Record<string, any> | null
  loading: boolean
  canOperate: boolean
  runningStateKnown: boolean
  running: boolean
  strategies: Record<string, any>[]
}>()

const emit = defineEmits<{ refresh: [] }>()

const statusRef = computed(() => props.status)
const { strategyContext } = usePaperFormat(statusRef)

const saving = ref(false)
const actionFeedback = ref('')
const actionError = ref('')
const startReview = ref(false)
const startForm = ref({ strategy: 'dual_ma', codes: '000001', interval: 30, cash: 50000, enable_risk: true })
const strategyOptions = computed(() => props.strategies.length ? props.strategies : [{ name: 'dual_ma', label: '双均线' }])

const statusDisplay = computed(() => {
  if (!props.runningStateKnown) return '状态未知'
  return props.running ? '运行中' : '已停止'
})

function requireOperable() {
  if (props.canOperate) return true
  actionError.value = '当前 paper 运行状态不可确认，已禁用此操作；请刷新状态后重试。'
  return false
}

async function startPaper() {
  if (!requireOperable() || saving.value) return
  saving.value = true; actionFeedback.value = ''; actionError.value = ''
  try {
    const codes = startForm.value.codes.split(',').map(c => c.trim()).filter(Boolean)
    await api.startPaper({ strategy: startForm.value.strategy, codes, interval: startForm.value.interval, initial_cash: startForm.value.cash, enable_risk: startForm.value.enable_risk })
    actionFeedback.value = 'paper 启动命令已接受；等待 worker/模拟引擎确认'
    startReview.value = false
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '启动失败' }
  finally { saving.value = false }
}

async function stopPaper() {
  if (!requireOperable() || saving.value) return
  saving.value = true; actionFeedback.value = ''; actionError.value = ''
  try {
    await api.stopPaper()
    actionFeedback.value = '停止命令已提交；等待确认'
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '停止失败' }
  finally { saving.value = false }
}

async function resetPaper() {
  if (!requireOperable() || saving.value) return
  saving.value = true; actionFeedback.value = ''; actionError.value = ''
  try {
    await api.resetPaper()
    actionFeedback.value = '重置命令已提交；请重新启动 paper'
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '重置失败' }
  finally { saving.value = false }
}
</script>

<template>
  <section class="panel paper-control-panel" :aria-busy="loading">
    <div class="panel-head">
      <div>
        <h2>Paper 运行控制</h2>
        <p>启动、停止和重置会提交 legacy paper 命令；点击后仍需等待后端确认。</p>
      </div>
      <span class="tag" :class="runningStateKnown ? (running ? 'good' : 'warn') : 'bad'">{{ statusDisplay }}</span>
    </div>
    <div class="button-row">
      <button class="button primary" type="button" :disabled="saving || !canOperate || running" @click="startReview = true"><Play :size="15" />启动</button>
      <button class="button danger" type="button" :disabled="saving || !canOperate || !running" @click="stopPaper"><Square :size="15" />停止</button>
      <button class="button ghost" type="button" :disabled="saving || !canOperate" @click="resetPaper"><RotateCcw :size="15" />重置</button>
    </div>
    <div v-if="actionError" class="error-box" role="alert"><X :size="16" />{{ actionError }}</div>
    <div v-if="actionFeedback" class="info-box" role="status" aria-live="polite"><Check :size="16" />{{ actionFeedback }}</div>

    <Teleport to="body">
      <div v-if="startReview" class="modal-backdrop" @click.self="startReview = false">
        <div class="modal" role="dialog" aria-labelledby="paper-start-title">
          <h3 id="paper-start-title">确认 paper 启动</h3>
          <div class="form-grid">
            <label>策略<div class="select-wrap"><select v-model="startForm.strategy"><option v-for="s in strategyOptions" :key="s.name" :value="s.name">{{ s.label || s.name }}</option></select></div></label>
            <label>股票代码（逗号分隔）<input v-model="startForm.codes" placeholder="000001,600519" /></label>
            <label>运行间隔（秒）<input v-model.number="startForm.interval" type="number" min="10" /></label>
            <label>初始现金<input v-model.number="startForm.cash" type="number" min="1000" /></label>
            <label class="checkbox-label"><input v-model="startForm.enable_risk" type="checkbox" />启用风控</label>
          </div>
          <p class="small muted">确认要提交 {{ strategyContext }} 的 paper 启动请求？提交后等待 worker/模拟引擎状态。</p>
          <div class="button-row">
            <button class="button primary" type="button" :disabled="saving || !canOperate" @click="startPaper"><Check :size="15" />确认提交</button>
            <button class="button ghost" type="button" @click="startReview = false">取消</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>
