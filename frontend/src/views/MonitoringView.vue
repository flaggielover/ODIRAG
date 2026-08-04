<script setup lang="ts">
import { Activity, AlertTriangle, CheckCircle2, Clock3, Database, RefreshCw, ServerCog } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/resources'
import type { Alert, AlertSeverity, AlertStatus, HealthResponse, MetricsResponse } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import MetricTile from '@/components/MetricTile.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatCost, formatDuration, formatNumber, formatPercent } from '@/utils/format'

const metrics = ref<MetricsResponse | null>(null)
const health = ref<HealthResponse | null>(null)
const alerts = ref<Alert[]>([])
const statusFilter = ref<AlertStatus | ''>('')
const severityFilter = ref<AlertSeverity | ''>('')
const actionId = ref<number | null>(null)
const actionError = ref<string | null>(null)
const { loading, error, run } = useAsyncTask()

const filteredAlerts = computed(() => alerts.value.filter((item) => (!statusFilter.value || item.status === statusFilter.value) && (!severityFilter.value || item.severity === severityFilter.value)))

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    const [metricResult, healthResult, alertResult] = await Promise.all([api.metrics(), api.health(), api.alerts({ refresh: true })])
    metrics.value = metricResult
    health.value = healthResult
    alerts.value = alertResult
  })
}

async function acknowledge(alert: Alert): Promise<void> {
  actionId.value = alert.id
  actionError.value = null
  try {
    await api.acknowledgeAlert(alert.id)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '确认告警失败'
  } finally {
    actionId.value = null
  }
}

async function resolve(alert: Alert): Promise<void> {
  actionId.value = alert.id
  actionError.value = null
  try {
    await api.resolveAlert(alert.id)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '解决告警失败'
  } finally {
    actionId.value = null
  }
}
</script>

