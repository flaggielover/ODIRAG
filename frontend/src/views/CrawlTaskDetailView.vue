<script setup lang="ts">
import { ArrowLeft, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '@/api/resources'
import type {
  CozeInvocation,
  CrawlTask,
  CrawlTaskAcceptanceSummary,
  CrawlTaskFailure,
  CrawlTaskResult,
} from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime, formatNumber } from '@/utils/format'

const route = useRoute()
const task = ref<CrawlTask | null>(null)
const acceptanceSummary = ref<CrawlTaskAcceptanceSummary | null>(null)
const acceptanceError = ref<string | null>(null)
const invocations = ref<CozeInvocation[]>([])
const failures = ref<CrawlTaskFailure[]>([])
const results = ref<CrawlTaskResult[]>([])
const retryingFailureId = ref<number | null>(null)
const actionError = ref<string | null>(null)
const { loading, error, run } = useAsyncTask()
const taskId = computed(() => Number(route.params.id))
const counts = computed(() => Object.entries(task.value?.stage_counts ?? {}))

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    acceptanceSummary.value = null
    acceptanceError.value = null
    const [taskResult, invocationResult, failureResult, documentResult, summaryResult] = await Promise.allSettled([
      api.crawlTask(taskId.value),
      api.crawlInvocations(taskId.value),
      api.crawlTaskFailures(taskId.value),
      api.crawlTaskResults(taskId.value),
      api.crawlTaskAcceptanceSummary(taskId.value),
    ])
    if (taskResult.status === 'rejected') throw taskResult.reason
    if (invocationResult.status === 'rejected') throw invocationResult.reason
    if (failureResult.status === 'rejected') throw failureResult.reason
    if (documentResult.status === 'rejected') throw documentResult.reason
    task.value = taskResult.value
    invocations.value = invocationResult.value
    failures.value = failureResult.value
    results.value = documentResult.value
    if (summaryResult.status === 'fulfilled') {
      acceptanceSummary.value = summaryResult.value
    } else {
      acceptanceError.value = summaryResult.reason instanceof Error ? summaryResult.reason.message : '验收摘要暂时不可用'
    }
  })
}

async function retryFailure(failure: CrawlTaskFailure): Promise<void> {
  retryingFailureId.value = failure.id
  actionError.value = null
  try {
    await api.retryCrawlTaskFailure(taskId.value, failure.id)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '失败 URL 重试入队失败'
  } finally {
    retryingFailureId.value = null
  }
}
</script>

