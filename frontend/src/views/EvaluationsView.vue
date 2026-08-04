<script setup lang="ts">
import { Eye, Play, Plus, RefreshCw, Trash2 } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { EvaluationQuestionInput, EvaluationReport, EvaluationRun } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import MetricTile from '@/components/MetricTile.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatCost, formatDateTime, formatDuration, formatPercent } from '@/utils/format'

interface QuestionDraft {
  key: string
  question_id: string
  question: string
  query_type: 'sql' | 'rag' | 'sql+rag'
  expected_document_ids: string
  expected_chunk_ids: string
  expected_answer_points: string
  should_refuse: boolean
  category: string
}

const runs = ref<EvaluationRun[]>([])
const selected = ref<EvaluationRun | null>(null)
const report = ref<EvaluationReport | null>(null)
const modalOpen = ref(false)
const saving = ref(false)
const actionError = ref<string | null>(null)
const reportLoading = ref(false)
const { loading, error, run } = useAsyncTask()
const form = reactive({ run_name: '', top_k: 10, retrieval_version: '', prompt_version: '' })
const questions = ref<QuestionDraft[]>([newQuestion()])

onMounted(load)

function newQuestion(): QuestionDraft {
  return {
    key: crypto.randomUUID(),
    question_id: `question-${crypto.randomUUID().slice(0, 8)}`,
    question: '',
    query_type: 'rag',
    expected_document_ids: '',
    expected_chunk_ids: '',
    expected_answer_points: '',
    should_refuse: false,
    category: '',
  }
}

async function load(): Promise<void> {
  await run(async () => {
    runs.value = await api.evaluations(200)
  })
}

function openRun(): void {
  form.run_name = `evaluation-${new Date().toISOString().slice(0, 10)}`
  form.top_k = 10
  form.retrieval_version = ''
  form.prompt_version = ''
  questions.value = [newQuestion()]
  actionError.value = null
  modalOpen.value = true
}

async function execute(): Promise<void> {
  saving.value = true
  actionError.value = null
  try {
    const payloadQuestions: EvaluationQuestionInput[] = questions.value.map((item) => ({
      question_id: item.question_id,
      question: item.question,
      query_type: item.query_type,
      expected_document_ids: splitValues(item.expected_document_ids),
      expected_chunk_ids: splitValues(item.expected_chunk_ids),
      expected_answer_points: item.expected_answer_points.split('\n').map((value) => value.trim()).filter(Boolean),
      expected_filters: {},
      should_refuse: item.should_refuse,
      difficulty: 'medium',
      category: item.category || null,
      created_by: 'console',
      verified: true,
    }))
    const completed = await api.runEvaluation({
      run_name: form.run_name,
      question_ids: [],
      questions: payloadQuestions,
      retrieval_version: form.retrieval_version || null,
      prompt_version: form.prompt_version || null,
      top_k: form.top_k,
    })
    modalOpen.value = false
    await load()
    await showReport(completed)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '评估运行失败'
  } finally {
    saving.value = false
  }
}

function splitValues(value: string): string[] {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)
}

