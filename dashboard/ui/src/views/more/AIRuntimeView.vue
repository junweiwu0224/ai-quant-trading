<script setup lang="ts">
import BaseCard from '../../components/base/BaseCard.vue'
import { Settings } from 'lucide-vue-next'

const title = 'AI Runtime 配置'
const description = 'AI 模型、Provider 与 Token 使用管理'
const features = [
  'Token 使用统计与成本分析',
  '模型配置与切换管理',
  'API Provider 设置（OpenAI、Claude 等）',
  '请求速率与配额监控',
  '会话历史与审计日志',
  'Prompt 模板管理'
]
</script>

<template>
  <div class="page-container">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <Settings :size="22" class="faint" />
    </div>

    <BaseCard padding="lg">
      <div class="placeholder-content">
        <div class="status-badge migration">功能迁移中</div>

        <div class="placeholder-body">
          <h2>计划功能</h2>
          <ul class="feature-list">
            <li v-for="feature in features" :key="feature">{{ feature }}</li>
          </ul>

          <div class="migration-note">
            <p><strong>迁移说明：</strong></p>
            <p>此功能正在从旧版系统迁移至新的 Vue 3 架构。迁移完成后，将提供更流畅的用户体验和更强的扩展性。</p>
            <p>当前可通过"更多工具"页面的功能覆盖矩阵访问旧版入口。</p>
          </div>
        </div>
      </div>
    </BaseCard>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1200px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.page-head h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin-bottom: var(--spacing-xs);
}

.page-head p {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
  margin: 0;
}

.faint {
  color: var(--color-ink-faint);
}

.placeholder-content {
  text-align: left;
}

.status-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--spacing-lg);
}

.status-badge.migration {
  background-color: var(--color-warn-bg);
  color: var(--color-warn);
  border: 1px solid var(--color-warn);
}

.placeholder-body h2 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin-bottom: var(--spacing-md);
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--spacing-xl) 0;
}

.feature-list li {
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  color: var(--color-ink);
  position: relative;
  padding-left: var(--spacing-xl);
}

.feature-list li::before {
  content: '•';
  position: absolute;
  left: var(--spacing-md);
  color: var(--color-accent);
  font-weight: bold;
}

.migration-note {
  padding: var(--spacing-lg);
  background-color: var(--color-info-bg);
  border-left: 3px solid var(--color-info);
  border-radius: var(--radius-md);
}

.migration-note p {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: var(--font-size-base);
  color: var(--color-ink);
  line-height: var(--line-height-relaxed);
}

.migration-note p:last-child {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .page-head h1 {
    font-size: var(--font-size-xl);
  }
}
</style>
