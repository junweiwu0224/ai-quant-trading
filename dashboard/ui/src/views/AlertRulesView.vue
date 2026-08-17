<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BellRing, Check, CircleAlert, Edit3, Plus, RefreshCw, RotateCw, Save, Trash2, X } from 'lucide-vue-next'
import { api } from '../api/client'

type Row = Record<string, any>

const rules = ref<Row[]>([])
const history = ref<Row[]>([])
const conditions = ref<Record<string, string>>({})
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const editingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const form = ref({ code: '', condition: 'price_above', threshold: 0, name: '', cooldown: 300, webhook_url: '' })

const conditionOptions = computed(() => {
  const entries = Object.entries(conditions.value)
  return entries.length ? entries : [
    ['price_above', '价格突破'],
    ['price_below', '价格跌破'],
    ['change_above', '涨幅超过'],
    ['change_below', '跌幅超过'],
    ['volume_ratio_above', '量比超过'],
    ['turnover_above', '换手率超过'],
    ['amplitude_above', '振幅超过'],
  ]
})

function resetForm() {
  editingId.value = null
  deletingId.value = null
  form.value = { code: '', condition: conditionOptions.value[0]?.[0] || 'price_above', threshold: 0, name: '', cooldown: 300, webhook_url: '' }
}

function editRule(rule: Row) {
  editingId.value = Number(rule.id)
  deletingId.value = null
  form.value = {
    code: String(rule.code || ''),
    condition: String(rule.condition || 'price_above'),
    threshold: Number(rule.threshold || 0),
    name: String(rule.name || ''),
    cooldown: Number(rule.cooldown || 300),
    webhook_url: String(rule.webhook_url || ''),
  }
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    const [rulesResponse, conditionResponse, historyResponse] = await Promise.all([
      api.alerts(), api.alertConditions(), api.alertHistory(),
    ])
    rules.value = Array.isArray(rulesResponse.rules) ? rulesResponse.rules : []
    conditions.value = conditionResponse.conditions || {}
    history.value = Array.isArray(historyResponse.alerts) ? historyResponse.alerts : []
    if (!editingId.value && !form.value.condition) resetForm()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '告警数据加载失败'
  } finally {
    loading.value = false
  }
}

