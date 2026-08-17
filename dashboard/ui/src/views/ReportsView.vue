<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Ban, Copy, ExternalLink, RefreshCw } from 'lucide-vue-next'
import { api } from '../api/client'
import type { DecisionReport, DecisionShareResponse } from '../types'

type ShareLink = { id?: string; expires_at?: string; created_at?: string; revoked?: boolean }
type ReportRow = DecisionReport & { share_link_id?: string; share_created_at?: string; share_revoked?: boolean }
type ShareResponse = DecisionShareResponse & { link?: ShareLink }

const reports = ref<ReportRow[]>([])
const deliveryAttempts = ref<any[]>([])
const loading = ref(false)
const sharingId = ref<string | null>(null)
const revokingId = ref<string | null>(null)
const message = ref('')

function shortHash(hash: string | undefined, length = 12) {
  return hash ? `${hash.slice(0, length)}…` : '不可用'
}

async function copyToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // Fall through to the synchronous browser fallback when clipboard permission is unavailable.
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
  message.value = ''
  try {
    const [reportResult, deliveryResult] = await Promise.allSettled([
      api.get<{ items: DecisionReport[] }>('/api/decisions/reports'),
      api.get<{ items: any[] }>('/api/decisions/delivery-attempts'),
    ])
    if (reportResult.status === 'fulfilled') reports.value = (reportResult.value.items || []) as ReportRow[]
    if (deliveryResult.status === 'fulfilled') deliveryAttempts.value = deliveryResult.value.items || []
    if (reportResult.status === 'rejected') {
      message.value = reportResult.reason instanceof Error ? reportResult.reason.message : '报告加载失败'
    } else if (deliveryResult.status === 'rejected') {
      message.value = deliveryResult.reason instanceof Error ? `投递历史加载失败：${deliveryResult.reason.message}` : '投递历史加载失败'
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '报告加载失败'
  } finally {
    loading.value = false
  }
}

function latestDeliveryStatus(reportId: string) {
  return deliveryAttempts.value.find((attempt) => attempt.report_id === reportId)?.status || '未投递'
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
    message.value = (await copyToClipboard(publicUrl))
      ? '完整报告链接已复制'
      : '分享链接已生成，请点击“打开分享页”或复制链接'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '分享链接生成失败'
  } finally {
    sharingId.value = null
  }
}

function shareState(report: ReportRow): 'none' | 'active' | 'expired' | 'revoked' {
  if (!report.share_url) return 'none'
  if (report.share_revoked) return 'revoked'
  const expiresAt = report.share_expires_at ? Date.parse(report.share_expires_at) : NaN
  return Number.isFinite(expiresAt) && expiresAt <= Date.now() ? 'expired' : 'active'
}

function shareStateLabel(report: ReportRow) {
  return ({ none: '未生成', active: '有效', expired: '已过期', revoked: '已撤销' })[shareState(report)]
}

function shareStateClass(report: ReportRow) {
  return ({ none: 'muted', active: 'good', expired: 'warn', revoked: 'bad' })[shareState(report)]
}

async function revokeShare(report: ReportRow) {
  if (!report.share_link_id || shareState(report) !== 'active') {
    message.value = '当前分享链接没有可用的撤销入口，请重新生成链接'
    return
  }
  if (typeof window.confirm === 'function' && !window.confirm('撤销后，已发出的分享链接将立即失效。继续吗？')) return
  revokingId.value = report.id
  try {
    await api.revokeShareLink(report.share_link_id)
    report.share_revoked = true
    message.value = '分享链接已撤销'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '分享链接撤销失败'
  } finally {
    revokingId.value = null
  }
}

async function copyShareUrl(report: DecisionReport) {
  const row = report as ReportRow
  if (!row.share_url || shareState(row) !== 'active') {
    message.value = '当前分享链接已失效，不能复制'
    return
  }
  message.value = (await copyToClipboard(row.share_url)) ? '完整报告链接已复制' : '复制失败，请使用打开分享页'
}

onMounted(load)
</script>
<template>
  <section>
    <div class="page-head">
      <div><h1>报告索引</h1><p>消息渠道只携带精简摘要；完整内容在独立的手机和桌面阅读页中查看。</p></div>
      <button class="button" :disabled="loading" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </div>
    <div v-if="message" class="error-box" role="status">{{ message }}</div>
    <section class="panel">
      <div class="panel-head"><div><h2>冻结报告</h2><p>每份报告都保留输入 hash、版本 hash 和生成来源。</p></div><span class="tag">{{ reports.length }} 份</span></div>
      <div v-if="!reports.length" class="panel-body"><div class="empty"><strong>还没有报告</strong><span>从决策中心完成一次预览或手动分析。</span></div></div>
      <div v-else>
        <article v-for="report in reports" :key="report.id" class="report-card">
          <div class="report-row">
            <div>
              <a :href="`/api/decisions/reports/${encodeURIComponent(report.id)}`" target="_blank" rel="noopener noreferrer">
                {{ report.report_type === 'preview' ? '预览报告' : report.report_type === 'manual' ? '手动研究报告' : '决策报告' }}
              </a>
              <div class="report-meta">
                <span>生成于 {{ report.created_at }}</span>
                <span>hash {{ shortHash(report.report_hash) }}</span>
                <span>市场 {{ report.body?.market || '不可用' }}</span>
                <span>数据 {{ report.body?.quality_status || '不可用' }}</span>
                <span>验证 {{ report.body?.validation?.status || 'not_run' }}</span>
                <span>AI {{ report.ai_commentary_status || 'not_available' }}</span>
                <span>{{ report.body?.decisions?.length || 0 }} 个决策</span>
                <span>投递 {{ latestDeliveryStatus(report.id) }}</span>
                <span class="tag" :class="shareStateClass(report)">分享 {{ shareStateLabel(report) }}</span>
              </div>
              <div v-if="report.share_url" class="report-meta report-share-actions">
                <span v-if="report.share_created_at">创建于 {{ report.share_created_at }}</span>
                <span v-if="report.share_expires_at">有效期至 {{ report.share_expires_at }}</span>
                <template v-if="shareState(report) === 'active'">
                  <a class="button ghost" :href="report.share_url" target="_blank" rel="noopener noreferrer">打开分享页</a>
                  <button class="button ghost" type="button" @click="copyShareUrl(report)"><Copy :size="15" />复制分享链接</button>
                  <button v-if="report.share_link_id" class="button danger" type="button" :disabled="revokingId === report.id" @click="revokeShare(report)"><Ban :size="15" />{{ revokingId === report.id ? '撤销中' : '撤销分享' }}</button>
                </template>
                <span v-else class="muted">链接已不可访问，可重新生成。</span>
              </div>
              <div class="report-meta">
                <span>证据包：</span>
                <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=json`" download>JSON</a>
                <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=markdown`" download>Markdown</a>
                <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}/export?format=pdf`" download>PDF</a>
              </div>
            </div>
            <div class="head-actions">
              <button class="button" type="button" :disabled="sharingId === report.id || revokingId === report.id" @click="share(report)"><Copy :size="15" />{{ sharingId === report.id ? '生成中' : shareState(report) === 'none' ? '分享' : '重新分享' }}</button>
              <a class="button ghost" :href="`/api/decisions/reports/${encodeURIComponent(report.id)}`" target="_blank" rel="noopener noreferrer" title="打开认证原始数据" aria-label="打开认证原始数据"><ExternalLink :size="15" /></a>
            </div>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>
