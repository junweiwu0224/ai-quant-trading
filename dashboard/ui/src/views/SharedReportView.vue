<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CircleAlert, ShieldCheck } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { SharedDecisionReport } from '../types'

const route = useRoute()
const report = ref<SharedDecisionReport | null>(null)
const loading = ref(false)
const error = ref('')
const linkStatus = computed(() => {
  const expiresAt = report.value?.expires_at ? Date.parse(report.value.expires_at) : NaN
  if (!Number.isFinite(expiresAt)) return 'unknown'
  return expiresAt > Date.now() ? 'active' : 'expired'
})

function shortHash(hash: string | undefined, length = 16) {
  return hash ? `${hash.slice(0, length)}…` : '不可用'
}

function scoreOrUnknown(value: unknown): string {
  const score = Number(value)
  return Number.isFinite(score)
    ? score.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })
    : '不可判断'
}

function statusLabel(value: unknown) {
  const labels: Record<string, string> = {
    passed: '验证通过',
    failed: '验证未通过',
    eligible: '具备资格',
    blocked: '资格阻断',
    not_run: '尚未验证',
    not_checked: '尚未检查',
    available: '已生成',
    not_available: '未生成',
  }
  return labels[String(value || '')] || String(value || '不可用')
}

function capabilityText(key: string) {
  const value = report.value?.report.market_capabilities?.[key]
  if (Array.isArray(value)) return value.join('、')
  return value == null || value === '' ? '不可用' : String(value)
}

function evidenceMembers() {
  const value = report.value?.report.evidence?.members
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : []
}

async function loadSharedReport(rawToken: unknown) {
  const token = Array.isArray(rawToken) ? String(rawToken[0] || '') : String(rawToken || '')
  report.value = null
  error.value = ''
  if (!token) {
    error.value = '报告链接不可用'
    return
  }

  loading.value = true
  try {
    const data = await api.get<SharedDecisionReport>(`/api/decisions/shared/${encodeURIComponent(token)}`)
    report.value = data
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告链接不可用'
  } finally {
    loading.value = false
  }
}

watch(() => route.params.token, (token) => { void loadSharedReport(token) }, { immediate: true })
</script>
<template>
  <main class="report-reader">
    <div v-if="error" class="error-box" role="alert" aria-live="assertive"><CircleAlert :size="16" />{{ error }}</div>
    <template v-else-if="report">
      <header>
        <div class="data-source">
          <span><ShieldCheck :size="14" />只读报告</span>
          <span class="tag" :class="linkStatus === 'active' ? 'good' : 'warn'">{{ linkStatus === 'active' ? '链接有效' : linkStatus === 'expired' ? '链接已过期' : '有效期未知' }}</span>
          <span>有效期至 {{ report.expires_at || '不可用' }}</span>
          <span>报告 hash {{ shortHash(report.report_hash) }}</span>
          <span v-if="report.report.input_hash">输入 hash {{ shortHash(report.report.input_hash) }}</span>
        </div>
        <h1>策略组合决策报告</h1>
        <p class="reader-intro">这份报告由冻结输入生成。动作、分数和风险否决来自确定性规则，AI 解释如果存在，只是独立补充件。</p>
      </header>
      <section class="reader-context">
        <div class="reader-context-grid">
          <div><span>组合</span><strong>{{ report.report.portfolio_id || '不可用' }}</strong></div>
          <div><span>市场</span><strong>{{ report.report.market || '不可用' }}</strong></div>
          <div><span>数据状态</span><strong>{{ report.report.quality_status || '不可用' }}</strong></div>
          <div><span>验证</span><strong>{{ statusLabel(report.report.validation?.status) }}</strong></div>
          <div><span>自动推送资格</span><strong>{{ statusLabel(report.report.eligibility?.status) }}</strong></div>
          <div><span>证据成员</span><strong>{{ report.report.evidence?.member_count ?? 0 }}</strong></div>
        </div>
        <div class="reader-context-block">
          <h2>市场能力与策略版本</h2>
          <div class="data-source"><span>{{ capabilityText('display_name') }}</span><span>时区 {{ capabilityText('timezone') }}</span><span>日线 {{ capabilityText('daily_granularities') }}</span><span>盘中 {{ capabilityText('intraday_granularities') }}</span><span>自动推送 {{ capabilityText('automatic_push_supported') }}</span></div>
          <div class="reader-strategies">
            <span v-for="strategy in report.report.strategy_weights || []" :key="String(strategy.strategy_name)" class="reader-strategy">{{ strategy.strategy_name || '策略' }} · {{ strategy.version || '未版本化' }} · 权重 {{ strategy.weight ?? '—' }}</span>
          </div>
        </div>
        <div class="reader-context-block">
          <h2>验证摘要与关键证据</h2>
          <p class="muted small">{{ (report.report.validation?.result?.reasons as string[] | undefined)?.join('、') || report.report.eligibility?.reasons?.join('、') || '没有额外阻断原因' }}</p>
          <div v-if="evidenceMembers().length" class="reader-evidence">
            <span v-for="evidence in evidenceMembers()" :key="String(evidence.membership_id)" class="tag">{{ evidence.symbol }} · 覆盖 {{ evidence.coverage_pct ?? evidence.coverage ?? 0 }}% · {{ evidence.quality_status || '未知' }}</span>
          </div>
        </div>
        <div class="reader-context-block">
          <h2>AI 解释与投递历史</h2>
          <div class="data-source"><span>AI {{ statusLabel(report.ai_commentary_status) }}</span><span>投递 {{ report.delivery_attempts?.length || 0 }} 次</span></div>
          <div v-if="report.ai_commentary?.length" class="reader-supplements">
            <article v-for="(item, index) in report.ai_commentary" :key="index" class="reader-supplement"><strong>{{ item.model || 'AI' }}</strong><p>{{ item.content || '无补充内容' }}</p></article>
          </div>
          <div v-if="report.delivery_attempts?.length" class="reader-deliveries">
            <div v-for="(attempt, index) in report.delivery_attempts" :key="index" class="reader-delivery"><span>{{ attempt.channel || attempt.target_id || '通知目标' }}</span><span>{{ attempt.status || 'unknown' }}</span><span>{{ attempt.created_at || '' }}</span></div>
          </div>
        </div>
      </section>
      <section class="reader-list">
        <article v-for="item in report.report.decisions || []" :key="item.id" class="reader-item">
          <div class="reader-item-head"><strong>{{ item.symbol }}</strong><span class="action" :class="item.action">{{ item.action }}</span></div>
          <p class="muted small">综合分：{{ scoreOrUnknown(item.score) }} · {{ (item.reason_codes || []).join('、') || '无额外原因码' }}</p>
          <div class="data-source"><span>有效：{{ item.valid ? '是' : '否' }}</span><span>风险否决：{{ item.risk_veto ? '命中' : '未命中' }}</span><span>贡献数：{{ item.contributions?.length || 0 }}</span></div>
        </article>
      </section>
    </template>
    <div v-else class="empty">{{ loading ? '正在读取冻结报告…' : '报告链接不可用' }}</div>
  </main>
</template>
