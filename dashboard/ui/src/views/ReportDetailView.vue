<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Ban, CheckCircle2, CircleAlert, Copy, Download, ExternalLink, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../api/client'
import type { DecisionReport } from '../types'
import AsyncState from '../components/base/AsyncState.vue'

 type ReportAttempt = Record<string, unknown>
 type ReportRow = DecisionReport & { share_link_id?: string; share_created_at?: string; share_revoked?: boolean }

const route = useRoute()
const report = ref<ReportRow | null>(null)
const attempts = ref<ReportAttempt[]>([])
const loading = ref(false)
const sharing = ref(false)
const revoking = ref(false)
const error = ref('')
const notice = ref('')

const reportId = computed(() => String(route.params.id || '').trim())
const shareState = computed<'none' | 'active' | 'expired' | 'revoked'>(() => {
  if (!report.value?.share_url && !report.value?.share_link_id) return 'none'
  if (report.value.share_revoked) return 'revoked'
  const expiresAt = report.value.share_expires_at ? Date.parse(report.value.share_expires_at) : NaN
  return Number.isFinite(expiresAt) && expiresAt <= Date.now() ? 'expired' : 'active'
})
const deliverySummary = computed(() => ({
  delivered: attempts.value.filter((attempt) => attempt.status === 'delivered').length,
  blocked: attempts.value.filter((attempt) => String(attempt.status || '').startsWith('blocked_')).length,
  review: attempts.value.filter((attempt) => ['retryable', 'unknown', 'dispatching'].includes(String(attempt.status))).length,
  failed: attempts.value.filter((attempt) => ['failed', 'dead'].includes(String(attempt.status))).length,
}))

const decisionRows = computed(() => Array.isArray(report.value?.body?.decisions) ? report.value.body.decisions : [])
const hasDecisionRows = computed(() => decisionRows.value.length > 0)
const decisionCount = computed(() => report.value?.body?.decisions == null ? '—' : decisionRows.value.length)

function shortHash(value: unknown, length = 16) {
  const text = String(value || '')
  return text ? `${text.slice(0, length)}…` : '不可用'
}

function statusLabel(value: unknown) {
  return ({
    passed: '验证通过', failed: '验证未通过', eligible: '具备资格', blocked: '资格阻断',
    not_run: '尚未验证', not_checked: '尚未检查', available: '已生成', not_available: '未生成',
  } as Record<string, string>)[String(value || '')] || String(value || '不可用')
}

function attemptLabel(value: unknown) {
  return ({
    delivered: '已投递', retryable: '等待重试', failed: '投递失败', dead: '已进入死信', unknown: '结果未知',
    dispatching: '投递中', blocked_no_route: '缺少路由', blocked_target: '目标阻断',
    blocked_external: '外部投递关闭', blocked_eligibility: '资格阻断',
  } as Record<string, string>)[String(value || '')] || String(value || '未知状态')
}

function attemptClass(value: unknown) {
  const status = String(value || '')
  return status === 'delivered' ? 'good' : ['failed', 'dead'].includes(status) ? 'bad' : 'warn'
}

function scoreLabel(value: unknown) {
  const score = Number(value)
  return Number.isFinite(score)
    ? score.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })
    : '不可判断'
}

function reportTitle(value: unknown) {
  return value === 'preview' ? '预览报告' : value === 'manual' ? '手动研究报告' : '决策报告'
}

async function load() {
  if (!reportId.value) {
    error.value = '报告 ID 不可用'
    return
  }
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const loadedReport = await api.get<ReportRow>(`/api/decisions/reports/${encodeURIComponent(reportId.value)}`)
    report.value = {
      ...loadedReport,
      share_link_id: loadedReport.share_link?.id,
      share_created_at: loadedReport.share_link?.created_at,
      share_expires_at: loadedReport.share_link?.expires_at,
      share_revoked: Boolean(loadedReport.share_link?.revoked),
    }
    try {
      const deliveryResult = await api.get<{ items: ReportAttempt[] }>(`/api/decisions/reports/${encodeURIComponent(reportId.value)}/deliveries`)
      attempts.value = deliveryResult.items || []
    } catch {
      attempts.value = []
      notice.value = '投递审计暂不可用，报告内容仍可查看。'
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告读取失败'
  } finally {
    loading.value = false
  }
}

async function copyToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // Fall through when browser permissions deny the async clipboard API.
    }
  }
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    return document.execCommand('copy')
  } finally {
    textarea.remove()
  }
}

