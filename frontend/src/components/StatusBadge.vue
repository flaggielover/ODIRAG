<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string | boolean | null | undefined
}>()

const normalized = computed(() => String(props.status ?? 'unknown').toLowerCase())
const label = computed(() => {
  const labels: Record<string, string> = {
    true: '启用',
    false: '停用',
    healthy: '正常',
    completed: '已完成',
    success: '成功',
    approved: '已批准',
    activated: '已激活',
    activating: '激活中',
    awaiting_approval: '等待审批',
    pending_approval: '待审批',
    no_gap: '无缺口',
    gap_detected: '检测到缺口',
    discovered: '已发现',
    validated: '已验证',
    validation_failed: '验证失败',
    columns_discovered: '已发现栏目',
    trial_crawled: '试抓完成',
    official: '官方',
    indexed: '已索引',
    reachable: '可访问',
    running: '运行中',
    queued: '排队中',
    pending: '待处理',
    acknowledged: '已确认',
    warning: '警告',
    high: '高',
    critical: '严重',
    degraded: '降级',
    unavailable: '不可用',
    failed: '失败',
    rejected: '已拒绝',
    cancelled: '已取消',
    open: '未处理',
    resolved: '已解决',
    disabled: '已禁用',
    stale: '待更新',
    info: '信息',
    coze: 'Coze',
    local: 'Local',
    playwright: 'Playwright',
    custom: 'Custom',
    calling_coze: '调用 Coze',
    coze_running: 'Coze 抓取中',
    normalizing: '结果标准化',
    saving_documents: '保存文档',
    waiting_review: '等待审核',
    partial_failed: '部分失败',
  }
  return labels[normalized.value] ?? String(props.status ?? '未知')
})

const tone = computed(() => {
  if (['true', 'healthy', 'completed', 'success', 'approved', 'activated', 'validated', 'trial_crawled', 'official', 'no_gap', 'indexed', 'reachable', 'resolved'].includes(normalized.value)) return 'success'
  if (['running', 'queued', 'pending', 'activating', 'awaiting_approval', 'pending_approval', 'discovered', 'columns_discovered', 'acknowledged', 'info', 'calling_coze', 'coze_running', 'normalizing', 'saving_documents', 'waiting_review', 'coze', 'local', 'playwright', 'custom'].includes(normalized.value)) return 'info'
  if (['warning', 'high', 'degraded', 'stale', 'gap_detected', 'partial_failed'].includes(normalized.value)) return 'warning'
  if (['critical', 'unavailable', 'failed', 'validation_failed', 'rejected', 'cancelled', 'open', 'false', 'disabled'].includes(normalized.value)) return 'danger'
  return 'neutral'
})
</script>

<template>
  <span class="status-badge" :class="`status-${tone}`">
    <span class="status-dot" aria-hidden="true" />
    {{ label }}
  </span>
</template>
