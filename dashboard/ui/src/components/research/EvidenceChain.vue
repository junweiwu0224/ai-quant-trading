<script setup lang="ts">
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'
import ResearchStatePanel from './ResearchStatePanel.vue'
import type { Evidence } from '../../api/types'
import type { SourceState } from '../../api/research'

const props = withDefaults(defineProps<{
  market?: string
  symbol?: string
  evidence?: Evidence[]
  sources?: SourceState[]
  state?: 'loading' | 'available' | 'partial' | 'unavailable'
}>(), { evidence: () => [], sources: () => [], state: 'loading' })

function label(source: string) { return source === 'news' ? '新闻' : '研报' }
function sourceState(source: SourceState | undefined) { return source?.status === 'available' ? '可用' : source?.status === 'partial' ? '暂无记录' : '不可用' }
</script>

<template>
  <div class="evidence-chain">
    <h2 class="chain-title">证据链</h2>
    <ResearchStatePanel :state="props.state" :error="props.sources.find((item) => item.status === 'unavailable')?.error" />
    <div class="source-summary"><span v-for="source in props.sources" :key="source.source" class="source-chip">{{ label(source.source) }}：{{ sourceState(source) }}<small v-if="source.error"> · {{ source.error }}</small></span></div>
    <div v-if="!props.evidence.length && props.state !== 'loading'" class="empty evidence-empty">当前股票没有可展示的新闻或研报证据。</div>
    <div v-else class="chain-items"><div v-for="(item, index) in props.evidence" :key="`${item.type}-${item.timestamp}-${index}`" class="chain-item-wrapper"><BaseCard class="evidence-item" padding="md" bordered><div class="evidence-header"><div class="evidence-source"><span class="source-label">{{ item.source || label(item.type) }}</span><span class="source-timestamp">{{ item.timestamp || '时间未知' }}</span></div><BaseTag variant="info" size="sm">{{ label(item.type) }}</BaseTag></div><div class="evidence-content">{{ item.content || '该证据没有摘要' }}</div></BaseCard><div v-if="index < props.evidence.length - 1" class="chain-connector">↓</div></div></div>
  </div>
</template>

<style scoped>
.evidence-chain { width:100%; }
.chain-title { margin:0 0 var(--spacing-md); font-size:var(--font-size-xl); color:var(--color-ink); }
.source-summary { display:flex; flex-wrap:wrap; gap:var(--spacing-sm); margin:var(--spacing-md) 0; }
.source-chip { padding:var(--spacing-xs) var(--spacing-sm); border:1px solid var(--color-line); border-radius:var(--radius-sm); color:var(--color-ink-soft); font-size:var(--font-size-xs); }
.source-chip small { color:var(--color-danger); }
.chain-items { display:flex; flex-direction:column; }
.evidence-item { background:var(--color-ai-bg); border:1px solid var(--color-ai-border); }
.evidence-header { display:flex; justify-content:space-between; gap:var(--spacing-md); margin-bottom:var(--spacing-sm); }
.evidence-source { display:flex; flex-direction:column; gap:var(--spacing-xs); }
.source-label { color:var(--color-ink); font-weight:var(--font-weight-semibold); }
.source-timestamp { color:var(--color-ink-faint); font-size:var(--font-size-xs); }
.evidence-content { color:var(--color-ink-soft); line-height:var(--line-height-relaxed); }
.chain-connector { align-self:center; padding:var(--spacing-sm); color:var(--color-accent); }
.evidence-empty { padding:var(--spacing-xl); text-align:center; }
</style>