async function share() {
  if (!report.value) return
  sharing.value = true
  try {
    const response = await api.post<{ url: string; link?: { id?: string; created_at?: string; expires_at?: string } }>(`/api/decisions/reports/${encodeURIComponent(report.value.id)}/share`, {})
    report.value.share_url = new URL(response.url, window.location.origin).toString()
    report.value.share_link_id = response.link?.id
    report.value.share_created_at = response.link?.created_at
    report.value.share_expires_at = response.link?.expires_at
    report.value.share_revoked = false
    notice.value = report.value.share_url && await copyToClipboard(report.value.share_url) ? '分享链接已复制。' : '分享链接已生成。'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '分享链接生成失败'
  } finally {
    sharing.value = false
  }
}

async function revokeShare() {
  if (!report.value?.share_link_id || shareState.value !== 'active') return
  if (!window.confirm('撤销后，已发出的分享链接将立即失效。继续吗？')) return
  revoking.value = true
  try {
    await api.revokeShareLink(report.value.share_link_id)
    report.value.share_revoked = true
    notice.value = '分享链接已撤销。'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '分享链接撤销失败'
  } finally {
    revoking.value = false
  }
}

watch(reportId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="report-detail-view">
    <div class="page-head">
      <div>
        <RouterLink class="muted small report-detail-back" to="/app/reports"><ArrowLeft :size="14" />返回报告审计</RouterLink>
        <h1>{{ report ? reportTitle(report.report_type) : '报告详情' }}</h1>
        <p>认证报告详情保留冻结输入、确定性结果、验证、资格、AI 补充件和投递审计。</p>
      </div>
      <div class="head-actions"><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button><a v-if="report" class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}`" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15" />原始 JSON</a></div>
    </div>

    <AsyncState v-if="error" state="error" :message="error" @retry="load" />
    <AsyncState v-if="notice" state="success" :message="notice" />

    <template v-if="report">
      <section class="report-detail-hero panel">
        <div class="report-detail-hero-main"><span class="eyebrow">FROZEN REPORT / AUTHENTICATED</span><h2>{{ reportTitle(report.report_type) }}</h2><p>报告 hash {{ shortHash(report.report_hash) }} · 输入 hash {{ shortHash(report.body?.input_hash) }} · 生成于 {{ report.created_at || '不可用' }}</p></div>
        <div class="report-detail-hero-actions"><span class="tag" :class="report.body?.eligibility?.status === 'eligible' ? 'good' : 'warn'">{{ statusLabel(report.body?.eligibility?.status) }}</span><button class="button primary" type="button" :disabled="sharing || revoking" @click="share"><Copy :size="15" />{{ sharing ? '生成中' : shareState === 'none' ? '分享' : '重新分享' }}</button><button v-if="shareState === 'active' && report.share_link_id" class="button danger" type="button" :disabled="revoking" @click="revokeShare"><Ban :size="15" />{{ revoking ? '撤销中' : '撤销分享' }}</button></div>
      </section>

      <div class="report-detail-summary" aria-label="报告状态摘要">
        <div><span>数据</span><strong>{{ report.body?.quality_status || 'unknown' }}</strong></div>
        <div><span>验证</span><strong>{{ statusLabel(report.body?.validation?.status) }}</strong></div>
        <div><span>资格</span><strong>{{ statusLabel(report.body?.eligibility?.status) }}</strong></div>
        <div><span>决策</span><strong>{{ decisionCount }}</strong></div>
        <div><span>已投递</span><strong>{{ deliverySummary.delivered }}</strong></div>
      </div>

      <section class="section-grid two report-detail-grid">
        <section class="panel"><div class="panel-head"><div><h2>冻结输入</h2><p>报告由不可变输入、策略版本和数据质量共同生成。</p></div><ShieldCheck :size="18" class="faint" /></div><div class="panel-body report-detail-facts"><div><span>组合</span><strong>{{ report.body?.portfolio_id || '不可用' }}</strong></div><div><span>市场</span><strong>{{ report.body?.market || '不可用' }}</strong></div><div><span>策略版本</span><strong>{{ report.body?.portfolio_version_id || '不可用' }}</strong></div><div><span>来源</span><strong>{{ report.body?.source || '不可用' }}</strong></div><div><span>AI</span><strong>{{ statusLabel(report.ai_commentary_status) }}</strong></div><div><span>分享</span><strong>{{ shareState === 'active' ? '有效' : shareState === 'revoked' ? '已撤销' : shareState === 'expired' ? '已过期' : '未生成' }}</strong></div></div></section>
        <section class="panel"><div class="panel-head"><div><h2>验证与资格</h2><p>研究结果、资格状态和阻断原因分开表达。</p></div><CheckCircle2 :size="18" class="faint" /></div><div class="panel-body"><div class="detail-status-row"><span>验证</span><span class="tag" :class="report.body?.validation?.status === 'passed' ? 'good' : 'warn'">{{ statusLabel(report.body?.validation?.status) }}</span></div><div class="detail-status-row"><span>自动推送资格</span><span class="tag" :class="report.body?.eligibility?.status === 'eligible' ? 'good' : 'warn'">{{ statusLabel(report.body?.eligibility?.status) }}</span></div><div v-if="report.body?.eligibility?.reasons?.length" class="detail-reasons"><strong>阻断原因</strong><span v-for="reason in report.body.eligibility.reasons" :key="reason"><CircleAlert :size="14" />{{ reason }}</span></div><div v-else class="empty compact-empty">没有额外阻断原因。</div></div></section>
      </section>

      <section class="panel report-decision-list"><div class="panel-head"><div><h2>确定性决策</h2><p>动作、有效性、风险否决和原因码来自冻结报告。</p></div><span class="tag">{{ decisionCount }} 项</span></div><div v-if="!hasDecisionRows" class="panel-body"><div class="empty">报告没有决策明细。</div></div><div v-else class="report-decision-rows"><article v-for="decision in decisionRows" :key="decision.id" class="report-decision-row"><div><strong>{{ decision.symbol || '未标的' }}</strong><span>{{ decision.action || '不可判断' }}</span></div><div class="report-decision-meta"><span>分数 {{ scoreLabel(decision.score) }}</span><span>{{ decision.valid ? '有效' : '无效' }}</span><span>风险否决 {{ decision.risk_veto ? '命中' : '未命中' }}</span><small>{{ decision.reason_codes?.join('、') || '无额外原因码' }}</small></div></article></div></section>

      <section class="section-grid two report-detail-grid">
        <section class="panel"><div class="panel-head"><div><h2>AI 研究解释</h2><p>AI 只作为独立补充件，不改变确定性决策或资格。</p></div></div><div class="panel-body"><div v-if="!report.ai_commentary?.length" class="empty">没有 AI 补充件。</div><div v-else class="detail-commentary"><article v-for="(item, index) in report.ai_commentary" :key="index"><strong>{{ item.model || 'AI' }}</strong><p>{{ item.content || '无补充内容' }}</p></article></div></div></section>
        <section class="panel"><div class="panel-head"><div><h2>投递审计</h2><p>报告生成不等于通知已发送。</p></div></div><div class="panel-body"><div class="detail-delivery-summary"><span>已投递 {{ deliverySummary.delivered }}</span><span>阻断 {{ deliverySummary.blocked }}</span><span>待复核 {{ deliverySummary.review }}</span><span>失败 {{ deliverySummary.failed }}</span></div><div v-if="!attempts.length" class="empty compact-empty">没有投递尝试。</div><div v-else class="detail-attempts"><div v-for="attempt in attempts" :key="String(attempt.id)" class="detail-attempt"><div><strong>{{ attempt.target_id || '通知目标' }}</strong><small>{{ attempt.created_at || '' }} · 第 {{ attempt.attempt_no || 1 }} 次</small></div><span class="tag" :class="attemptClass(attempt.status)">{{ attemptLabel(attempt.status) }}</span></div></div></div></section>
      </section>

      <div class="report-detail-exports"><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=json`" download><Download :size="15" />JSON</a><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=markdown`" download><Download :size="15" />Markdown</a><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=pdf`" download><Download :size="15" />PDF</a><a v-if="shareState === 'active' && report.share_url" class="button ghost" :href="report.share_url" target="_blank" rel="noopener noreferrer">打开分享页</a></div>
    </template>
  </section>
</template>

<style scoped>
.report-detail-back { display:inline-flex; align-items:center; gap:5px; margin-bottom:9px; }
.report-detail-hero { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:18px; padding:20px; }
.report-detail-hero-main { min-width:0; }
.report-detail-hero-main h2 { margin:8px 0 6px; font-size:20px; }
.report-detail-hero-main p { margin:0; overflow-wrap:anywhere; color:var(--color-ink-soft); font:11px/1.5 var(--font-family-mono); }
.report-detail-hero-actions { display:flex; align-items:center; justify-content:flex-end; gap:7px; flex-wrap:wrap; }
.report-detail-summary { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); margin-bottom:18px; border:1px solid var(--color-line); background:var(--color-surface); }
.report-detail-summary > div { display:grid; gap:5px; min-width:0; padding:14px 16px; border-right:1px solid var(--color-line); }
.report-detail-summary > div:last-child { border-right:0; }
.report-detail-summary span { color:var(--color-ink-soft); font-size:12px; }
.report-detail-summary strong { overflow:hidden; font:600 16px/1.2 var(--font-family-mono); text-overflow:ellipsis; white-space:nowrap; }
.report-detail-grid { margin-bottom:18px; }
.report-detail-facts { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.report-detail-facts > div { min-width:0; }
.report-detail-facts span, .detail-status-row > span:first-child { display:block; color:var(--color-ink-faint); font-size:11px; }
.report-detail-facts strong { display:block; margin-top:4px; overflow-wrap:anywhere; color:var(--color-ink-soft); font:11px/1.45 var(--font-family-mono); }
.detail-status-row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 0; border-bottom:1px solid var(--color-line); }
.detail-reasons { display:grid; gap:7px; margin-top:14px; color:var(--color-danger-strong); font-size:12px; }
.detail-reasons strong { color:var(--color-ink); }
.detail-reasons span { display:flex; align-items:flex-start; gap:6px; overflow-wrap:anywhere; }
.compact-empty { margin:0; padding:16px 8px; border:0; }
.report-decision-list { margin-bottom:18px; }
.report-decision-rows { display:grid; }
.report-decision-row { display:grid; grid-template-columns:minmax(140px, .4fr) minmax(0, 1fr); gap:18px; padding:14px 18px; border-bottom:1px solid var(--color-line); }
.report-decision-row:last-child { border-bottom:0; }
.report-decision-row > div:first-child { display:grid; gap:4px; }
.report-decision-row strong { font-size:13px; }
.report-decision-row > div:first-child span { color:var(--color-ink-soft); font-size:12px; }
.report-decision-meta { display:flex; flex-wrap:wrap; align-items:center; gap:6px 12px; color:var(--color-ink-soft); font-size:11px; }
.report-decision-meta small { flex:1 1 100%; overflow-wrap:anywhere; color:var(--color-ink-faint); }
.detail-commentary { display:grid; gap:10px; }
.detail-commentary article { padding:11px 12px; border:1px solid var(--color-ai-border); background:var(--color-ai-bg); }
.detail-commentary p { margin:6px 0 0; white-space:pre-wrap; overflow-wrap:anywhere; color:var(--color-ink-soft); font-size:12px; line-height:1.6; }
.detail-delivery-summary { display:flex; flex-wrap:wrap; gap:7px 12px; margin-bottom:12px; color:var(--color-ink-soft); font-size:11px; }
.detail-attempts { display:grid; }
.detail-attempt { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; padding:10px 0; border-bottom:1px solid var(--color-line); }
.detail-attempt:last-child { border-bottom:0; }
.detail-attempt strong, .detail-attempt small { display:block; }
.detail-attempt strong { font-size:12px; }
.detail-attempt small { margin-top:3px; color:var(--color-ink-faint); font-size:10px; }
.report-detail-exports { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
@media (max-width:767px) {
  .report-detail-hero { flex-direction:column; padding:15px; }
  .report-detail-hero-actions { justify-content:flex-start; width:100%; }
  .report-detail-hero-actions .button { flex:1 1 auto; }
  .report-detail-summary { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .report-detail-summary > div:nth-child(2n) { border-right:0; }
  .report-detail-summary > div { border-bottom:1px solid var(--color-line); }
  .report-detail-summary > div:nth-last-child(-n + 2) { border-bottom:0; }
  .report-detail-grid { grid-template-columns:1fr; }
  .report-decision-row { grid-template-columns:1fr; gap:8px; padding:14px 15px; }
  .report-detail-exports > .button { flex:1 1 calc(50% - 8px); }
}
@media (max-width:360px) {
  .report-detail-summary { grid-template-columns:1fr; }
  .report-detail-summary > div, .report-detail-summary > div:nth-child(2n), .report-detail-summary > div:nth-last-child(-n + 2) { border-right:0; border-bottom:1px solid var(--color-line); }
  .report-detail-summary > div:last-child { border-bottom:0; }
}
</style>
