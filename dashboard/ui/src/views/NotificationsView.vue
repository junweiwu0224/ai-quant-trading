<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bell, CircleAlert, History, Link2, Plus, RefreshCw, Send, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api/client'

const targets = ref<any[]>([])
const routes = ref<any[]>([])
const portfolios = ref<any[]>([])
const attempts = ref<any[]>([])
const loading = ref(false)
const form = ref({ channel: 'wecom_robot', label: '', secret_ref: '', endpoint_ref: '' })
const routeForm = ref({ portfolio_id: '', target_id: '', event_type: 'scheduled' })
const message = ref('')

async function load() {
  loading.value = true
  try {
    const [targetResponse, routeResponse, portfolioResponse, attemptResponse] = await Promise.all([
      api.get<{ items: any[] }>('/api/decisions/targets'),
      api.get<{ items: any[] }>('/api/decisions/routes'),
      api.get<{ items: any[] }>('/api/decisions/portfolios'),
      api.get<{ items: any[] }>('/api/decisions/delivery-attempts'),
    ])
    targets.value = targetResponse.items || []
    routes.value = routeResponse.items || []
    portfolios.value = portfolioResponse.items || []
    attempts.value = attemptResponse.items || []
  } catch (error) {
    message.value = error instanceof Error ? error.message : '通知配置加载失败'
  } finally {
    loading.value = false
  }
}

async function addTarget() {
  try {
    await api.post('/api/decisions/targets', form.value)
    form.value = { channel: 'wecom_robot', label: '', secret_ref: '', endpoint_ref: '' }
    message.value = '目标已保存，仍需完成受控测试'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '目标保存失败'
  }
}

async function testTarget(id: string) {
  try {
    const queued = await api.post<{ command_id: string }>(`/api/decisions/targets/${id}/test`, {})
    const command = await api.waitDecisionCommand<any>(queued.command_id)
    message.value = command.result?.message || command.result?.status || (command.status === 'failed' ? '测试失败' : '测试完成')
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '测试失败'
  }
}

async function addRoute() {
  try {
    await api.post('/api/decisions/routes', routeForm.value)
    message.value = '路由已保存'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '路由保存失败'
  }
}

function targetLabel(targetId: string) {
  return targets.value.find((target) => target.id === targetId)?.label || targetId
}

function portfolioLabel(portfolioId: string) {
  return portfolios.value.find((portfolio) => portfolio.id === portfolioId)?.name || portfolioId
}

function attemptClass(status: string) {
  if (status === 'delivered') return 'good'
  if (['failed', 'dead', 'blocked_target', 'blocked_external'].includes(status)) return 'bad'
  return 'warn'
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div><h1>通知路由</h1><p>摘要发送到企业微信、个人微信服务、飞书或 QQ；完整报告通过短期只读链接打开。凭证只使用受保护引用。</p></div>
      <div class="head-actions"><span class="tag warn"><ShieldCheck :size="14" />外部投递默认关闭</span><button class="button" :disabled="loading" type="button" @click="load"><RefreshCw :size="15" />刷新</button></div>
    </div>
    <div v-if="message" class="error-box" role="status">{{ message }}</div>

    <div class="section-grid two">
      <section class="panel">
        <div class="panel-head"><div><h2>通知目标</h2><p>每个渠道独立测试、失败计数和停用。</p></div><Bell :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="field-grid">
            <div class="field"><label>渠道</label><select v-model="form.channel"><option value="wecom_robot">企业微信机器人</option><option value="pushplus">PushPlus 个人微信</option><option value="feishu_robot">飞书群机器人</option><option value="qq_official_bot">QQ 官方机器人</option></select></div>
            <div class="field"><label>显示名称</label><input v-model="form.label" placeholder="例如 盘前企业微信" /></div>
            <div class="field"><label>密钥引用</label><input v-model="form.secret_ref" placeholder="env://QUANT_CHANNEL_SECRET" /></div>
            <div class="field"><label>端点引用</label><input v-model="form.endpoint_ref" placeholder="env://WECHAT_WEBHOOK_URL" /></div>
          </div>
          <div class="form-actions"><button class="button primary" :disabled="!form.label || !form.secret_ref" @click="addTarget"><Plus :size="15" />保存目标</button></div>
        </div>
        <div v-if="!targets.length" class="panel-body"><div class="empty">尚未配置渠道。保存后仍不能自动推送，直到测试通过。</div></div>
        <div v-for="target in targets" :key="target.id" class="report-card">
          <div style="display:flex;justify-content:space-between;gap:10px"><div><strong>{{ target.label }}</strong><div class="report-meta"><span>{{ target.channel }}</span><span>{{ target.test_status }}</span><span>失败 {{ target.failure_count }} 次</span></div></div><button class="button" @click="testTarget(target.id)"><Send :size="14" />测试</button></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head"><div><h2>报告路由</h2><p>按组合和事件类型分发，不参与动作计算。</p></div><Link2 :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="field-grid"><div class="field"><label>策略组合</label><select v-model="routeForm.portfolio_id"><option value="">选择组合</option><option v-for="item in portfolios" :key="item.id" :value="item.id">{{ item.name }}</option></select></div><div class="field"><label>通知目标</label><select v-model="routeForm.target_id"><option value="">选择目标</option><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.label }}</option></select></div><div class="field"><label>事件类型</label><select v-model="routeForm.event_type"><option value="scheduled">定时报告</option><option value="state_change">状态变化</option><option value="major_risk">首次重大风险</option></select></div></div>
          <div class="form-actions"><button class="button primary" :disabled="!routeForm.portfolio_id || !routeForm.target_id" @click="addRoute"><Plus :size="15" />保存路由</button></div>
        </div>
        <div v-if="!routes.length" class="panel-body"><div class="empty">暂无路由。</div></div>
        <div v-for="item in routes" :key="item.id" class="report-card"><strong>{{ portfolioLabel(item.portfolio_id) }}</strong><div class="report-meta"><span>{{ item.event_type }}</span><span>{{ targetLabel(item.target_id) }}</span><span>{{ item.enabled ? '已启用' : '已停用' }}</span></div></div>
      </section>
    </div>

    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><h2>发送历史与失败队列</h2><p>每一次投递尝试都可审计；失败、阻断和死信不会被展示成“已发送”。</p></div><History :size="18" class="faint" /></div>
      <div v-if="!attempts.length" class="panel-body"><div class="empty"><strong>暂无投递尝试</strong><span>启用外部渠道前，系统只会在这里记录受控阻断原因。</span></div></div>
      <div v-else class="panel-body"><div class="stack-sm"><article v-for="attempt in attempts.slice(0, 50)" :key="attempt.id" class="report-card"><div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><strong>{{ targetLabel(attempt.target_id) }}</strong><div class="report-meta"><span>报告 {{ attempt.report_id }}</span><span>第 {{ attempt.attempt_no }} 次</span><span>{{ attempt.created_at }}</span></div><div v-if="attempt.error" class="muted small">{{ attempt.error }}</div></div><span class="tag" :class="attemptClass(attempt.status)"><CircleAlert v-if="attempt.status !== 'delivered'" :size="13" />{{ attempt.status }}</span></div></article></div></div>
    </section>
  </section>
</template>
