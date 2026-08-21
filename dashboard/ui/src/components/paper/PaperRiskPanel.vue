<script setup lang="ts">
import { Check, CircleAlert, RefreshCw, RotateCcw, Save, ShieldAlert } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../../api/client'
import { usePaperFormat } from '../../composables/usePaperFormat'

const props = defineProps<{
  status: Record<string, any> | null
  riskEvents: Record<string, any>[]
  riskRules: Record<string, any>
  canOperate: boolean
  saving: boolean
}>()

const emit = defineEmits<{ refresh: []; 'update:saving': [v: boolean] }>()

const statusRef = ref(props.status)
const { stateLabel, stateTone } = usePaperFormat(statusRef)
const riskForm = ref({ max_position_pct: 0.2, max_positions: 10, max_drawdown: 0.1, max_daily_loss: 0.03 })
const actionFeedback = ref('')
const actionError = ref('')

async function saveRiskRules() {
  emit('update:saving', true)
  actionFeedback.value = ''; actionError.value = ''
  try {
    await api.updatePaperRiskRules(riskForm.value)
    actionFeedback.value = '风控规则已保存'
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '保存失败' }
  finally { emit('update:saving', false) }
}
</script>

<template>
  <div class="section-grid two">
    <section class="panel">
      <div class="panel-head">
        <div><h2>风控规则</h2><p>规则仅对 paper 生效；对账和恢复状态以 status 返回为准。</p></div>
      </div>
      <form class="form-grid" @submit.prevent="saveRiskRules">
        <label>单票最大仓位占比<input v-model.number="riskForm.max_position_pct" type="number" step="0.01" min="0" max="1" /></label>
        <label>最大持仓数<input v-model.number="riskForm.max_positions" type="number" min="1" /></label>
        <label>最大回撤阈值<input v-model.number="riskForm.max_drawdown" type="number" step="0.01" min="0" max="1" /></label>
        <label>单日最大亏损<input v-model.number="riskForm.max_daily_loss" type="number" step="0.01" min="0" max="1" /></label>
        <div class="button-row"><button class="button primary" type="button" :disabled="saving || !canOperate" @click="saveRiskRules"><Save :size="15" />保存规则</button></div>
      </form>
      <div class="small muted" style="margin-top:16px">{{ JSON.stringify(riskRules, null, 2) }}</div>
      <div v-if="actionError" class="error-box" role="alert"><CircleAlert :size="16" />{{ actionError }}</div>
      <div v-if="actionFeedback" class="info-box" role="status" aria-live="polite"><Check :size="16" />{{ actionFeedback }}</div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <div><h2>对账、恢复与风险事件</h2><p>对账和恢复状态以 status 返回为准；当前 legacy API 未提供时显示未提供。</p></div>
        <span class="tag">{{ riskEvents.length }} 条</span>
      </div>
      <div class="state-list">
        <div class="state-row">
          <span><ShieldAlert :size="15" />最终 RiskGate</span>
          <span class="tag" :class="stateTone(props.status?.final_risk_status)">{{ stateLabel(props.status?.final_risk_status, '未提供') }}</span>
        </div>
        <div class="state-row">
          <span><RefreshCw :size="15" />对账</span>
          <span class="tag" :class="stateTone(props.status?.reconciliation_status)">{{ stateLabel(props.status?.reconciliation_status, '未提供') }}</span>
        </div>
        <div class="state-row">
          <span><RotateCcw :size="15" />恢复</span>
          <span class="tag" :class="stateTone(props.status?.recovery_status)">{{ stateLabel(props.status?.recovery_status, '未提供') }}</span>
        </div>
      </div>
      <div v-if="!riskEvents.length" class="empty">暂无风险事件；这不等于风控已通过。</div>
      <div v-else class="check-list">
        <div v-for="(event, index) in riskEvents" :key="index" class="check-item">
          <span class="tag" :class="event.status === 'passed' ? 'good' : event.status === 'rejected' ? 'bad' : 'warn'">{{ event.status || '—' }}</span>
          <div><strong>{{ event.rule || event.check || '风控检查' }}</strong><small>{{ event.reason || event.detail || '—' }}</small></div>
        </div>
      </div>
    </section>
  </div>
</template>