async function showReport(item: EvaluationRun): Promise<void> {
  selected.value = item
  report.value = null
  reportLoading.value = true
  actionError.value = null
  try {
    report.value = await api.evaluationReport(item.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '评估报告不可用'
  } finally {
    reportLoading.value = false
  }
}
</script>

<template>
  <PageHeader title="评估" :meta="`${runs.length} 次运行`">
    <template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button><button class="button" type="button" @click="openRun"><Play :size="16" aria-hidden="true" />运行评估</button></template>
  </PageHeader>

  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>

  <AsyncState :loading="loading" :error="error" :empty="runs.length === 0" empty-text="暂无评估运行" @retry="load">
    <div class="quality-layout">
      <section class="table-frame">
        <div class="table-scroll"><table class="data-table"><thead><tr><th>运行</th><th>状态</th><th>问题数</th><th>Recall@5</th><th>引用准确率</th><th>拒答准确率</th><th>P95</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in runs" :key="item.id" :class="{ 'row-selected': selected?.id === item.id }"><td><span class="cell-primary">{{ item.run_name }}</span><span class="cell-secondary">{{ item.retrieval_version ?? '-' }} · {{ item.prompt_version ?? '-' }}</span></td><td><StatusBadge :status="item.finished_at ? 'completed' : 'running'" /></td><td>{{ item.question_count }}</td><td>{{ formatPercent(item.recall_at_5) }}</td><td>{{ formatPercent(item.citation_accuracy) }}</td><td>{{ formatPercent(item.refusal_accuracy) }}</td><td>{{ formatDuration(Number(item.p95_latency ?? 0)) }}</td><td>{{ formatDateTime(item.created_at) }}</td><td><button class="icon-button" type="button" title="查看报告" aria-label="查看报告" @click="showReport(item)"><Eye :size="16" aria-hidden="true" /></button></td></tr></tbody></table></div>
      </section>

      <aside class="quality-inspector panel">
        <header class="panel-header"><h2>{{ selected?.run_name ?? '评估报告' }}</h2><StatusBadge v-if="selected" :status="selected.finished_at ? 'completed' : 'running'" /></header>
        <div v-if="reportLoading" class="state-panel">正在加载报告</div>
        <div v-else-if="report" class="panel-body stack-list">
          <div class="mini-metric-grid"><MetricTile label="Recall@1" :value="formatPercent(report.aggregate.recall_at_1)" /><MetricTile label="MRR" :value="formatPercent(report.aggregate.mrr)" /><MetricTile label="引用准确率" :value="formatPercent(report.aggregate.citation_accuracy)" /><MetricTile label="幻觉率" :value="formatPercent(report.aggregate.hallucination_rate)" :tone="Number(report.aggregate.hallucination_rate) > 0 ? 'warning' : 'positive'" /></div>
          <JsonPanel label="聚合指标" :value="report.aggregate" />
          <JsonPanel label="逐题结果" :value="report.questions ?? report.cases ?? []" />
        </div>
        <div v-else class="state-panel">选择一次运行查看报告</div>
        <footer v-if="selected" class="quality-footer"><span>平均成本 {{ formatCost(selected.average_cost) }}</span><span>平均延迟 {{ formatDuration(Number(selected.average_latency ?? 0)) }}</span></footer>
      </aside>
    </div>
  </AsyncState>

  <ModalDialog :open="modalOpen" title="运行评估" width="large" @close="modalOpen = false">
    <form id="evaluation-form" class="stack-list" @submit.prevent="execute">
      <div class="form-grid"><div class="form-field"><label for="evaluation-name">运行名称</label><input id="evaluation-name" v-model="form.run_name" class="input" required /></div><div class="form-field"><label for="evaluation-top-k">Top K</label><input id="evaluation-top-k" v-model.number="form.top_k" class="input" type="number" min="1" max="100" required /></div><div class="form-field"><label for="evaluation-retrieval">检索版本</label><input id="evaluation-retrieval" v-model="form.retrieval_version" class="input" /></div><div class="form-field"><label for="evaluation-prompt">Prompt 版本</label><input id="evaluation-prompt" v-model="form.prompt_version" class="input" /></div></div>
      <article v-for="(item, index) in questions" :key="item.key" class="question-editor">
        <header><strong>问题 {{ index + 1 }}</strong><button class="icon-button text-danger" type="button" title="删除问题" aria-label="删除问题" :disabled="questions.length === 1" @click="questions.splice(index, 1)"><Trash2 :size="15" aria-hidden="true" /></button></header>
        <div class="form-grid"><div class="form-field"><label :for="`question-id-${item.key}`">问题 ID</label><input :id="`question-id-${item.key}`" v-model="item.question_id" class="input" required /></div><div class="form-field"><label :for="`question-type-${item.key}`">查询类型</label><select :id="`question-type-${item.key}`" v-model="item.query_type" class="select"><option value="rag">RAG</option><option value="sql">SQL</option><option value="sql+rag">SQL + RAG</option></select></div><div class="form-field form-field-full"><label :for="`question-text-${item.key}`">问题</label><textarea :id="`question-text-${item.key}`" v-model="item.question" class="textarea" required /></div><div class="form-field"><label :for="`question-docs-${item.key}`">期望文档 ID</label><textarea :id="`question-docs-${item.key}`" v-model="item.expected_document_ids" class="textarea compact-textarea" /></div><div class="form-field"><label :for="`question-chunks-${item.key}`">期望分块 ID</label><textarea :id="`question-chunks-${item.key}`" v-model="item.expected_chunk_ids" class="textarea compact-textarea" /></div><div class="form-field form-field-full"><label :for="`question-points-${item.key}`">期望答案要点（每行一项）</label><textarea :id="`question-points-${item.key}`" v-model="item.expected_answer_points" class="textarea compact-textarea" /></div><label class="checkbox-row"><input v-model="item.should_refuse" type="checkbox" />应当拒答</label></div>
      </article>
      <button class="button button-secondary" type="button" @click="questions.push(newQuestion())"><Plus :size="16" aria-hidden="true" />添加问题</button>
      <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
    </form>
    <template #footer><button class="button button-secondary" type="button" @click="modalOpen = false">取消</button><button class="button" type="submit" form="evaluation-form" :disabled="saving">{{ saving ? '运行中' : '运行' }}</button></template>
  </ModalDialog>
</template>