async function saveRule() {
  if (!form.value.code.trim() || !Number.isFinite(Number(form.value.threshold))) {
    message.value = '请填写股票代码和有效阈值'
    return
  }
  saving.value = true
  message.value = ''
  try {
    if (editingId.value) {
      await api.updateAlertRule(editingId.value, form.value)
      message.value = '告警规则已更新'
    } else {
      await api.createAlertRule(form.value)
      message.value = '告警规则已创建，默认保持关闭直到你启用'
    }
    resetForm()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '告警规则保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleRule(rule: Row) {
  saving.value = true
  message.value = ''
  try {
    await api.updateAlertRule(rule.id, { enabled: !rule.enabled })
    message.value = rule.enabled ? '告警规则已关闭' : '告警规则已启用'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '告警状态更新失败'
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
  message.value = ''
  try {
    await api.deleteAlertRule(rule.id)
    message.value = '告警规则已删除'
    deletingId.value = null
    if (editingId.value === Number(rule.id)) resetForm()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '告警规则删除失败'
  } finally {
    saving.value = false
  }
}

async function reloadEngine() {
  saving.value = true
  try {
    await api.reloadAlertRules()
    message.value = '告警引擎已重新加载规则'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '告警引擎重载失败'
  } finally {
    saving.value = false
  }
}

function conditionLabel(value: unknown) {
  return conditions.value[String(value)] || String(value || '—')
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div><h1>告警规则</h1><p>告警只产生研究提醒，不改变确定性决策、自动推送资格或订单。每条规则都按当前 workspace 隔离。</p></div>
      <div class="head-actions"><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />刷新</button><button class="button" type="button" :disabled="saving" @click="reloadEngine"><RotateCw :size="15" />重载引擎</button></div>
    </div>
    <div v-if="message" class="error-box" role="status"><CircleAlert :size="16" />{{ message }}</div>

    <div class="section-grid two">
      <section class="panel">
        <div class="panel-head"><div><h2>{{ editingId ? '编辑告警' : '创建告警' }}</h2><p>启用是独立动作；保存规则不会自动打开。</p></div><BellRing :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="field-grid">
            <div class="field"><label for="alert-code">股票代码</label><input id="alert-code" v-model="form.code" maxlength="16" placeholder="600519" /></div>
            <div class="field"><label for="alert-condition">条件</label><select id="alert-condition" v-model="form.condition"><option v-for="item in conditionOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></div>
            <div class="field"><label for="alert-threshold">阈值</label><input id="alert-threshold" v-model.number="form.threshold" type="number" step="0.01" /></div>
            <div class="field"><label for="alert-cooldown">冷却秒数</label><input id="alert-cooldown" v-model.number="form.cooldown" type="number" min="0" /></div>
            <div class="field"><label for="alert-name">规则名称</label><input id="alert-name" v-model="form.name" placeholder="盘中突破提醒" /></div>
            <div class="field"><label for="alert-webhook">Webhook 引用（可选）</label><input id="alert-webhook" v-model="form.webhook_url" placeholder="env://ALERT_WEBHOOK_URL" autocomplete="off" /></div>
          </div>
          <div class="form-actions"><button class="button primary" type="button" :disabled="saving" @click="saveRule"><Save :size="15" />{{ saving ? '保存中' : editingId ? '保存修改' : '保存关闭规则' }}</button><button v-if="editingId" class="button ghost" type="button" @click="resetForm"><X :size="15" />取消编辑</button></div>
          <div class="security-note"><Check :size="15" /><span>只保存引用，不保存密钥正文。外部通知仍需目标测试和独立资格。</span></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head"><div><h2>已配置规则</h2><p>启用、编辑和删除都保留在同一个可审计列表。</p></div><span class="tag">{{ rules.length }} 条</span></div>
        <div class="panel-body">
          <div v-if="!rules.length" class="empty"><strong>暂无告警规则</strong><span>创建一条规则后，它会以关闭状态出现在这里。</span></div>
          <div v-else class="rule-list">
            <article v-for="rule in rules" :key="rule.id" class="rule-row">
              <div class="rule-copy"><strong>{{ rule.name || `${rule.code} · ${conditionLabel(rule.condition)}` }}</strong><span>{{ rule.code }} · {{ conditionLabel(rule.condition) }} {{ rule.threshold }} · 冷却 {{ rule.cooldown || 0 }} 秒</span><small>{{ rule.webhook_url ? '已配置引用' : '不投递外部通知' }}</small></div>
              <div class="rule-actions"><span class="tag" :class="rule.enabled ? 'good' : 'warn'">{{ rule.enabled ? '已启用' : '已关闭' }}</span><button class="icon-button compact-icon" type="button" :disabled="saving" title="启用或关闭" aria-label="启用或关闭" @click="toggleRule(rule)"><Check v-if="rule.enabled" :size="14" /><BellRing v-else :size="14" /></button><button class="icon-button compact-icon" type="button" title="编辑规则" aria-label="编辑规则" @click="editRule(rule)"><Edit3 :size="14" /></button><button class="icon-button compact-icon" type="button" title="删除规则" aria-label="删除规则" @click="deleteRule(rule)"><Trash2 :size="14" /></button></div>
              <div v-if="deletingId === Number(rule.id)" class="inline-confirm"><span>再次点击确认删除这条规则。</span><button class="button danger" type="button" :disabled="saving" @click="deleteRule(rule)">确认删除</button><button class="button ghost" type="button" @click="deletingId = null">取消</button></div>
            </article>
          </div>
        </div>
      </section>
    </div>

    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><h2>触发历史</h2><p>触发记录只表达提醒事实；空结果不会被补成“无风险”。</p></div><span class="tag">{{ history.length }} 条</span></div>
      <div class="panel-body"><div v-if="!history.length" class="empty">暂无触发记录。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>时间</th><th>标的</th><th>条件</th><th>阈值</th><th>状态</th><th>详情</th></tr></thead><tbody><tr v-for="(item, index) in history" :key="String(item.id || index)"><td>{{ item.triggered_at || item.created_at || item.time || '—' }}</td><td class="symbol">{{ item.code || '—' }}</td><td>{{ conditionLabel(item.condition || item.alert_type) }}</td><td>{{ item.threshold ?? '—' }}</td><td><span class="tag" :class="item.delivered ? 'good' : 'warn'">{{ item.delivered ? '已记录投递' : '仅记录' }}</span></td><td>{{ item.message || item.reason || '—' }}</td></tr></tbody></table></div></div>
    </section>
  </section>
</template>
