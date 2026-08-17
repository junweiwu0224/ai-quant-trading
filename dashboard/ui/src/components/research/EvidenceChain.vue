<script setup lang="ts">
import { computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'
import BaseTag from '../base/BaseTag.vue'

export interface EvidenceItem {
  id: string
  source: string
  content: string
  confidence: 'high' | 'medium' | 'low'
  timestamp: string
}

interface Props {
  market?: string
  symbol?: string
}

defineProps<Props>()

// Placeholder evidence data
const evidenceItems = computed<EvidenceItem[]>(() => [
  {
    id: '1',
    source: '基本面分析',
    content: '数据加载中...',
    confidence: 'high',
    timestamp: '2分钟前'
  },
  {
    id: '2',
    source: '技术指标',
    content: '数据加载中...',
    confidence: 'medium',
    timestamp: '3分钟前'
  },
  {
    id: '3',
    source: '市场情绪',
    content: '数据加载中...',
    confidence: 'medium',
    timestamp: '5分钟前'
  },
  {
    id: '4',
    source: '行业趋势',
    content: '数据加载中...',
    confidence: 'low',
    timestamp: '7分钟前'
  }
])

const getConfidenceVariant = (confidence: string) => {
  switch (confidence) {
    case 'high': return 'success'
    case 'medium': return 'warning'
    case 'low': return 'danger'
    default: return 'default'
  }
}

const getConfidenceLabel = (confidence: string) => {
  switch (confidence) {
    case 'high': return '高置信度'
    case 'medium': return '中等置信度'
    case 'low': return '低置信度'
    default: return '未知'
  }
}
</script>

<template>
  <div class="evidence-chain">
    <h2 class="chain-title">证据链</h2>
    <div class="chain-items">
      <div
        v-for="(item, index) in evidenceItems"
        :key="item.id"
        class="chain-item-wrapper"
      >
        <BaseCard class="evidence-item" padding="md" bordered>
          <div class="evidence-header">
            <div class="evidence-source">
              <span class="source-label">{{ item.source }}</span>
              <span class="source-timestamp">{{ item.timestamp }}</span>
            </div>
            <BaseTag
              :variant="getConfidenceVariant(item.confidence)"
              size="sm"
            >
              {{ getConfidenceLabel(item.confidence) }}
            </BaseTag>
          </div>
          <div class="evidence-content">
            {{ item.content }}
          </div>
        </BaseCard>
        <div v-if="index < evidenceItems.length - 1" class="chain-connector">
          <div class="connector-line"></div>
          <div class="connector-arrow">↓</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.evidence-chain {
  width: 100%;
}

.chain-title {
  margin: 0 0 var(--spacing-lg) 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.chain-items {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.chain-item-wrapper {
  display: flex;
  flex-direction: column;
  animation: fadeInSlide var(--duration-slow) var(--ease-smooth);
}

@keyframes fadeInSlide {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.evidence-item {
  background-color: var(--color-ai-bg);
  border: 1px solid var(--color-ai-border);
  transition: all var(--duration-normal) var(--ease-smooth);
}

.evidence-item:hover {
  border-color: var(--color-line);
  box-shadow: var(--shadow-sm);
}

.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.evidence-source {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.source-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.source-timestamp {
  font-size: var(--font-size-xs);
  color: var(--color-ink-faint);
}

.evidence-content {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  line-height: var(--line-height-relaxed);
}

.chain-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  position: relative;
}

.connector-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(
    to bottom,
    var(--color-line) 0%,
    var(--color-accent) 50%,
    var(--color-line) 100%
  );
  opacity: 0.4;
}

.connector-arrow {
  position: relative;
  z-index: var(--z-base);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background-color: var(--color-surface);
  border: 2px solid var(--color-line);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  color: var(--color-accent);
  font-weight: var(--font-weight-bold);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .chain-title {
    font-size: var(--font-size-lg);
    margin-bottom: var(--spacing-md);
  }

  .evidence-header {
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .evidence-source {
    width: 100%;
  }

  .chain-connector {
    height: 24px;
  }

  .connector-arrow {
    width: 20px;
    height: 20px;
    font-size: var(--font-size-xs);
  }
}

/* Small mobile */
@media (max-width: 480px) {
  .chain-title {
    font-size: var(--font-size-base);
  }

  .source-label {
    font-size: var(--font-size-sm);
  }

  .evidence-content {
    font-size: var(--font-size-xs);
  }

  .chain-connector {
    height: 20px;
  }
}
</style>
