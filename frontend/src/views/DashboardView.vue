<script setup lang="ts">
import { AlertTriangle, BookOpenCheck, BotMessageSquare, DatabaseZap, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '@/api/resources'
import type { Alert, CrawlTask, EvaluationRun, HealthResponse, MetricsResponse } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import MetricTile from '@/components/MetricTile.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime, formatDuration, formatNumber, formatPercent } from '@/utils/format'

const metrics = ref<MetricsResponse | null>(null)
const health = ref<HealthResponse | null>(null)
const alerts = ref<Alert[]>([])
const tasks = ref<CrawlTask[]>([])
const evaluations = ref<EvaluationRun[]>([])
const { loading, error, run } = useAsyncTask()

const openAlerts = computed(() => alerts.value.filter((item) => item.status !== 'resolved'))

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    const [metricsResult, healthResult, alertResult, taskResult, evaluationResult] = await Promise.all([
      api.metrics(),
      api.health(),
      api.alerts({ refresh: true }),
      api.crawlTasks(),
      api.evaluations(8),
    ])
    metrics.value = metricsResult
    health.value = healthResult
    alerts.value = alertResult
    tasks.value = taskResult.slice(0, 8)
    evaluations.value = evaluationResult.slice(0, 5)
  })
}
</script>

<template>
  <PageHeader title="仪表盘" :meta="metrics ? `服务已运行 ${formatDuration(metrics.uptime_seconds * 1000)}` : undefined">
    <template #actions>
      <button class="button button-secondary" type="button" :disabled="loading" @click="load">
        <RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />
        刷新
      </button>
    </template>
  </PageHeader>

  <AsyncState :loading="loading" :error="error" @retry="load">
    <template v-if="metrics">
      <section class="metric-grid" aria-label="核心指标">
        <MetricTile
          label="知识库文档"
          :value="formatNumber(metrics.knowledge.document_count)"
          :detail="`${formatNumber(metrics.knowledge.indexed_count)} 已索引`"
          :icon="BookOpenCheck"
          tone="positive"
        />
        <MetricTile
          label="窗口内抓取任务"
          :value="formatNumber(metrics.crawler.task_count)"
          :detail="`失败率 ${formatPercent(metrics.crawler.task_failure_rate)}`"
          :icon="DatabaseZap"
          :tone="metrics.crawler.task_failure_rate > 0 ? 'warning' : 'default'"
        />
        <MetricTile
          label="RAG 查询"
          :value="formatNumber(metrics.rag.query_count)"
          :detail="`P95 ${formatDuration(metrics.rag.p95_latency_ms)}`"
          :icon="BotMessageSquare"
        />
        <MetricTile
          label="未解决告警"
          :value="formatNumber(openAlerts.length)"
          :detail="health ? `系统状态：${health.status}` : undefined"
          :icon="AlertTriangle"
          :tone="openAlerts.length > 0 ? 'danger' : 'positive'"
        />
      </section>

      <section class="content-grid content-grid-wide">
        <div class="panel">
          <header class="panel-header">
            <h2>最近抓取任务</h2>
            <RouterLink class="text-button" to="/crawl-tasks">查看全部</RouterLink>
          </header>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr><th>任务</th><th>状态</th><th>抓取</th><th>成功</th><th>创建时间</th></tr>
              </thead>
              <tbody>
                <tr v-for="task in tasks" :key="task.id">
                  <td><span class="cell-primary">#{{ task.id }} · {{ task.task_type }}</span></td>
                  <td><StatusBadge :status="task.status" /></td>
                  <td>{{ formatNumber(task.fetched_count) }}</td>
                  <td>{{ formatNumber(task.success_count) }}</td>
                  <td>{{ formatDateTime(task.created_at) }}</td>
                </tr>
                <tr v-if="tasks.length === 0"><td colspan="5" class="muted">暂无抓取任务</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="panel">
          <header class="panel-header">
            <h2>依赖状态</h2>
            <RouterLink class="text-button" to="/monitoring">监控详情</RouterLink>
          </header>
          <div class="panel-body stack-list">
            <div v-for="(dependency, name) in metrics.dependencies" :key="name" class="list-row">
              <div class="list-row-main">
                <strong>{{ name }}</strong>
                <span>{{ dependency.detail ?? (dependency.latency_ms !== null ? formatDuration(dependency.latency_ms) : '-') }}</span>
              </div>
              <StatusBadge :status="dependency.status" />
            </div>
          </div>
        </div>

        <div class="panel">
          <header class="panel-header">
            <h2>当前告警</h2>
            <RouterLink class="text-button" to="/monitoring">处理告警</RouterLink>
          </header>
          <div class="panel-body stack-list">
            <div v-for="alert in openAlerts.slice(0, 6)" :key="alert.id" class="list-row">
              <div class="list-row-main">
                <strong>{{ alert.message }}</strong>
                <span>{{ alert.component }} · {{ formatDateTime(alert.last_seen_at) }}</span>
              </div>
              <StatusBadge :status="alert.severity" />
            </div>
            <div v-if="openAlerts.length === 0" class="muted">当前没有未解决告警</div>
          </div>
        </div>

        <div class="panel">
          <header class="panel-header">
            <h2>最近评估</h2>
            <RouterLink class="text-button" to="/evaluations">评估详情</RouterLink>
          </header>
          <div class="panel-body stack-list">
            <div v-for="evaluation in evaluations" :key="evaluation.id" class="list-row">
              <div class="list-row-main">
                <strong>{{ evaluation.run_name }}</strong>
                <span>Recall@5 {{ formatPercent(evaluation.recall_at_5) }} · {{ formatDateTime(evaluation.created_at) }}</span>
              </div>
              <StatusBadge :status="evaluation.finished_at ? 'completed' : 'running'" />
            </div>
            <div v-if="evaluations.length === 0" class="muted">暂无评估运行</div>
          </div>
        </div>
      </section>
    </template>
  </AsyncState>
</template>
