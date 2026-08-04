<script setup lang="ts">
import { Ban, ExternalLink, Plus, RefreshCw, RotateCcw } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { CozeContract, CrawlProvider, CrawlTask, CrawlTaskInput, Source } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime, formatNumber } from '@/utils/format'

const tasks = ref<CrawlTask[]>([])
const sources = ref<Source[]>([])
const statusFilter = ref('')
const modalOpen = ref(false)
const actionError = ref<string | null>(null)
const actionId = ref<number | null>(null)
const saving = ref(false)
const { loading, error, run } = useAsyncTask()
const form = reactive<CrawlTaskInput>({
  source_column_id: 0,
  task_type: 'incremental',
  trigger_type: 'manual',
  execution_mode: 'queued',
  provider_contract: 'batch_crawl',
  max_articles: 5,
  max_pages: 1,
})

const columns = computed(() => sources.value.flatMap((source) => source.columns.map((column) => ({ ...column, sourceName: source.name }))))
const activeStatuses = ['pending', 'queued', 'calling_coze', 'coze_running', 'normalizing', 'saving_documents', 'waiting_review', 'running']
const retryableStatuses = ['failed', 'partial_failed', 'cancelled']

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    const [taskResult, sourceResult] = await Promise.all([api.crawlTasks(statusFilter.value || undefined), api.sources(true)])
    tasks.value = taskResult
    sources.value = sourceResult
    if (form.source_column_id === 0 && columns.value[0]) form.source_column_id = columns.value[0].id
  })
}

async function create(): Promise<void> {
  saving.value = true
  actionError.value = null
  try {
    await api.createCrawlTask(form)
    modalOpen.value = false
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '任务创建失败'
  } finally {
    saving.value = false
  }
}

async function retryTask(task: CrawlTask): Promise<void> {
  actionId.value = task.id
  actionError.value = null
  try { await api.retryCrawlTask(task.id); await load() } catch (caught) { actionError.value = caught instanceof Error ? caught.message : '重试失败' } finally { actionId.value = null }
}

async function cancelTask(task: CrawlTask): Promise<void> {
  actionId.value = task.id
  actionError.value = null
  try { await api.cancelCrawlTask(task.id); await load() } catch (caught) { actionError.value = caught instanceof Error ? caught.message : '取消失败' } finally { actionId.value = null }
}

function providerLabel(provider: CrawlProvider | undefined): string {
  return provider === 'local' ? 'Local 调试' : provider === 'playwright' ? 'Playwright' : 'Coze 工作流'
}

function stageCount(task: CrawlTask): string {
  const counts = task.stage_counts ?? {}
  const entries = Object.entries(counts).filter(([, value]) => value > 0)
  return entries.length ? entries.map(([key, value]) => `${key}:${formatNumber(value)}`).join(' · ') : '-'
}

function taskProvider(task: CrawlTask): CrawlProvider {
  return task.crawl_provider ?? task.provider ?? 'coze'
}

function taskContract(task: CrawlTask): CozeContract | null {
  return task.provider_contract ?? task.contract_mode ?? null
}

function taskStage(task: CrawlTask): string | null {
  return task.current_stage ?? task.stage ?? null
}

function taskErrorCode(task: CrawlTask): string | null {
  return task.provider_error_code ?? null
}
</script>