<template>
  <PageHeader title="监控与告警" :meta="health ? `${health.service} · ${health.environment}` : undefined"><template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button></template></PageHeader>
  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
  <AsyncState :loading="loading" :error="error" @retry="load">
    <template v-if="metrics && health">
      <section class="metric-grid">
        <MetricTile label="请求总数" :value="formatNumber(metrics.requests_total)" :detail="`运行 ${formatDuration(metrics.uptime_seconds * 1000)}`" :icon="Activity" />
        <MetricTile label="RAG P95" :value="formatDuration(metrics.rag.p95_latency_ms)" :detail="`${formatNumber(metrics.rag.query_count)} 次查询`" :icon="Clock3" :tone="metrics.rag.p95_latency_ms > 5000 ? 'warning' : 'default'" />
        <MetricTile label="DB P95" :value="formatDuration(metrics.database_latency.p95_latency_ms)" :detail="`${formatNumber(metrics.database_latency.sample_count)} 次查询`" :icon="Database" :tone="metrics.database_latency.p95_latency_ms > 300 ? 'warning' : 'default'" />
        <MetricTile label="Trace 完整率" :value="formatPercent(metrics.rag.trace_completeness_rate)" :detail="`拒答率 ${formatPercent(metrics.rag.refusal_rate)}`" :icon="CheckCircle2" tone="positive" />
        <MetricTile label="平均成本" :value="formatCost(metrics.rag.average_cost)" :detail="`总计 ${formatCost(metrics.rag.total_cost)}`" :icon="ServerCog" />
      </section>

      <section class="content-grid">
        <div class="panel"><header class="panel-header"><h2>依赖健康</h2><StatusBadge :status="health.status" /></header><div class="panel-body dependency-grid"><article v-for="(dependency, name) in health.dependencies" :key="name" class="dependency-item"><div><strong>{{ name }}</strong><span>{{ dependency.detail ?? '-' }}</span></div><div><StatusBadge :status="dependency.status" /><span>{{ dependency.latency_ms === null ? '-' : formatDuration(dependency.latency_ms) }}</span></div></article></div></div>
        <div class="panel"><header class="panel-header"><h2>知识库状态</h2></header><div class="panel-body stack-list"><div class="list-row"><span>批准文档</span><strong>{{ formatNumber(metrics.knowledge.approved_count) }}</strong></div><div class="list-row"><span>已索引文档</span><strong>{{ formatNumber(metrics.knowledge.indexed_count) }}</strong></div><div class="list-row"><span>索引失败</span><strong :class="{ danger: metrics.knowledge.index_failure_count > 0 }">{{ formatNumber(metrics.knowledge.index_failure_count) }}</strong></div><div class="list-row"><span>分块总数</span><strong>{{ formatNumber(metrics.knowledge.chunk_count) }}</strong></div></div></div>
        <div class="panel"><header class="panel-header"><h2>抓取窗口</h2><span class="muted">{{ metrics.crawler.window_hours }} 小时</span></header><div class="panel-body stack-list"><div class="list-row"><span>任务失败率</span><strong>{{ formatPercent(metrics.crawler.task_failure_rate) }}</strong></div><div class="list-row"><span>条目失败率</span><strong>{{ formatPercent(metrics.crawler.item_failure_rate) }}</strong></div><div class="list-row"><span>发现 / 成功</span><strong>{{ formatNumber(metrics.crawler.discovered_count) }} / {{ formatNumber(metrics.crawler.success_count) }}</strong></div><div class="progress-track"><div class="progress-fill" :style="{ width: `${Math.min(100, metrics.crawler.discovered_count ? metrics.crawler.success_count / metrics.crawler.discovered_count * 100 : 0)}%` }" /></div></div></div>
        <div class="panel"><header class="panel-header"><h2>HTTP 状态分布</h2></header><div class="panel-body stack-list"><div v-for="(count, statusClass) in metrics.requests_by_status_class" :key="statusClass" class="list-row"><span>{{ statusClass }}</span><strong>{{ formatNumber(count) }}</strong></div></div></div>
      </section>

      <section class="monitoring-section">
        <div class="section-heading"><div><h2>告警</h2><span>{{ filteredAlerts.length }} 条</span></div><div class="toolbar"><select v-model="statusFilter" class="select compact-control"><option value="">全部状态</option><option value="open">未处理</option><option value="acknowledged">已确认</option><option value="resolved">已解决</option></select><select v-model="severityFilter" class="select compact-control"><option value="">全部级别</option><option value="critical">严重</option><option value="high">高</option><option value="warning">警告</option><option value="info">信息</option></select></div></div>
        <div class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>告警</th><th>组件</th><th>级别</th><th>状态</th><th>观测 / 阈值</th><th>次数</th><th>操作</th></tr></thead><tbody><tr v-for="alert in filteredAlerts" :key="alert.id"><td><span class="cell-primary"><AlertTriangle :size="14" aria-hidden="true" />{{ alert.message }}</span><span class="cell-secondary">{{ alert.alert_type }}</span></td><td>{{ alert.component }}</td><td><StatusBadge :status="alert.severity" /></td><td><StatusBadge :status="alert.status" /></td><td>{{ alert.observed_value ?? '-' }} / {{ alert.threshold_value ?? '-' }}</td><td>{{ alert.occurrence_count }}</td><td><div class="inline-actions"><button class="text-button" type="button" :disabled="alert.status !== 'open' || actionId === alert.id" @click="acknowledge(alert)">确认</button><button class="text-button" type="button" :disabled="alert.status === 'resolved' || actionId === alert.id" @click="resolve(alert)">解决</button></div></td></tr><tr v-if="filteredAlerts.length === 0"><td colspan="7" class="muted">没有匹配的告警</td></tr></tbody></table></div></div>
      </section>

      <section class="monitoring-section"><div class="section-heading"><div><h2>路由请求</h2><span>{{ metrics.routes.length }} 个状态组合</span></div></div><div class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>方法</th><th>路径</th><th>状态码</th><th>请求数</th><th>P95</th></tr></thead><tbody><tr v-for="(routeMetric, index) in metrics.routes" :key="`${routeMetric.method}-${routeMetric.path}-${routeMetric.status_code}-${index}`"><td><span class="status-badge">{{ routeMetric.method }}</span></td><td class="mono">{{ routeMetric.path }}</td><td><StatusBadge :status="routeMetric.status_code >= 500 ? 'failed' : routeMetric.status_code >= 400 ? 'warning' : 'success'" /></td><td>{{ formatNumber(routeMetric.count) }}</td><td>{{ formatDuration(routeMetric.p95_latency_ms) }}</td></tr></tbody></table></div></div></section>
    </template>
  </AsyncState>
</template>
