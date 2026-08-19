<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bell, CircleAlert, History, Link2, Plus, RefreshCw, Send, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api/client'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import AsyncState from '../components/base/AsyncState.vue'

const targets = ref<any[]>([])
const routes = ref<any[]>([])
const portfolios = ref<any[]>([])
const attempts = ref<any[]>([])
const loading = ref(false)
const refreshing = ref(false)
const form = ref({ channel: 'wecom_robot', label: '', secret_ref: '', endpoint_ref: '' })
const routeForm = ref({ portfolio_id: '', target_id: '', event_type: 'scheduled' })
const message = ref('')
const noticeState = ref<'success' | 'partial' | 'error' | ''>('')

const attemptSummary = computed(() => ({
  delivered: attempts.value.filter((attempt) => attempt.status === 'delivered').length,
  blocked: attempts.value.filter((attempt) => String(attempt.status || '').startsWith('blocked_')).length,
  review: attempts.value.filter((attempt) => ['retryable', 'unknown', 'dispatching'].includes(String(attempt.status))).length,
  failed: attempts.value.filter((attempt) => ['failed', 'dead'].includes(String(attempt.status))).length,
}))

async function loadData(preserveNotice = false) {
  loading.value = true
  refreshing.value = targets.value.length > 0 || routes.value.length > 0 || attempts.value.length > 0
  if (!preserveNotice) {
    message.value = ''
    noticeState.value = ''
  }
  try {
    const results = await Promise.allSettled([
      api.get<{ items: any[] }>('/api/decisions/targets'),
      api.get<{ items: any[] }>('/api/decisions/routes'),
      api.get<{ items: any[] }>('/api/decisions/portfolios'),
      api.get<{ items: any[] }>('/api/decisions/delivery-attempts'),
    ])
    const [targetResult, routeResult, portfolioResult, attemptResult] = results
    if (targetResult.status === 'fulfilled') targets.value = targetResult.value.items || []
    if (routeResult.status === 'fulfilled') routes.value = routeResult.value.items || []
    if (portfolioResult.status === 'fulfilled') portfolios.value = portfolioResult.value.items || []
    if (attemptResult.status === 'fulfilled') attempts.value = attemptResult.value.items || []

    const failedLabels = ['通知目标', '报告路由', '策略组合', '投递历史'].filter((_, index) => results[index].status === 'rejected')
    if (failedLabels.length) {
      noticeState.value = noticeState.value === 'error' || failedLabels.length === results.length ? 'error' : 'partial'
      const refreshMessage = `${failedLabels.join('、')}读取失败；已返回内容保持可用。`
      message.value = preserveNotice && message.value ? `${message.value} ${refreshMessage}` : refreshMessage
    }
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function load() {
  return loadData(false)
}

async function addTarget() {
  try {
    await api.post('/api/decisions/targets', form.value)
    form.value = { channel: 'wecom_robot', label: '', secret_ref: '', endpoint_ref: '' }
    noticeState.value = 'success'
    message.value = '目标已保存，仍需完成受控测试。'
    await loadData(true)
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '目标保存失败'
  }
}

async function testTarget(id: string) {
  try {
    const queued = await api.post<{ command_id: string }>(`/api/decisions/targets/${id}/test`, {})
    const command = await api.waitDecisionCommand<any>(queued.command_id)
    const resultStatus = String(command.result?.status || command.status || '')
    const failed = ['failed', 'rejected', 'timeout', 'cancelled'].includes(String(command.status)) || resultStatus === 'failed'
    noticeState.value = failed ? 'error' : resultStatus === 'external_test_required' ? 'partial' : 'success'
    message.value = command.result?.message || command.result?.error || (failed ? '渠道测试失败' : resultStatus === 'passed' ? '渠道测试通过' : '渠道测试已完成')
    await loadData(true)
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '测试失败'
  }
}

async function addRoute() {
  try {
    await api.post('/api/decisions/routes', routeForm.value)
    noticeState.value = 'success'
    message.value = '路由已保存。'
    await loadData(true)
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '路由保存失败'
  }
}

function targetLabel(targetId: string) {
  return targets.value.find((target) => target.id === targetId)?.label || targetId
}

function portfolioLabel(portfolioId: string) {
  return portfolios.value.find((portfolio) => portfolio.id === portfolioId)?.name || portfolioId
}

function targetTestClass(status: string) {
  return status === 'passed' ? 'good' : status === 'failed' ? 'bad' : 'warn'
}

function targetTestLabel(status: string) {
  return ({ passed: '测试通过', failed: '测试失败', external_test_required: '需外部测试', not_tested: '尚未测试' } as Record<string, string>)[status] || '尚未测试'
}

function eventTypeLabel(eventType: string) {
  return ({ scheduled: '定时报告', state_change: '状态变化', major_risk: '首次重大风险' } as Record<string, string>)[eventType] || eventType
}

function attemptClass(status: string) {
  if (status === 'delivered') return 'good'
  if (['failed', 'dead'].includes(status)) return 'bad'
  return 'warn'
}

function attemptLabel(status: string) {
  return ({
    delivered: '已投递', retryable: '等待重试', failed: '投递失败', dead: '已进入死信', unknown: '结果未知',
    dispatching: '投递中', blocked_no_route: '缺少路由', blocked_target: '目标阻断',
    blocked_external: '外部投递关闭', blocked_eligibility: '资格阻断',
  } as Record<string, string>)[status] || status || '未知状态'
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div><h1>通知路由</h1><p>摘要发送到企业微信、个人微信服务、飞书或 QQ；完整报告通过短期只读链接打开。凭证只使用受保护引用。</p></div>
      <div class="head-actions"><RefreshIndicator :state="refreshing ? 'refreshing' : targets.length || routes.length ? 'live' : 'unavailable'" :label="refreshing ? '保留配置，正在刷新' : '投递配置'" /><span class="tag warn"><ShieldCheck :size="14" />外部投递默认关闭</span><button class="button" :disabled="loading" type="button" @click="load"><RefreshCw :size="15" />刷新</button></div>
    </div>
    <AsyncState
      v-if="message"
      :state="noticeState || 'error'"
      :title="noticeState === 'success' ? '操作完成' : noticeState === 'partial' ? '部分可用' : '操作失败'"
      :message="message"
      @retry="load"
    />

    <div class="delivery-summary" aria-label="投递状态摘要">
      <div><span>已投递</span><strong>{{ attemptSummary.delivered }}</strong></div>
      <div><span>策略阻断</span><strong>{{ attemptSummary.blocked }}</strong></div>
      <div><span>待复核</span><strong>{{ attemptSummary.review }}</strong></div>
      <div><span>失败 / 死信</span><strong>{{ attemptSummary.failed }}</strong></div>
    </div>

    <div class="section-grid two notification-config-grid">
      <section class="panel">
        <div class="panel-head"><div><h2>通知目标</h2><p>每个渠道独立测试、失败计数和停用。</p></div><Bell :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="field-grid">
            <div class="field"><label for="notification-channel">渠道</label><select id="notification-channel" v-model="form.channel"><option value="wecom_robot">企业微信机器人</option><option value="pushplus">PushPlus 个人微信</option><option value="feishu_robot">飞书群机器人</option><option value="qq_official_bot">QQ 官方机器人</option></select></div>
            <div class="field"><label for="notification-label">显示名称</label><input id="notification-label" v-model="form.label" placeholder="例如 盘前企业微信" /></div>
            <div class="field"><label for="notification-secret">密钥引用</label><input id="notification-secret" v-model="form.secret_ref" autocomplete="off" placeholder="env://QUANT_CHANNEL_SECRET" /></div>
            <div class="field"><label for="notification-endpoint">端点引用</label><input id="notification-endpoint" v-model="form.endpoint_ref" autocomplete="off" placeholder="env://WECHAT_WEBHOOK_URL" /></div>
          </div>
          <div class="form-actions"><button class="button primary" :disabled="!form.label || !form.secret_ref" @click="addTarget"><Plus :size="15" />保存目标</button></div>
        </div>
        <div v-if="!targets.length" class="panel-body"><div class="empty">尚未配置渠道。保存后仍不能自动推送，直到测试通过。</div></div>
        <div v-for="target in targets" :key="target.id" class="report-card notification-row">
          <div class="notification-row-copy"><strong>{{ target.label }}</strong><div class="report-meta"><span>{{ target.channel }}</span><span class="tag" :class="targetTestClass(target.test_status)">{{ targetTestLabel(target.test_status) }}</span><span>失败 {{ target.failure_count || 0 }} 次</span><span>{{ target.enabled ? '已启用' : '已停用' }}</span></div></div><button class="button" type="button" :disabled="loading" @click="testTarget(target.id)"><Send :size="14" />测试</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head"><div><h2>报告路由</h2><p>按组合和事件类型分发，不参与动作计算。</p></div><Link2 :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="field-grid"><div class="field"><label for="notification-portfolio">策略组合</label><select id="notification-portfolio" v-model="routeForm.portfolio_id"><option value="">选择组合</option><option v-for="item in portfolios" :key="item.id" :value="item.id">{{ item.name }}</option></select></div><div class="field"><label for="notification-target">通知目标</label><select id="notification-target" v-model="routeForm.target_id"><option value="">选择目标</option><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.label }}</option></select></div><div class="field"><label for="notification-event">事件类型</label><select id="notification-event" v-model="routeForm.event_type"><option value="scheduled">定时报告</option><option value="state_change">状态变化</option><option value="major_risk">首次重大风险</option></select></div></div>
          <div class="form-actions"><button class="button primary" :disabled="!routeForm.portfolio_id || !routeForm.target_id" @click="addRoute"><Plus :size="15" />保存路由</button></div>
        </div>
        <div v-if="!routes.length" class="panel-body"><div class="empty">暂无路由。</div></div>
        <div v-for="item in routes" :key="item.id" class="report-card notification-row"><div class="notification-row-copy"><strong>{{ portfolioLabel(item.portfolio_id) }}</strong><div class="report-meta"><span>{{ eventTypeLabel(item.event_type) }}</span><span>{{ targetLabel(item.target_id) }}</span></div></div><span class="tag" :class="item.enabled ? 'good' : 'warn'">{{ item.enabled ? '已启用' : '已停用' }}</span></div>
      </section>
    </div>

    <section class="panel delivery-ledger">
      <div class="panel-head"><div><h2>发送历史与失败队列</h2><p>每一次投递尝试都可审计；失败、阻断和死信不会被展示成“已发送”。</p></div><History :size="18" class="faint" /></div>
      <div v-if="!attempts.length" class="panel-body"><div class="empty"><strong>暂无投递尝试</strong><span>启用外部渠道前，系统只会在这里记录受控阻断原因。</span></div></div>
      <div v-else class="delivery-attempt-list"><article v-for="attempt in attempts.slice(0, 50)" :key="attempt.id" class="delivery-attempt-row"><div class="delivery-attempt-main"><strong>{{ targetLabel(attempt.target_id) }}</strong><div class="report-meta"><span>报告 {{ attempt.report_id }}</span><span>第 {{ attempt.attempt_no }} 次</span><span>{{ attempt.created_at }}</span></div><p v-if="attempt.error" class="delivery-error">{{ attempt.error }}</p><p v-if="attempt.response_summary" class="delivery-response">渠道响应：{{ attempt.response_summary }}</p></div><span class="tag" :class="attemptClass(attempt.status)"><CircleAlert v-if="attempt.status !== 'delivered'" :size="13" />{{ attemptLabel(attempt.status) }}</span></article></div>
    </section>
  </section>
</template>

<style scoped>
.delivery-summary { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); margin:18px 0; border:1px solid var(--color-line); background:var(--color-surface); }
.delivery-summary > div { display:grid; gap:5px; min-width:0; padding:14px 16px; border-right:1px solid var(--color-line); }
.delivery-summary > div:last-child { border-right:0; }
.delivery-summary span { color:var(--color-ink-soft); font-size:12px; }
.delivery-summary strong { font:600 21px/1 var(--font-family-mono); font-variant-numeric:tabular-nums; }
.notification-config-grid { align-items:start; }
.notification-row { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.notification-row-copy { min-width:0; }
.notification-row-copy > strong { display:block; overflow-wrap:anywhere; }
.delivery-ledger { margin-top:18px; }
.delivery-attempt-list { display:grid; }
.delivery-attempt-row { display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:start; gap:12px; padding:14px 18px; border-bottom:1px solid var(--color-line); }
.delivery-attempt-row:last-child { border-bottom:0; }
.delivery-attempt-main { min-width:0; }
.delivery-attempt-main > strong { font-size:13px; }
.delivery-error, .delivery-response { margin:7px 0 0; overflow-wrap:anywhere; color:var(--color-ink-soft); font-size:12px; line-height:1.5; }
.delivery-error { color:var(--color-danger-strong); }
.delivery-response { font-family:var(--font-family-mono); font-size:11px; }
@media (max-width:767px) {
  .delivery-summary { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .delivery-summary > div { border-bottom:1px solid var(--color-line); }
  .delivery-summary > div:nth-child(2n) { border-right:0; }
  .delivery-summary > div:nth-last-child(-n + 2) { border-bottom:0; }
  .notification-row { align-items:stretch; flex-direction:column; }
  .notification-row > .button { width:100%; }
  .delivery-attempt-row { grid-template-columns:1fr; padding:14px 15px; }
  .delivery-attempt-row > .tag { justify-self:start; }
}
@media (max-width:360px) {
  .delivery-summary { grid-template-columns:1fr; }
  .delivery-summary > div { border-right:0; border-bottom:1px solid var(--color-line); }
  .delivery-summary > div:nth-last-child(-n + 2) { border-bottom:1px solid var(--color-line); }
  .delivery-summary > div:last-child { border-bottom:0; }
}
</style>