<template>
  <PageHeader :title="`抓取任务 #${taskId}`" :meta="task?.crawl_provider ?? task?.provider ?? '-'">
    <template #actions><RouterLink class="button button-secondary" to="/crawl-tasks"><ArrowLeft :size="16" aria-hidden="true" />返回任务列表</RouterLink><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button></template>
  </PageHeader>

  <AsyncState :loading="loading" :error="error" :empty="!task" empty-text="任务不存在" @retry="load">
    <template v-if="task">
      <section class="detail-section acceptance-summary-section" aria-labelledby="acceptance-summary-title">
        <h2 id="acceptance-summary-title">验收摘要</h2>
        <div v-if="acceptanceSummary" class="metric-row">
          <div><strong>{{ formatNumber(acceptanceSummary.database_document_count) }}</strong><span>数据库文档</span></div>
          <div><strong>{{ formatNumber(acceptanceSummary.chunk_count) }}</strong><span>分块</span></div>
          <div><strong>{{ acceptanceSummary.qdrant_collection_exists ? '已创建' : '未创建' }}</strong><span>Qdrant 集合</span></div>
          <div><strong>{{ formatNumber(acceptanceSummary.qdrant_point_count) }}</strong><span>Qdrant 向量点</span></div>
        </div>
        <div v-else-if="acceptanceError" class="notice" role="status">验收摘要不可用：{{ acceptanceError }}</div>
        <p v-else class="muted">验收摘要暂无数据。</p>
      </section>
      <section class="detail-band"><div class="detail-grid"><div><span class="detail-label">状态</span><StatusBadge :status="task.status" /></div><div><span class="detail-label">当前阶段</span><span>{{ task.current_stage || task.stage || task.status }}</span></div><div><span class="detail-label">Provider</span><span>{{ task.crawl_provider || task.provider || 'coze' }}</span></div><div><span class="detail-label">Coze 契约</span><span>{{ task.provider_contract || task.contract_mode || '-' }}</span></div><div><span class="detail-label">Coze execution ID</span><code>{{ task.coze_execution_id || task.provider_task_id || '-' }}</code></div><div><span class="detail-label">Provider 状态</span><span>{{ task.provider_status || '-' }}</span></div><div><span class="detail-label">开始时间</span><span>{{ formatDateTime(task.started_at) }}</span></div><div><span class="detail-label">结束时间</span><span>{{ formatDateTime(task.finished_at) }}</span></div></div></section>
      <section class="detail-section"><h2>处理计数</h2><div class="metric-row"><div><strong>{{ formatNumber(task.discovered_count) }}</strong><span>发现</span></div><div><strong>{{ formatNumber(task.fetched_count) }}</strong><span>抓取</span></div><div><strong>{{ formatNumber(task.success_count) }}</strong><span>成功</span></div><div><strong>{{ formatNumber(task.accepted_count ?? task.success_count) }}</strong><span>接受</span></div><div><strong>{{ formatNumber(task.rejected_count ?? 0) }}</strong><span>拒绝</span></div><div><strong>{{ formatNumber(task.pending_review_count ?? 0) }}</strong><span>待审核</span></div><div><strong>{{ formatNumber(task.failed_count) }}</strong><span>失败</span></div><div><strong>{{ formatNumber(task.retry_count) }}</strong><span>重试</span></div></div></section>
      <section class="detail-section"><h2>阶段计数</h2><div v-if="counts.length" class="stage-grid"><div v-for="[name, value] in counts" :key="name"><span>{{ name }}</span><strong>{{ formatNumber(value) }}</strong></div></div><p v-else class="muted">暂无阶段计数。</p></section>
      <section v-if="task.provider_error_code || task.provider_error_message || task.error_message" class="detail-section error-section"><h2>错误信息</h2><dl><dt>错误码</dt><dd><code>{{ task.provider_error_code || '-' }}</code></dd><dt>任务错误</dt><dd>{{ task.error_message || '-' }}</dd><dt>Provider 错误</dt><dd>{{ task.provider_error_message || '-' }}</dd></dl></section>
      <section class="detail-section"><h2>Coze 调用记录</h2><div v-if="invocations.length" class="invocation-list"><div v-for="invocation in invocations" :key="invocation.id" class="invocation-row"><div><StatusBadge :status="invocation.status" /><span>{{ invocation.contract }}</span></div><span>{{ invocation.http_status_code ?? '-' }} · {{ invocation.duration_ms ?? '-' }} ms · 尝试 {{ invocation.attempt_count }}</span><code v-if="invocation.error_code">{{ invocation.error_code }}</code></div></div><p v-else class="muted">暂无 Coze 调用记录。</p></section>
      <section class="detail-section"><h2>文章结果</h2><div v-if="results.length" class="result-list"><div v-for="result in results" :key="result.id" class="result-row"><div><a :href="result.source_url" target="_blank" rel="noopener noreferrer">{{ result.title }}</a><span class="cell-secondary">{{ result.document_id }}</span></div><StatusBadge :status="result.decision" /><span>{{ result.quality_score ?? '-' }}</span><span>{{ result.review_reason || '-' }}</span></div></div><p v-else class="muted">暂无已持久化文章结果。</p></section>
      <section class="detail-section"><h2>失败 URL</h2><div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div><div v-if="failures.length" class="result-list"><div v-for="failure in failures" :key="failure.id" class="result-row"><div><a :href="failure.url" target="_blank" rel="noopener noreferrer">{{ failure.url }}</a><span class="cell-secondary">{{ failure.stage }} · {{ failure.error_code }}</span></div><StatusBadge :status="failure.status" /><span>{{ failure.error_message }}</span><button class="button button-secondary" type="button" :disabled="!failure.retryable || retryingFailureId === failure.id" @click="retryFailure(failure)">重试</button></div></div><p v-else class="muted">没有失败 URL。</p></section>
    </template>
  </AsyncState>
</template>

<style scoped>
.detail-band { padding: 18px 0; border-top: 1px solid var(--color-border); border-bottom: 1px solid var(--color-border); }
.detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 18px; }
.detail-grid > div { min-width: 0; }
.detail-label { display: block; margin-bottom: 6px; color: var(--color-text-muted); font-size: 12px; }
.detail-section { padding: 20px 0; border-bottom: 1px solid var(--color-border); }
.detail-section h2 { margin: 0 0 14px; font-size: 16px; }
.metric-row, .stage-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }
.metric-row > div, .stage-grid > div { display: flex; flex-direction: column; gap: 4px; }
.metric-row strong { font-size: 22px; }
.metric-row span, .stage-grid span { color: var(--color-text-muted); font-size: 12px; }
.stage-grid > div { flex-direction: row; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--color-border); }
.error-section { color: var(--color-danger); }
.error-section dl { display: grid; grid-template-columns: 110px 1fr; gap: 8px 16px; margin: 0; }
.error-section dt { font-weight: 600; }
.error-section dd { margin: 0; overflow-wrap: anywhere; }
.invocation-list { display: grid; gap: 10px; }
.invocation-row { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(180px, auto) minmax(120px, auto); gap: 14px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.invocation-row > div { display: flex; align-items: center; gap: 8px; }
.result-list { display: grid; gap: 8px; }
.result-row { display: grid; grid-template-columns: minmax(240px, 2fr) minmax(100px, auto) minmax(80px, auto) minmax(180px, 1fr); gap: 14px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.result-row > div:first-child { min-width: 0; }
.result-row a { overflow-wrap: anywhere; }
code { overflow-wrap: anywhere; }
@media (max-width: 720px) { .invocation-row, .result-row { grid-template-columns: 1fr; } }
</style>
