<script setup lang="ts">
import { BarChart3, Eye, FlaskConical, Play, Plus, RefreshCw } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { Experiment, ExperimentComparison } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime } from '@/utils/format'

const experiments = ref<Experiment[]>([])
const selected = ref<Experiment | null>(null)
const comparison = ref<ExperimentComparison | null>(null)
const createOpen = ref(false)
const runOpen = ref(false)
const saving = ref(false)
const comparisonLoading = ref(false)
const actionError = ref<string | null>(null)
const { loading, error, run } = useAsyncTask()
const createForm = reactive({
  experiment_name: '',
  experiment_type: 'retrieval',
  baseline: JSON.stringify({ chunking: { target_chars: 600, min_chars: 160, max_chars: 900, overlap_chars: 100 }, top_k: 5, rerank: 'deterministic', prompt_version: 'baseline-v1' }, null, 2),
  candidate: JSON.stringify({ chunking: { target_chars: 800, min_chars: 160, max_chars: 1200, overlap_chars: 120 }, top_k: 5, rrf_k: 30, rerank: false, score_threshold: 0, prompt_version: 'candidate-v1' }, null, 2),
})
const runForm = reactive({ question_ids: '', category: '', regression_tolerance: 0 })

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    experiments.value = await api.experiments(200)
  })
}

function openCreate(): void {
  createForm.experiment_name = `retrieval_${new Date().toISOString().slice(0, 10).replaceAll('-', '_')}`
  actionError.value = null
  createOpen.value = true
}

async function createExperiment(): Promise<void> {
  saving.value = true
  actionError.value = null
  try {
    const created = await api.createExperiment({
      experiment_name: createForm.experiment_name,
      experiment_type: createForm.experiment_type,
      baseline_config: JSON.parse(createForm.baseline) as Record<string, unknown>,
      candidate_config: JSON.parse(createForm.candidate) as Record<string, unknown>,
    })
    createOpen.value = false
    await load()
    selected.value = created
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '实验创建失败'
  } finally {
    saving.value = false
  }
}

function openRun(item: Experiment): void {
  selected.value = item
  runForm.question_ids = ''
  runForm.category = ''
  runForm.regression_tolerance = 0
  actionError.value = null
  runOpen.value = true
}

async function executeExperiment(): Promise<void> {
  if (!selected.value) return
  saving.value = true
  actionError.value = null
  try {
    const completed = await api.runExperiment(selected.value.id, {
      question_ids: runForm.question_ids.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
      questions: [],
      category: runForm.category || null,
      regression_tolerance: runForm.regression_tolerance,
    })
    runOpen.value = false
    await load()
    await showComparison(completed)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '实验运行失败'
  } finally {
    saving.value = false
  }
}

async function showComparison(item: Experiment): Promise<void> {
  selected.value = item
  comparison.value = null
  comparisonLoading.value = true
  actionError.value = null
  try {
    comparison.value = await api.experimentComparison(item.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '实验比较报告不可用'
  } finally {
    comparisonLoading.value = false
  }
}
</script>

<template>
  <PageHeader title="实验" :meta="`${experiments.length} 个实验`"><template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button><button class="button" type="button" @click="openCreate"><Plus :size="16" aria-hidden="true" />新建实验</button></template></PageHeader>
  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
  <AsyncState :loading="loading" :error="error" :empty="experiments.length === 0" empty-text="暂无实验" @retry="load">
    <div class="quality-layout">
      <section class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>实验</th><th>类型</th><th>状态</th><th>结论</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in experiments" :key="item.id" :class="{ 'row-selected': selected?.id === item.id }"><td><span class="cell-primary">{{ item.experiment_name }}</span><span class="cell-secondary">#{{ item.id }}</span></td><td>{{ item.experiment_type }}</td><td><StatusBadge :status="item.status" /></td><td><span class="cell-primary">{{ item.conclusion ?? '-' }}</span></td><td>{{ formatDateTime(item.created_at) }}</td><td><div class="inline-actions"><button class="icon-button" type="button" title="运行" aria-label="运行" @click="openRun(item)"><Play :size="16" aria-hidden="true" /></button><button class="icon-button" type="button" title="比较" aria-label="比较" :disabled="item.status !== 'completed'" @click="showComparison(item)"><Eye :size="16" aria-hidden="true" /></button></div></td></tr></tbody></table></div></section>
      <aside class="quality-inspector panel"><header class="panel-header"><h2>{{ selected?.experiment_name ?? '实验比较' }}</h2><BarChart3 :size="17" aria-hidden="true" /></header><div v-if="comparisonLoading" class="state-panel">正在加载比较报告</div><div v-else-if="comparison" class="panel-body stack-list"><div class="notice" :class="comparison.regressions.length ? 'notice-error' : 'notice-success'"><FlaskConical :size="17" aria-hidden="true" /><span>{{ comparison.conclusion }}</span></div><JsonPanel label="指标比较" :value="comparison.comparisons" /><JsonPanel label="回归" :value="comparison.regressions" /><JsonPanel label="失败案例" :value="comparison.failed_cases" /></div><div v-else class="state-panel">选择已完成实验查看比较</div></aside>
    </div>
  </AsyncState>

  <ModalDialog :open="createOpen" title="新建实验" width="large" @close="createOpen = false"><form id="experiment-create" class="form-grid" @submit.prevent="createExperiment"><div class="form-field"><label for="experiment-name">实验名称</label><input id="experiment-name" v-model="createForm.experiment_name" class="input" required pattern="[A-Za-z0-9][A-Za-z0-9_.-]*" /></div><div class="form-field"><label for="experiment-type">类型</label><input id="experiment-type" v-model="createForm.experiment_type" class="input" required /></div><div class="form-field"><label for="baseline-config">基线配置 JSON</label><textarea id="baseline-config" v-model="createForm.baseline" class="textarea code-textarea" required /></div><div class="form-field"><label for="candidate-config">候选配置 JSON</label><textarea id="candidate-config" v-model="createForm.candidate" class="textarea code-textarea" required /></div><div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div></form><template #footer><button class="button button-secondary" type="button" @click="createOpen = false">取消</button><button class="button" type="submit" form="experiment-create" :disabled="saving">{{ saving ? '创建中' : '创建' }}</button></template></ModalDialog>

  <ModalDialog :open="runOpen" title="运行实验" @close="runOpen = false"><form id="experiment-run" class="form-grid" @submit.prevent="executeExperiment"><div class="form-field form-field-full"><label for="experiment-question-ids">评估问题 ID（逗号或换行分隔）</label><textarea id="experiment-question-ids" v-model="runForm.question_ids" class="textarea" required /></div><div class="form-field"><label for="experiment-category">类别筛选</label><input id="experiment-category" v-model="runForm.category" class="input" /></div><div class="form-field"><label for="experiment-tolerance">回归容差</label><input id="experiment-tolerance" v-model.number="runForm.regression_tolerance" class="input" type="number" min="0" step="0.001" /></div><div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div></form><template #footer><button class="button button-secondary" type="button" @click="runOpen = false">取消</button><button class="button" type="submit" form="experiment-run" :disabled="saving">{{ saving ? '运行中' : '运行' }}</button></template></ModalDialog>
</template>
