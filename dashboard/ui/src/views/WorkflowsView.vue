<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, CheckCircle2, LockKeyhole, Moon, Sun } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import { COMMAND_WORKFLOWS, WORKFLOW_GROUPS, type WorkflowGroup } from '../navigation/workflows'

const { isDark, toggleTheme } = useTheme()

const groupedWorkflows = computed(() => WORKFLOW_GROUPS.map((group) => ({
  group,
  items: COMMAND_WORKFLOWS.filter((entry) => entry.group === group),
})).filter((section) => section.items.length))

function groupHint(group: WorkflowGroup): string {
  return {
    决策: '先看当前状态和确定性动作',
    行情: '把市场事实和来源放在一起',
    研究: '从候选到证据的人工研究路径',
    '策略与验证': '验证策略，不绕过资格门禁',
    '组合与执行': '模拟盘写操作都需要确认',
    AI: 'AI 只解释冻结输入，不改写动作',
    '报告与通知': '阅读结果并管理投递资格',
    系统: '运行状态、边界和账户设置',
  }[group]
}
</script>

<template>
  <section class="workflows-view">
    <div class="page-head workflow-head">
      <div>
        <p class="context-label">工作流目录</p>
        <h1>从这里进入每个能力</h1>
        <p>按用户任务组织入口，所有功能都有唯一的 canonical 页面；历史链接会自动重定向。</p>
      </div>
      <div class="workflow-head-meta"><span><CheckCircle2 :size="15" />入口已统一</span><span><LockKeyhole :size="15" />写操作需确认</span><button class="button workflow-theme" type="button" @click="toggleTheme"><component :is="isDark ? Sun : Moon" :size="15" />{{ isDark ? '浅色主题' : '深色主题' }}</button></div>
    </div>

    <section v-for="section in groupedWorkflows" :key="section.group" class="workflow-section">
      <div class="workflow-section-head"><div><h2>{{ section.group }}</h2><p>{{ groupHint(section.group) }}</p></div><span class="tag">{{ section.items.length }} 个工作流</span></div>
      <div class="workflow-grid">
        <RouterLink v-for="entry in section.items" :key="entry.id" class="workflow-entry" :to="entry.to">
          <div class="workflow-entry-icon"><component :is="entry.icon" :size="19" /></div>
          <div class="workflow-entry-copy"><strong>{{ entry.label }}</strong><span>{{ entry.description }}</span><small v-if="entry.readOnly">只读工作流</small></div>
          <ArrowRight :size="17" class="workflow-entry-arrow" />
        </RouterLink>
      </div>
    </section>
  </section>
</template>

<style scoped>
.workflow-head { align-items: end; }
.workflow-head h1 { margin: 5px 0 8px; }
.workflow-head-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px 14px; color: var(--ink-soft); font-size: 12px; }
.workflow-head-meta span { display: inline-flex; align-items: center; gap: 6px; }
.workflow-theme { min-height:36px; padding:4px 9px; font-size:12px; }
.workflow-section { margin-top: 24px; }
.workflow-section-head { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 10px; }
.workflow-section-head h2 { margin: 0; font-size: 17px; }
.workflow-section-head p { margin: 4px 0 0; color: var(--ink-soft); font-size: 12px; }
.workflow-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.workflow-entry { min-width: 0; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 11px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: inherit; text-decoration: none; transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease, background 180ms ease; }
.workflow-entry:hover, .workflow-entry:focus-visible { transform: translateY(-2px); border-color: var(--accent); background: var(--accent-pale); box-shadow: var(--shadow-sm); }
.workflow-entry:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.workflow-entry-icon { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 8px; color: var(--accent-strong); background: var(--accent-pale); }
.workflow-entry-copy { min-width: 0; }
.workflow-entry-copy strong, .workflow-entry-copy span, .workflow-entry-copy small { display: block; }
.workflow-entry-copy strong { font-size: 13px; }
.workflow-entry-copy span { margin-top: 4px; overflow: hidden; color: var(--ink-soft); font-size: 11px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.workflow-entry-copy small { margin-top: 5px; color: var(--ink-faint); font-size: 10px; }
.workflow-entry-arrow { color: var(--ink-faint); transition: transform 180ms ease; }
.workflow-entry:hover .workflow-entry-arrow, .workflow-entry:focus-visible .workflow-entry-arrow { transform: translateX(3px); color: var(--accent-strong); }
@media (max-width: 1080px) { .workflow-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) { .workflow-head { align-items: start; } .workflow-head-meta { justify-content: flex-start; } .workflow-grid { grid-template-columns: 1fr; } }
</style>
