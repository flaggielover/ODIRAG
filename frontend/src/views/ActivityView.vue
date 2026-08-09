<script setup lang="ts">
import { Eye, MessageSquareWarning, RefreshCw, TestTube2 } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { api } from '@/api/resources'
import type { Feedback, QueryTrace } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatCost, formatDateTime, formatDuration } from '@/utils/format'

const traces = ref<QueryTrace[]>([])
const feedback = ref<Feedback[]>([])
const feedbackError = ref<string | null>(null)
const selectedTrace = ref<QueryTrace | null>(null)
const traceOpen = ref(false)
const convertingId = ref<number | null>(null)
const actionError = ref<string | null>(null)
const queryType = ref('')
const refusal = ref('')
const { loading, error, run } = useAsyncTask()

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    const [traceResult, feedbackResult] = await Promise.allSettled([
      api.traces({ limit: 200, query_type: queryType.value || undefined, refusal: refusal.value === '' ? undefined : refusal.value === 'true' }),
      api.feedback(),
    ])
    if (traceResult.status === 'fulfilled') traces.value = traceResult.value
    else throw traceResult.reason
    if (feedbackResult.status === 'fulfilled') {
      feedback.value = feedbackResult.value
      feedbackError.value = null
    } else {
      feedback.value = []
      feedbackError.value = feedbackResult.reason instanceof Error ? feedbackResult.reason.message : '反馈列表加载失败'
    }
  })
}

function inspect(trace: QueryTrace): void {
  selectedTrace.value = trace
  traceOpen.value = true
}

function canConvert(item: Feedback): boolean {
  return (
    item.feedback_type !== 'helpful' &&
    !item.converted_to_evaluation &&
    convertingId.value !== item.id
  )
}

async function convert(item: Feedback): Promise<void> {
  if (!canConvert(item)) return
  convertingId.value = item.id
  actionError.value = null
  try {
    await api.convertFeedback(item.id)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '转换失败'
  } finally {
    convertingId.value = null
  }
}
</script>

<template>
  <PageHeader title="反馈与日志" :meta="`${traces.length} 条查询 Trace`"><template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button></template></PageHeader>
  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
  <div class="filter-bar"><div class="form-field"><label for="trace-type">查询类型</label><select id="trace-type" v-model="queryType" class="select" @change="load"><option value="">全部</option><option value="sql">SQL</option><option value="rag">RAG</option><option value="sql+rag">SQL + RAG</option></select></div><div class="form-field"><label for="trace-refusal">拒答</label><select id="trace-refusal" v-model="refusal" class="select" @change="load"><option value="">全部</option><option value="true">是</option><option value="false">否</option></select></div></div>
  <AsyncState :loading="loading" :error="error" @retry="load">
    <section class="monitoring-section"><div class="section-heading"><div><h2>查询日志</h2><span>完整 Trace 审计</span></div></div><div class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>查询</th><th>类型</th><th>结果</th><th>延迟</th><th>成本</th><th>时间</th><th>操作</th></tr></thead><tbody><tr v-for="trace in traces" :key="trace.trace_id"><td><span class="cell-primary">{{ trace.user_query }}</span><span class="cell-secondary mono">{{ trace.trace_id }}</span></td><td>{{ trace.query_type }}</td><td><StatusBadge :status="trace.refusal ? 'rejected' : 'completed'" /></td><td>{{ formatDuration(trace.latency_ms) }}</td><td>{{ formatCost(trace.cost) }}</td><td>{{ formatDateTime(trace.created_at) }}</td><td><button class="icon-button" type="button" title="查看 Trace" aria-label="查看 Trace" @click="inspect(trace)"><Eye :size="16" aria-hidden="true" /></button></td></tr><tr v-if="traces.length === 0"><td colspan="7" class="muted">暂无查询日志</td></tr></tbody></table></div></div></section>

    <section class="monitoring-section"><div class="section-heading"><div><h2>用户反馈</h2><span>{{ feedback.length }} 条</span></div></div><div v-if="feedbackError" class="notice notice-error"><MessageSquareWarning :size="16" aria-hidden="true" /><span>{{ feedbackError }}</span></div><div v-else class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>Trace</th><th>反馈类型</th><th>评分</th><th>备注</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in feedback" :key="item.id"><td class="mono">{{ item.trace_id }}</td><td>{{ item.feedback_type }}</td><td>{{ item.rating ?? '-' }}</td><td><span class="cell-primary">{{ item.comment ?? '-' }}</span></td><td><StatusBadge :status="item.converted_to_evaluation ? 'completed' : item.resolved ? 'resolved' : 'pending'" /></td><td>{{ formatDateTime(item.created_at) }}</td><td><button class="text-button" type="button" :disabled="!canConvert(item)" :title="item.feedback_type === 'helpful' ? '正向反馈无需转为评估' : '转为评估'" @click="convert(item)"><TestTube2 :size="15" aria-hidden="true" />转为评估</button></td></tr><tr v-if="feedback.length === 0"><td colspan="7" class="muted">暂无用户反馈</td></tr></tbody></table></div></div></section>
  </AsyncState>

  <ModalDialog :open="traceOpen" title="查询 Trace" width="large" @close="traceOpen = false"><div v-if="selectedTrace" class="stack-list"><JsonPanel label="基本信息" :value="{ trace_id: selectedTrace.trace_id, query: selectedTrace.user_query, query_type: selectedTrace.query_type, refusal: selectedTrace.refusal, latency_ms: selectedTrace.latency_ms, token_usage: selectedTrace.token_usage_json, cost: selectedTrace.cost }" /><JsonPanel label="过滤条件" :value="selectedTrace.parsed_filters_json" /><JsonPanel label="检索阶段" :value="{ bm25: selectedTrace.bm25_results_json, vector: selectedTrace.vector_results_json, fusion: selectedTrace.fusion_results_json, rerank: selectedTrace.rerank_results_json }" /><JsonPanel label="Rerank 执行" :value="selectedTrace.rerank_metadata_json" /><JsonPanel label="Prompt" :value="selectedTrace.prompt_snapshot_json" /><JsonPanel label="引用" :value="selectedTrace.citations_json" /></div></ModalDialog>
</template>
