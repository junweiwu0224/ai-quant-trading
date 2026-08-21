<script setup lang="ts">
import { Check, CircleAlert, Pause, Save, X } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../../api/client'
import { usePaperFormat } from '../../composables/usePaperFormat'

const props = defineProps<{
  positions: Record<string, any>[]
  canOperate: boolean
  saving: boolean
}>()

const emit = defineEmits<{ refresh: []; 'update:saving': [v: boolean] }>()

const { number } = usePaperFormat(ref(null))
const stopDrafts = ref<Record<string, { stop_loss_price: number | null; take_profit_price: number | null }>>({})
const closeCode = ref('')
const closeVolume = ref(0)
const showCloseForm = ref<string | null>(null)
const actionFeedback = ref('')
const actionError = ref('')

function requireOperable() {
  if (props.canOperate) return true
  actionError.value = '当前 paper 运行状态不可确认，已禁用此操作。'
  return false
}

function getStopDraft(code: string) {
  if (!stopDrafts.value[code]) stopDrafts.value[code] = { stop_loss_price: null, take_profit_price: null }
  return stopDrafts.value[code]
}

async function savePositionRisk(code: string) {
  if (!requireOperable()) return
  const draft = getStopDraft(code)
  emit('update:saving', true)
  actionFeedback.value = ''; actionError.value = ''
  try {
    await api.updatePaperPositionRisk(code, { stop_loss_price: draft.stop_loss_price, take_profit_price: draft.take_profit_price })
    actionFeedback.value = `已提交 ${code} 的止损/止盈设置`
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '保存失败' }
  finally { emit('update:saving', false) }
}

function openCloseForm(position: Record<string, any>) {
  closeCode.value = position.code || position.instrument || ''
  closeVolume.value = Number(position.volume || 0)
  showCloseForm.value = closeCode.value
}

async function closePosition(position: Record<string, any>) {
  const code = position.code || position.instrument
  if (!code || !requireOperable()) return
  if (!closeVolume.value || closeVolume.value > Number(position.volume) || closeVolume.value % 100 !== 0) {
    actionError.value = '平仓数量必须为 100 的整数倍且不超过持仓'
    return
  }
  emit('update:saving', true)
  actionFeedback.value = ''; actionError.value = ''
  try {
    await api.createPaperOrder({
      code, direction: 'sell', order_type: 'market', volume: closeVolume.value,
      strategy_name: 'manual', signal_reason: '人工平仓',
    })
    actionFeedback.value = `已提交 ${code} 平仓命令`
    showCloseForm.value = null
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '平仓失败' }
  finally { emit('update:saving', false) }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div><h2>Paper 持仓与退出</h2><p>止损、止盈和平仓只创建 paper 动作；提交后等待 worker/撮合状态，不代表已成交。</p></div>
      <span class="tag">{{ positions.length }} 个标的</span>
    </div>
    <div v-if="!positions.length" class="empty">暂无持仓；这不等于风控已通过。</div>
    <div v-else class="table-wrap">
      <table class="table" aria-label="paper 持仓">
        <thead><tr><th>代码</th><th>持仓量</th><th>现价</th><th>成本</th><th>盈亏</th><th>止损</th><th>止盈</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="pos in positions" :key="pos.code || pos.instrument">
            <td>{{ pos.code || pos.instrument || '—' }}</td>
            <td>{{ number(pos.volume ?? pos.quantity, 0) }}</td>
            <td>{{ number(pos.current_price ?? pos.price) }}</td>
            <td>{{ number(pos.avg_cost ?? pos.cost_price) }}</td>
            <td :class="(pos.pnl ?? pos.unrealized_pnl ?? 0) >= 0 ? 'good' : 'bad'">{{ number(pos.pnl ?? pos.unrealized_pnl) }}</td>
            <td>
              <div class="inline-edit" v-if="showCloseForm !== (pos.code || pos.instrument)">
                <input v-model.number="getStopDraft(pos.code || pos.instrument).stop_loss_price" type="number" step="0.01" placeholder="止损价" class="mini-input" />
                <input v-model.number="getStopDraft(pos.code || pos.instrument).take_profit_price" type="number" step="0.01" placeholder="止盈价" class="mini-input" />
                <button class="button ghost small" type="button" :disabled="saving || !canOperate" @click="savePositionRisk(pos.code || pos.instrument)"><Save :size="14" /></button>
              </div>
            </td>
            <td>
              <template v-if="showCloseForm === (pos.code || pos.instrument)">
                <input v-model.number="closeVolume" type="number" step="100" :max="Number(pos.volume)" class="mini-input" />
                <button class="button danger small" type="button" :disabled="saving || !canOperate" @click="closePosition(pos)"><Check :size="14" />确认</button>
                <button class="button ghost small" type="button" @click="showCloseForm = null"><X :size="14" /></button>
              </template>
              <button v-else class="button ghost small" type="button" @click="openCloseForm(pos)"><Pause :size="14" />平仓</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="actionError" class="error-box" role="alert"><CircleAlert :size="16" />{{ actionError }}</div>
    <div v-if="actionFeedback" class="info-box" role="status" aria-live="polite"><Check :size="16" />{{ actionFeedback }}</div>
  </section>
</template>
