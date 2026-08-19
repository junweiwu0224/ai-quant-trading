<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Ban, ChevronDown, Copy, ExternalLink, RefreshCw } from 'lucide-vue-next'
import { api } from '../api/client'
import type { DecisionReport, DecisionShareResponse } from '../types'
import RefreshIndicator from '../components/base/RefreshIndicator.vue'
import AsyncState from '../components/base/AsyncState.vue'

type ShareLink = { id?: string; expires_at?: string; created_at?: string; revoked?: boolean }
type ReportRow = DecisionReport & { share_link_id?: string; share_created_at?: string; share_revoked?: boolean }
type ShareResponse = DecisionShareResponse & { link?: ShareLink }

const reports = ref<ReportRow[]>([])
const deliveryAttempts = ref<any[]>([])
const loading = ref(false)
const refreshing = ref(false)
const sharingId = ref<string | null>(null)
const revokingId = ref<string | null>(null)
const message = ref('')
const noticeState = ref<'success' | 'partial' | 'error' | ''>('')
const expandedReportId = ref<string | null>(null)

const deliveredCount = computed(() => reports.value.filter((report) => latestDeliveryStatus(report.id) === 'delivered').length)

function shortHash(hash: string | undefined, length = 12) {
  return hash ? `${hash.slice(0, length)}…` : '不可用'
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

async function load() {
  loading.value = true
  refreshing.value = reports.value.length > 0 || deliveryAttempts.value.length > 0
  message.value = ''
  noticeState.value = ''
  try {
    const [reportResult, deliveryResult] = await Promise.allSettled([
      api.get<{ items: DecisionReport[] }>('/api/decisions/reports'),
      api.get<{ items: any[] }>('/api/decisions/delivery-attempts'),
    ])
    if (reportResult.status === 'fulfilled') reports.value = (reportResult.value.items || []).map((report) => ({
      ...report,
      share_link_id: report.share_link?.id,
      share_created_at: report.share_link?.created_at,
      share_expires_at: report.share_link?.expires_at,
      share_revoked: Boolean(report.share_link?.revoked),
    }))
    if (deliveryResult.status === 'fulfilled') deliveryAttempts.value = deliveryResult.value.items || []
    if (reportResult.status === 'rejected') {
      noticeState.value = 'error'
      message.value = reportResult.reason instanceof Error ? reportResult.reason.message : '报告加载失败'
    } else if (deliveryResult.status === 'rejected') {
      noticeState.value = 'partial'
      message.value = deliveryResult.reason instanceof Error ? `投递历史加载失败：${deliveryResult.reason.message}` : '投递历史加载失败'
    }
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '报告加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function latestDeliveryStatus(reportId: string) {
  return deliveryAttempts.value.find((attempt) => attempt.report_id === reportId)?.status || '未投递'
}

function deliveryClass(reportId: string) {
  const status = latestDeliveryStatus(reportId)
  return status === 'delivered' ? 'good' : ['failed', 'dead'].includes(status) ? 'bad' : status === '未投递' ? '' : 'warn'
}

async function share(report: DecisionReport) {
  sharingId.value = report.id
  try {
    const data = await api.post<DecisionShareResponse>(`/api/decisions/reports/${encodeURIComponent(report.id)}/share`, {})
    const share = data as ShareResponse
    const publicUrl = new URL(data.url, window.location.origin).toString()
    const row = report as ReportRow
    report.share_url = publicUrl
    report.share_expires_at = share.link?.expires_at
    row.share_link_id = share.link?.id
    row.share_created_at = share.link?.created_at
    row.share_revoked = Boolean(share.link?.revoked)
    noticeState.value = 'success'
    message.value = (await copyToClipboard(publicUrl)) ? '完整报告链接已复制' : '分享链接已生成，请点击打开分享页或复制链接'
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '分享链接生成失败'
  } finally {
    sharingId.value = null
  }
}

function shareState(report: ReportRow): 'none' | 'active' | 'expired' | 'revoked' {
  if (!report.share_url && !report.share_link_id) return 'none'
  if (report.share_revoked) return 'revoked'
  const expiresAt = report.share_expires_at ? Date.parse(report.share_expires_at) : NaN
  return Number.isFinite(expiresAt) && expiresAt <= Date.now() ? 'expired' : 'active'
}

function shareStateLabel(report: ReportRow) {
  return ({ none: '未生成', active: '有效', expired: '已过期', revoked: '已撤销' })[shareState(report)]
}

function deliveryLabel(reportId: string) {
  const status = latestDeliveryStatus(reportId)
  return ({
    delivered: '已投递', retryable: '等待重试', failed: '投递失败', dead: '已进入死信', unknown: '结果未知',
    dispatching: '投递中', blocked_no_route: '缺少路由', blocked_target: '目标阻断',
    blocked_external: '外部投递关闭', blocked_eligibility: '资格阻断',
  } as Record<string, string>)[status] || status
}

function shareStateClass(report: ReportRow) {
  return ({ none: '', active: 'good', expired: 'warn', revoked: 'bad' })[shareState(report)]
}

async function revokeShare(report: ReportRow) {
  if (!report.share_link_id || shareState(report) !== 'active') {
    noticeState.value = 'error'
    message.value = '当前分享链接没有可用的撤销入口，请重新生成链接'
    return
  }
  if (typeof window.confirm === 'function' && !window.confirm('撤销后，已发出的分享链接将立即失效。继续吗？')) return
  revokingId.value = report.id
  try {
    await api.revokeShareLink(report.share_link_id)
    report.share_revoked = true
    noticeState.value = 'success'
    message.value = '分享链接已撤销'
  } catch (error) {
    noticeState.value = 'error'
    message.value = error instanceof Error ? error.message : '分享链接撤销失败'
  } finally {
    revokingId.value = null
  }
}

async function copyShareUrl(report: DecisionReport) {
  const row = report as ReportRow
  if (!row.share_url || shareState(row) !== 'active') {
    noticeState.value = 'error'
    message.value = '当前分享链接已失效，不能复制'
    return
  }
  const copied = await copyToClipboard(row.share_url)
  noticeState.value = copied ? 'success' : 'error'
  message.value = copied ? '完整报告链接已复制' : '复制失败，请使用打开分享页'
}

function toggleDetails(reportId: string) {
  expandedReportId.value = expandedReportId.value === reportId ? null : reportId
}

onMounted(load)
</script>

<template>
  <section class="reports-workbench">
    <div class="page-head">
      <div><h1>报告与投递审计</h1><p>报告生成、分享和投递是独立状态。只有投递记录成功，才代表通知已经发出。</p></div>
      <div class="head-actions"><RefreshIndicator :state="refreshing ? 'refreshing' : reports.length ? 'live' : 'unavailable'" :label="refreshing ? '保留报告，正在刷新' : '报告索引'" /><button class="button" :disabled="loading" type="button" @click="load"><RefreshCw :size="16" />刷新</button></div>
    </div>

    <div class="report-ledger-summary" aria-label="报告审计摘要">
      <div><span>报告</span><strong>{{ reports.length }}</strong></div>
      <div><span>已投递</span><strong>{{ deliveredCount }}</strong></div>
      <div><span>待处理</span><strong>{{ reports.length - deliveredCount }}</strong></div>
    </div>

    <AsyncState
      v-if="message"
      :state="noticeState || 'error'"
      :title="noticeState === 'success' ? '操作完成' : noticeState === 'partial' ? '部分可用' : '报告操作失败'"
      :message="message"
      @retry="load"
    />

    <section class="panel report-ledger">
      <div class="panel-head"><div><h2>冻结报告</h2><p>每行可回溯输入 hash、数据状态、验证状态、AI artifact 和投递审计。</p></div><span class="tag">{{ reports.length }} 份</span></div>
      <div v-if="!reports.length" class="panel-body"><div class="empty"><strong>还没有报告</strong><span>从决策中心完成一次预览或手动分析。</span></div></div>
      <div v-else class="report-table-wrap report-table-desktop">
        <table class="report-table">
          <thead><tr><th>报告</th><th>对象与时间</th><th>输入</th><th>数据</th><th>验证</th><th>AI</th><th>决策</th><th>投递</th><th>分享</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <template v-for="report in reports" :key="report.id">
              <tr>
                <td><RouterLink class="report-title" :to="`/app/reports/${encodeURIComponent(report.id)}`">{{ report.report_type === 'preview' ? '预览报告' : report.report_type === 'manual' ? '手动研究报告' : '决策报告' }}</RouterLink><small>{{ report.id }}</small></td>
                <td><span>{{ report.body?.market || '市场未知' }}</span><small>{{ report.created_at }}</small></td>
                <td class="mono">{{ shortHash(report.report_hash) }}</td>
                <td><span class="tag" :class="report.body?.quality_status === 'ok' ? 'good' : 'warn'">{{ report.body?.quality_status || 'unknown' }}</span></td>
                <td><span class="tag" :class="report.body?.validation?.status === 'passed' ? 'good' : report.body?.validation?.status === 'failed' ? 'bad' : 'warn'">{{ report.body?.validation?.status || 'not_run' }}</span></td>
                <td><span class="tag">{{ report.ai_commentary_status || 'not_available' }}</span></td>
                <td class="mono">{{ report.body?.decisions?.length || 0 }}</td>
                <td><span class="tag" :class="deliveryClass(report.id)">{{ deliveryLabel(report.id) }}</span></td>
                <td><span class="tag" :class="shareStateClass(report)">{{ shareStateLabel(report) }}</span></td>
                <td><button class="icon-button compact-icon" type="button" title="展开报告审计详情" aria-label="展开报告审计详情" :aria-expanded="expandedReportId === report.id" @click="toggleDetails(report.id)"><ExternalLink :size="15" /></button></td>
              </tr>
              <tr v-if="expandedReportId === report.id" class="report-detail-row"><td colspan="10"><div class="report-detail-grid"><div><strong>证据包</strong><span>hash {{ shortHash(report.report_hash) }}</span><span>数据 {{ report.body?.quality_status || '不可用' }} · 验证 {{ report.body?.validation?.status || 'not_run' }}</span></div><div class="report-detail-actions"><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=json`" download>JSON</a><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=markdown`" download>Markdown</a><a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=pdf`" download>PDF</a><button class="button" type="button" :disabled="sharingId === report.id || revokingId === report.id" @click="share(report)"><Copy :size="15" />{{ sharingId === report.id ? '生成中' : shareState(report) === 'none' ? '分享' : '重新分享' }}</button></div><div v-if="report.share_url" class="report-detail-actions"><a v-if="shareState(report) === 'active'" class="button ghost" :href="report.share_url" target="_blank" rel="noopener noreferrer">打开分享页</a><button v-if="shareState(report) === 'active'" class="button ghost" type="button" @click="copyShareUrl(report)">复制链接</button><button v-if="report.share_link_id && shareState(report) === 'active'" class="button danger" type="button" :disabled="revokingId === report.id" @click="revokeShare(report)"><Ban :size="15" />{{ revokingId === report.id ? '撤销中' : '撤销分享' }}</button></div></div></td></tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-if="reports.length" class="report-mobile-list" aria-label="移动报告列表">
        <article v-for="report in reports" :key="`mobile-${report.id}`" class="report-mobile-item">
          <div class="report-mobile-summary">
            <button
              class="report-mobile-toggle"
              type="button"
              :aria-expanded="expandedReportId === report.id"
              :aria-controls="`report-mobile-details-${report.id}`"
              @click="toggleDetails(report.id)"
            >
              <span class="report-mobile-heading">
                <strong>{{ report.report_type === 'preview' ? '预览报告' : report.report_type === 'manual' ? '手动研究报告' : '决策报告' }}</strong>
                <small>{{ report.body?.market || '市场未知' }} · {{ report.created_at }}</small>
              </span>
              <ChevronDown class="report-mobile-chevron" :size="18" aria-hidden="true" />
            </button>
            <RouterLink class="report-mobile-open" :to="`/app/reports/${encodeURIComponent(report.id)}`" :aria-label="`打开${report.report_type === 'preview' ? '预览报告' : '决策报告'}详情`"><ExternalLink :size="16" aria-hidden="true" /></RouterLink>
            <span class="report-mobile-statuses">
              <span class="tag" :class="report.body?.quality_status === 'ok' ? 'good' : 'warn'">数据 {{ report.body?.quality_status || 'unknown' }}</span>
              <span class="tag" :class="report.body?.validation?.status === 'passed' ? 'good' : report.body?.validation?.status === 'failed' ? 'bad' : 'warn'">验证 {{ report.body?.validation?.status || 'not_run' }}</span>
              <span class="tag" :class="deliveryClass(report.id)">投递 {{ deliveryLabel(report.id) }}</span>
            </span>
          </div>

          <div v-if="expandedReportId === report.id" :id="`report-mobile-details-${report.id}`" class="report-mobile-details">
            <dl class="report-mobile-facts">
              <div><dt>输入 hash</dt><dd class="mono">{{ shortHash(report.report_hash) }}</dd></div>
              <div><dt>AI artifact</dt><dd>{{ report.ai_commentary_status || 'not_available' }}</dd></div>
              <div><dt>确定性决策</dt><dd class="mono">{{ report.body?.decisions?.length || 0 }}</dd></div>
              <div><dt>分享</dt><dd>{{ shareStateLabel(report) }}</dd></div>
            </dl>
            <div v-if="report.share_url" class="report-mobile-share-meta">
              <span v-if="report.share_created_at">创建于 {{ report.share_created_at }}</span>
              <span v-if="report.share_expires_at">有效期至 {{ report.share_expires_at }}</span>
            </div>
            <div class="report-detail-actions">
              <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=json`" download>JSON</a>
              <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=markdown`" download>Markdown</a>
              <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=pdf`" download>PDF</a>
              <button class="button" type="button" :disabled="sharingId === report.id || revokingId === report.id" @click="share(report)"><Copy :size="15" />{{ sharingId === report.id ? '生成中' : shareState(report) === 'none' ? '分享' : '重新分享' }}</button>
            </div>
            <div v-if="report.share_url && shareState(report) === 'active'" class="report-detail-actions">
              <a class="button ghost" :href="report.share_url" target="_blank" rel="noopener noreferrer">打开分享页</a>
              <button class="button ghost" type="button" @click="copyShareUrl(report)">复制链接</button>
              <button v-if="report.share_link_id" class="button danger" type="button" :disabled="revokingId === report.id" @click="revokeShare(report)"><Ban :size="15" />{{ revokingId === report.id ? '撤销中' : '撤销分享' }}</button>
            </div>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.report-ledger-summary { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); margin-bottom:18px; border:1px solid var(--color-line); background:var(--color-surface); }
.report-ledger-summary > div { display:grid; gap:5px; min-width:0; padding:14px 16px; border-right:1px solid var(--color-line); }
.report-ledger-summary > div:last-child { border-right:0; }
.report-ledger-summary span { color:var(--color-ink-soft); font-size:12px; }
.report-ledger-summary strong { font:600 21px/1 var(--font-family-mono); font-variant-numeric:tabular-nums; }
.report-table-wrap { overflow:auto; }
.report-mobile-list { display:none; }
.report-table { min-width:1080px; }
.report-table th { padding:11px 13px; border-bottom:1px solid var(--color-line); color:var(--color-ink-faint); font-size:11px; font-weight:700; text-align:left; white-space:nowrap; }
.report-table td { padding:13px; border-bottom:1px solid var(--color-line); color:var(--color-ink-soft); font-size:12px; vertical-align:middle; }
.report-table tr:last-child td { border-bottom:0; }
.report-table td small, .report-table td > span:not(.tag) { display:block; margin-top:4px; color:var(--color-ink-faint); font-size:11px; }
.report-title { color:var(--color-ink); font-size:13px; font-weight:650; }
.report-title:hover { color:var(--color-accent-strong); }
.report-detail-row td { padding:0; background:var(--color-surface-muted); }
.report-detail-grid { display:grid; grid-template-columns:minmax(220px, 1fr) auto; gap:12px 20px; padding:14px; }
.report-detail-grid > div:first-child { display:grid; gap:5px; color:var(--color-ink-soft); font-size:12px; }
.report-detail-grid strong { color:var(--color-ink); }
.report-detail-actions { display:flex; flex-wrap:wrap; gap:7px; align-items:center; }
.report-detail-actions .button { min-height:36px; font-size:12px; }
.report-mobile-item { border-bottom:1px solid var(--color-line); }
.report-mobile-item:last-child { border-bottom:0; }
.report-mobile-summary { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:8px 8px; width:100%; min-height:72px; padding:10px 15px; background:transparent; color:var(--color-ink); }
.report-mobile-summary:hover { background:var(--color-surface-muted); }
.report-mobile-toggle { display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:start; gap:10px; min-width:0; min-height:50px; padding:4px 0; border:0; background:transparent; color:inherit; text-align:left; }
.report-mobile-toggle:focus-visible, .report-mobile-open:focus-visible { position:relative; z-index:1; }
.report-mobile-open { display:grid; width:36px; height:36px; place-items:center; align-self:start; border:1px solid var(--color-line); border-radius:var(--radius-sm); color:var(--color-ink-soft); }
.report-mobile-open:hover { border-color:var(--color-accent); color:var(--color-accent-strong); }
.report-mobile-heading { display:grid; min-width:0; gap:5px; }
.report-mobile-heading strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
.report-mobile-heading small { overflow:hidden; color:var(--color-ink-faint); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.report-mobile-chevron { align-self:start; color:var(--color-ink-faint); transition:transform var(--duration-fast) var(--ease-out); }
.report-mobile-toggle[aria-expanded="true"] .report-mobile-chevron { transform:rotate(180deg); color:var(--color-accent-strong); }
.report-mobile-statuses { grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:5px; min-width:0; }
.report-mobile-statuses .tag { font-size:10px; }
.report-mobile-details { display:grid; gap:14px; padding:0 15px 15px; background:var(--color-surface-muted); }
.report-mobile-facts { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px; margin:0; padding-top:14px; }
.report-mobile-facts > div { min-width:0; }
.report-mobile-facts dt { color:var(--color-ink-faint); font-size:10px; }
.report-mobile-facts dd { margin:4px 0 0; overflow:hidden; color:var(--color-ink-soft); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.report-mobile-share-meta { display:grid; gap:4px; color:var(--color-ink-faint); font-size:11px; }
@media (max-width:767px) {
  .report-ledger-summary { grid-template-columns:1fr; }
  .report-ledger-summary > div { grid-template-columns:1fr auto; align-items:baseline; border-right:0; border-bottom:1px solid var(--color-line); }
  .report-ledger-summary > div:last-child { border-bottom:0; }
  .report-table-desktop { display:none; }
  .report-mobile-list { display:block; }
  .report-detail-grid { grid-template-columns:1fr; }
  .report-detail-actions { justify-content:flex-start; }
}
@media (prefers-reduced-motion: reduce) {
  .report-mobile-chevron { transition:none; }
}
</style>