<template>
  <PageHeader title="抓取任务" :meta="`${tasks.length} 个任务`">
    <template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button><button class="button" type="button" :disabled="columns.length === 0" @click="modalOpen = true"><Plus :size="16" aria-hidden="true" />新建任务</button></template>
  </PageHeader>

  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
  <div class="filter-bar"><div class="form-field"><label for="task-status">状态</label><select id="task-status" v-model="statusFilter" class="select" @change="load"><option value="">全部</option><option value="pending">待处理</option><option value="queued">排队中</option><option value="calling_coze">调用 Coze</option><option value="coze_running">Coze 抓取中</option><option value="normalizing">结果标准化</option><option value="saving_documents">保存文档</option><option value="waiting_review">等待审核</option><option value="completed">已完成</option><option value="partial_failed">部分失败</option><option value="failed">失败</option><option value="cancelled">已取消</option></select></div></div>

  <AsyncState :loading="loading" :error="error" :empty="tasks.length === 0" empty-text="没有抓取任务" @retry="load">
    <div class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>任务</th><th>Provider</th><th>状态</th><th>阶段计数</th><th>发现 / 抓取</th><th>成功 / 失败</th><th>Coze 执行</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="task in tasks" :key="task.id">
        <td><RouterLink class="cell-primary" :to="`/crawl-tasks/${task.id}`">#{{ task.id }} · {{ task.task_type }} <ExternalLink :size="13" aria-hidden="true" /></RouterLink><span class="cell-secondary">栏目 {{ task.source_column_id }} · {{ task.trigger_type }}</span></td>
        <td><span class="cell-primary">{{ providerLabel(taskProvider(task)) }}</span><span v-if="taskContract(task)" class="cell-secondary">{{ taskContract(task) }}</span></td>
        <td><StatusBadge :status="task.status" /><span v-if="taskStage(task)" class="cell-secondary">{{ taskStage(task) }}</span></td>
        <td class="stage-counts">{{ stageCount(task) }}</td>
        <td>{{ formatNumber(task.discovered_count) }} / {{ formatNumber(task.fetched_count) }}</td>
        <td>{{ formatNumber(task.success_count) }} / <span :class="{ danger: task.failed_count > 0 }">{{ formatNumber(task.failed_count) }}</span></td>
        <td><span v-if="task.coze_execution_id || task.provider_task_id" class="mono">{{ task.coze_execution_id || task.provider_task_id }}</span><span v-else class="muted">-</span><span v-if="taskErrorCode(task)" class="cell-secondary danger">{{ taskErrorCode(task) }}</span></td>
        <td>{{ formatDateTime(task.created_at) }}</td>
        <td><div class="inline-actions"><button class="icon-button" type="button" title="重试" aria-label="重试" :disabled="actionId === task.id || !retryableStatuses.includes(task.status)" @click="retryTask(task)"><RotateCcw :size="16" aria-hidden="true" /></button><button class="icon-button text-danger" type="button" title="取消" aria-label="取消" :disabled="actionId === task.id || !activeStatuses.includes(task.status)" @click="cancelTask(task)"><Ban :size="16" aria-hidden="true" /></button></div></td>
      </tr>
    </tbody></table></div></div>
  </AsyncState>

  <ModalDialog :open="modalOpen" title="新建抓取任务" @close="modalOpen = false"><form id="crawl-form" class="form-grid" @submit.prevent="create"><div class="form-field form-field-full"><label for="crawl-column">来源栏目</label><select id="crawl-column" v-model.number="form.source_column_id" class="select" required><option v-for="column in columns" :key="column.id" :value="column.id">{{ column.sourceName }} / {{ column.column_name }}</option></select></div><div class="form-field"><label for="crawl-contract">Coze 契约</label><select id="crawl-contract" v-model="form.provider_contract" class="select"><option value="batch_crawl">批量抓取（默认）</option><option value="legacy_single_article">单篇筛选（兼容）</option></select></div><div class="form-field"><label for="crawl-type">任务类型</label><select id="crawl-type" v-model="form.task_type" class="select"><option value="incremental">增量</option><option value="full">全量</option></select></div><div class="form-field"><label for="crawl-mode">执行方式</label><select id="crawl-mode" v-model="form.execution_mode" class="select"><option value="queued">队列</option><option value="inline">立即执行</option></select></div><div class="form-field"><label for="crawl-max-articles">最多文章</label><input id="crawl-max-articles" v-model.number="form.max_articles" class="input" type="number" min="1" max="100" /></div><div class="form-field"><label for="crawl-max-pages">最多页数</label><input id="crawl-max-pages" v-model.number="form.max_pages" class="input" type="number" min="1" max="100" /></div><div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div></form><template #footer><button class="button button-secondary" type="button" @click="modalOpen = false">取消</button><button class="button" type="submit" form="crawl-form" :disabled="saving">{{ saving ? '创建中...' : '创建' }}</button></template></ModalDialog>
</template>

<style scoped>
.stage-counts { max-width: 240px; white-space: normal; font-size: 12px; color: var(--color-text-muted); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
</style>
