<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, Edit3, Plus, RefreshCw, Save, ShieldCheck, Trash2, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import BrokerDisableGuard from '../components/guards/BrokerDisableGuard.vue'

type Row = Record<string, any>
type RuleForm = { alert_rule_id: number; code: string; direction: string; order_type: string; price: number | null; volume: number; max_amount: number; enabled: boolean; cooldown: number }

const rules = ref<Row[]>([])
const events = ref<Row[]>([])
const form = ref<RuleForm>({ alert_rule_id: 1, code: '', direction: 'buy', order_type: 'market', price: null, volume: 100, max_amount: 0, enabled: false, cooldown: 300 })
const editingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)
const message = ref('')

function resetForm() {
  editingId.value = null
  deletingId.value = null
  form.value = { alert_rule_id: 1, code: '', direction: 'buy', order_type: 'market', price: null, volume: 100, max_amount: 0, enabled: false, cooldown: 300 }
}

function editRule(rule: Row) {
  editingId.value = Number(rule.id)
  deletingId.value = null
  form.value = {
    alert_rule_id: Number(rule.alert_rule_id || 1),
    code: String(rule.code || ''),
    direction: String(rule.direction || 'buy'),
    order_type: String(rule.order_type || 'market'),
    price: rule.price == null ? null : Number(rule.price),
    volume: Number(rule.volume || 100),
    max_amount: Number(rule.max_amount || 0),
    enabled: Boolean(rule.enabled),
    cooldown: Number(rule.cooldown || 300),
  }
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    const [rulesResponse, eventsResponse] = await Promise.all([api.conditionalRules(), api.conditionalEvents()])
    rules.value = Array.isArray(rulesResponse.data) ? rulesResponse.data : []
    events.value = Array.isArray(eventsResponse.data) ? eventsResponse.data : []
  } catch (error) {
    message.value = error instanceof Error ? error.message : '条件单加载失败'
  } finally {
    loading.value = false
  }
}

