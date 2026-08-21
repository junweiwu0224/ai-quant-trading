<script setup lang="ts">
import { Download } from 'lucide-vue-next'
import { computed } from 'vue'
import { usePaperFormat } from '../../composables/usePaperFormat'

const props = defineProps<{
  status: Record<string, any> | null
  performance: Record<string, any> | null
  tradeStats: Record<string, any> | null
  dailyPerformance: Record<string, any>[]
}>()

const statusRef = computed(() => props.status)
const { number, percent } = usePaperFormat(statusRef)

const metricRows = computed(() => {
  const item = props.performance || props.tradeStats || {}
  return [
    ['总权益', item.total_equity ?? props.status?.equity],
    ['总收益', item.total_return],
    ['最大回撤', item.max_drawdown],
    ['夏普', item.sharpe_ratio],
    ['胜率', item.win_rate],
    ['交易次数', item.total_trades ?? props.tradeStats?.total_trades],
  ]
})

function exportDaily() {
  if (!props.dailyPerformance.length) return
  const header = '日期,总权益,收益率,最大回撤'
  const rows = props.dailyPerformance.map(d => `${d.date || d.trade_date || ''},${d.total_equity ?? ''},${d.daily_return ?? d.return_rate ?? ''},${d.max_drawdown ?? ''}`)
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `paper-daily-${new Date().toISOString().slice(0, 10)}.csv`; a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="section-grid two">
    <section class="panel">
      <div class="panel-head">
        <div><h2>绩效指标</h2><p>没有历史数据时显示为空，不把 0 当作"已运行"。</p></div>
        <Download :size="18" class="faint" />
      </div>
      <div v-if="!metricRows.some(([, v]) => v != null)" class="empty">暂无绩效数据</div>
      <div v-else class="metric-grid">
        <div v-for="([label, value]) in metricRows" :key="label" class="metric-item">
          <span>{{ label }}</span>
          <strong>{{ label.includes('率') ? percent(value) : number(value) }}</strong>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <div><h2>每日收益</h2><p>当前 legacy API 不保证提供每日明细。</p></div>
        <button class="button ghost small" type="button" :disabled="!dailyPerformance.length" @click="exportDaily"><Download :size="14" />导出 CSV</button>
      </div>
      <div v-if="!dailyPerformance.length" class="empty">暂无每日收益数据</div>
      <div v-else class="table-wrap">
        <table class="table" aria-label="每日收益">
          <thead><tr><th>日期</th><th>总权益</th><th>收益率</th><th>最大回撤</th></tr></thead>
          <tbody>
            <tr v-for="day in dailyPerformance" :key="day.date || day.trade_date">
              <td>{{ day.date || day.trade_date || '—' }}</td>
              <td>{{ number(day.total_equity) }}</td>
              <td :class="(day.daily_return ?? day.return_rate ?? 0) >= 0 ? 'good' : 'bad'">{{ percent(day.daily_return ?? day.return_rate) }}</td>
              <td>{{ percent(day.max_drawdown) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