async function saveRule() {
  if (!form.value.code.trim() || form.value.volume < 100 || form.value.volume % 100 !== 0 || (form.value.order_type === 'limit' && !(Number(form.value.price) > 0))) {
    message.value = '请填写六位股票代码、100 的整数倍数量；限价单必须填写价格'
    return
  }
  saving.value = true
  message.value = ''
  try {
    if (editingId.value) {
      await api.updateConditionalRule(editingId.value, form.value)
      message.value = '条件单已更新，保持当前启用状态'
    } else {
      await api.createConditionalRule({ ...form.value, enabled: false })
      message.value = '条件单已创建，默认保持关闭状态'
    }
    resetForm()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '条件单保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleRule(rule: Row) {
  saving.value = true
  message.value = ''
  try {
    await api.updateConditionalRule(rule.id, { enabled: !rule.enabled })
    message.value = rule.enabled ? '条件单已关闭' : '条件单已启用；仍受模拟盘风控约束'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '条件单状态更新失败'
  } finally {
    saving.value = false
  }
}

async function deleteRule(rule: Row) {
  if (deletingId.value !== Number(rule.id)) {
    deletingId.value = Number(rule.id)
    return
  }
  saving.value = true
  try {
    await api.deleteConditionalRule(rule.id)
    message.value = '条件单已删除'
    resetForm()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '条件单删除失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <BrokerDisableGuard />
  <section>
    <div class="page-head"><div><RouterLink to="/app/workflows" class="muted small"><ArrowLeft :size="14" />返回工作流目录</RouterLink><h1>条件单</h1><p>条件单只写入模拟盘订单路径。规则可以编辑、启停和删除；启用不等于真实下单，也不会绕过风险校验。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button></div>
    <div v-if="message" class="error-box" role="status">{{ message }}</div>
    <div class="section-grid two">
      <section class="panel"><div class="panel-head"><div><h2>{{ editingId ? '编辑条件单' : '创建条件单' }}</h2><p>新建规则默认关闭；修改后仍会保留人工启停动作。</p></div><ShieldCheck :size="18" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="conditional-code">股票代码</label><input id="conditional-code" v-model="form.code" placeholder="600519" maxlength="6" /></div><div class="field"><label for="conditional-rule">告警规则 ID</label><input id="conditional-rule" v-model.number="form.alert_rule_id" type="number" min="1" /></div><div class="field"><label for="conditional-direction">方向</label><select id="conditional-direction" v-model="form.direction"><option value="buy">买入</option><option value="sell">卖出</option></select></div><div class="field"><label for="conditional-volume">数量</label><input id="conditional-volume" v-model.number="form.volume" type="number" min="100" step="100" /></div><div class="field"><label for="conditional-type">订单类型</label><select id="conditional-type" v-model="form.order_type"><option value="market">市价</option><option value="limit">限价</option></select></div><div class="field"><label for="conditional-price">限价</label><input id="conditional-price" v-model.number="form.price" type="number" min="0" step="0.001" :disabled="form.order_type !== 'limit'" /></div><div class="field"><label for="conditional-max">最大金额</label><input id="conditional-max" v-model.number="form.max_amount" type="number" min="0" step="100" /></div><div class="field"><label for="conditional-cooldown">冷却秒数</label><input id="conditional-cooldown" v-model.number="form.cooldown" type="number" min="0" /></div></div><div class="form-actions"><span class="tag warn">{{ editingId ? (form.enabled ? '当前已启用' : '当前已关闭') : '默认 disabled' }}</span><button class="button primary" type="button" :disabled="saving" @click="saveRule"><Save :size="15" />{{ saving ? '保存中' : editingId ? '保存修改' : '保存关闭规则' }}</button><button v-if="editingId" class="button ghost" type="button" @click="resetForm"><X :size="15" />取消编辑</button></div></div></section>
      <section class="panel"><div class="panel-head"><div><h2>规则列表</h2><p>启用/关闭只改变条件单引擎状态，执行仍记录在事件和模拟盘订单中。</p></div><span class="tag">{{ rules.length }} 条</span></div><div class="panel-body"><div v-if="!rules.length" class="empty">暂无条件单规则。</div><div v-else class="rule-list"><article v-for="rule in rules" :key="rule.id" class="rule-row"><div class="rule-copy"><strong>{{ rule.code || '未标的' }} · {{ rule.direction === 'sell' ? '卖出' : '买入' }}</strong><span>{{ rule.order_type || '—' }} · {{ rule.volume ?? '—' }} 股 · 关联告警 {{ rule.alert_rule_id ?? '—' }}</span><small>冷却 {{ rule.cooldown ?? 0 }} 秒 · 最大金额 {{ rule.max_amount || '不限' }}</small></div><div class="rule-actions"><span class="tag" :class="rule.enabled ? 'warn' : 'good'">{{ rule.enabled ? '已启用' : '已关闭' }}</span><button class="icon-button compact-icon" type="button" :disabled="saving" title="启用或关闭" aria-label="启用或关闭" @click="toggleRule(rule)"><ShieldCheck :size="14" /></button><button class="icon-button compact-icon" type="button" title="编辑条件单" aria-label="编辑条件单" @click="editRule(rule)"><Edit3 :size="14" /></button><button class="icon-button compact-icon" type="button" title="删除条件单" aria-label="删除条件单" @click="deleteRule(rule)"><Trash2 :size="14" /></button></div><div v-if="deletingId === Number(rule.id)" class="inline-confirm"><span>再次点击确认删除这条条件单。</span><button class="button danger" type="button" :disabled="saving" @click="deleteRule(rule)">确认删除</button><button class="button ghost" type="button" @click="deletingId = null">取消</button></div></article></div></div></section>
    </div>
    <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>触发事件</h2><p>事件只做审计展示，不能从此处直接下单。</p></div><span class="tag">{{ events.length }} 条</span></div><div class="panel-body"><div v-if="!events.length" class="empty">暂无条件单事件。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>规则</th><th>状态</th><th>详情</th></tr></thead><tbody><tr v-for="(event, index) in events" :key="String(event.id || index)"><td>{{ event.created_at || event.time || '—' }}</td><td>{{ event.rule_id || event.alert_rule_id || '—' }}</td><td>{{ event.status || event.event_type || '—' }}</td><td>{{ event.message || event.reason || '—' }}</td></tr></tbody></table></div></div></section>
  </section>
</template>
