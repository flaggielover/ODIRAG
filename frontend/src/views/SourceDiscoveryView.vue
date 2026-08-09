<script setup lang="ts">
import {
  Check,
  Eye,
  Gauge,
  Plus,
  RefreshCw,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  X,
  Zap,
} from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type {
  SourceCandidate,
  SourceDiscoveryEvent,
  SourceDiscoveryMetrics,
  SourceDiscoveryRun,
  SourceDiscoveryRunInput,
} from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import MetricTile from '@/components/MetricTile.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDateTime, formatNumber, formatPercent } from '@/utils/format'

const runs = ref<SourceDiscoveryRun[]>([])
const metrics = ref<SourceDiscoveryMetrics | null>(null)
const selectedRun = ref<SourceDiscoveryRun | null>(null)
const candidates = ref<SourceCandidate[]>([])
const runEvents = ref<SourceDiscoveryEvent[]>([])
const selectedCandidate = ref<SourceCandidate | null>(null)
const candidateEvents = ref<SourceDiscoveryEvent[]>([])
const loading = ref(false)
const detailLoading = ref(false)
const candidateLoading = ref(false)
const error = ref<string | null>(null)
const actionError = ref<string | null>(null)
const actionId = ref<number | null>(null)
const createOpen = ref(false)
const rejectOpen = ref(false)
const saving = ref(false)
const rejecting = ref<SourceCandidate | null>(null)

const form = reactive<SourceDiscoveryRunInput>(newRunForm())
const rejectForm = reactive({ reason: '' })

const candidateQuality = computed(() =>
  selectedCandidate.value?.quality_score === null || selectedCandidate.value?.quality_score === undefined
    ? '-'
    : formatPercent(selectedCandidate.value.quality_score),
)

onMounted(() => refresh())

function newRunForm(): SourceDiscoveryRunInput {
  return {
    topic: '',
    region: null,
    organization_level: null,
    query_text: null,
    required_source_count: 1,
    required_document_count: 3,
    max_candidates: 10,
    execution_mode: 'queued',
  }
}

function openCreate(): void {
  Object.assign(form, newRunForm())
  actionError.value = null
  createOpen.value = true
}

async function refresh(preferredRunId?: number, preferredCandidateId?: number): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [runResult, metricResult] = await Promise.all([
      api.sourceDiscoveryRuns(),
      api.sourceDiscoveryMetrics(),
    ])
    runs.value = runResult
    metrics.value = metricResult
    const runId = preferredRunId ?? selectedRun.value?.id ?? runResult[0]?.id
    if (runId) {
      await inspectRun(runId, preferredCandidateId ?? selectedCandidate.value?.id)
    } else {
      selectedRun.value = null
      candidates.value = []
      runEvents.value = []
      selectedCandidate.value = null
      candidateEvents.value = []
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '来源发现数据加载失败'
  } finally {
    loading.value = false
  }
}

async function inspectRun(runId: number, preferredCandidateId?: number): Promise<void> {
  detailLoading.value = true
  actionError.value = null
  try {
    const [runResult, candidateResult, eventResult] = await Promise.all([
      api.sourceDiscoveryRun(runId),
      api.sourceDiscoveryCandidates(runId),
      api.sourceDiscoveryRunEvents(runId),
    ])
    selectedRun.value = runResult
    candidates.value = candidateResult
    runEvents.value = eventResult
    const target =
      candidateResult.find((item) => item.id === preferredCandidateId) ?? candidateResult[0] ?? null
    if (target) await inspectCandidate(target.id)
    else {
      selectedCandidate.value = null
      candidateEvents.value = []
    }
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '发现运行详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

async function inspectCandidate(candidateId: number): Promise<void> {
  candidateLoading.value = true
  actionError.value = null
  try {
    const [candidateResult, eventResult] = await Promise.all([
      api.sourceCandidate(candidateId),
      api.sourceCandidateEvents(candidateId),
    ])
    selectedCandidate.value = candidateResult
    candidateEvents.value = eventResult
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '候选来源详情加载失败'
  } finally {
    candidateLoading.value = false
  }
}

async function createRun(): Promise<void> {
  saving.value = true
  actionError.value = null
  try {
    const created = await api.createSourceDiscoveryRun({
      ...form,
      region: form.region || null,
      organization_level: form.organization_level || null,
      query_text: form.query_text || null,
      max_candidates: form.max_candidates || null,
    })
    createOpen.value = false
    await refresh(created.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '发现运行创建失败'
  } finally {
    saving.value = false
  }
}

async function approve(candidate: SourceCandidate): Promise<void> {
  actionId.value = candidate.id
  actionError.value = null
  try {
    await api.approveSourceCandidate(candidate.id)
    await refresh(candidate.run_id, candidate.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '候选批准失败'
  } finally {
    actionId.value = null
  }
}

function openReject(candidate: SourceCandidate): void {
  rejecting.value = candidate
  rejectForm.reason = ''
  actionError.value = null
  rejectOpen.value = true
}

async function rejectCandidate(): Promise<void> {
  if (!rejecting.value || !rejectForm.reason.trim()) return
  const candidate = rejecting.value
  actionId.value = candidate.id
  saving.value = true
  actionError.value = null
  try {
    await api.rejectSourceCandidate(candidate.id, rejectForm.reason.trim())
    rejectOpen.value = false
    rejecting.value = null
    await refresh(candidate.run_id, candidate.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '候选拒绝失败'
  } finally {
    actionId.value = null
    saving.value = false
  }
}

async function activate(candidate: SourceCandidate): Promise<void> {
  actionId.value = candidate.id
  actionError.value = null
  try {
    await api.activateSourceCandidate(candidate.id)
    await refresh(candidate.run_id, candidate.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '来源激活失败'
  } finally {
    actionId.value = null
  }
}

async function retryRun(run: SourceDiscoveryRun): Promise<void> {
  actionId.value = -run.id
  actionError.value = null
  try {
    await api.retrySourceDiscoveryRun(run.id)
    await refresh(run.id)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '发现运行重试失败'
  } finally {
    actionId.value = null
  }
}
</script>

<template>
  <PageHeader title="来源发现" :meta="`${runs.length} 次发现运行`">
    <template #actions>
      <button class="button button-secondary" type="button" :disabled="loading" @click="refresh()">
        <RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新
      </button>
      <button class="button" type="button" @click="openCreate">
        <Plus :size="16" aria-hidden="true" />新建发现
      </button>
    </template>
  </PageHeader>

  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>

  <section v-if="metrics" class="metric-grid discovery-summary">
    <MetricTile label="待审批" :value="formatNumber(metrics.pending_approval_count)" :icon="ShieldCheck" />
    <MetricTile label="已激活来源" :value="formatNumber(metrics.activated_source_count)" :icon="Zap" tone="positive" />
    <MetricTile label="平均质量" :value="formatPercent(metrics.average_quality_score)" :icon="Gauge" />
    <MetricTile label="最近运行" :value="formatDateTime(metrics.last_run_at)" :icon="SearchCheck" />
  </section>

  <AsyncState :loading="loading" :error="error" :empty="runs.length === 0" empty-text="尚未创建来源发现运行" @retry="refresh()">
    <section class="monitoring-section">
      <div class="section-heading"><div><h2>发现运行</h2><span>{{ runs.length }} 条</span></div></div>
      <div class="table-frame">
        <div class="table-scroll">
          <table class="data-table discovery-runs-table">
            <thead><tr><th>主题</th><th>缺口</th><th>状态</th><th>现有 / 目标</th><th>候选 / 批准 / 激活</th><th>提供方</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in runs" :key="item.id" :class="{ 'row-selected': selectedRun?.id === item.id }">
                <td><span class="cell-primary">{{ item.topic }}</span><span class="cell-secondary">{{ item.region ?? '全部地区' }} · #{{ item.id }}</span></td>
                <td><StatusBadge :status="item.gap_detected ? 'gap_detected' : 'no_gap'" /></td>
                <td><StatusBadge :status="item.status" /></td>
                <td>{{ item.existing_source_count }} / {{ item.required_source_count }} 来源<br />{{ item.existing_document_count }} / {{ item.required_document_count }} 文档</td>
                <td>{{ item.candidate_count }} / {{ item.approved_count }} / {{ item.activated_count }}</td>
                <td>{{ item.discovery_provider }}</td>
                <td>{{ formatDateTime(item.created_at) }}</td>
                <td><div class="inline-actions"><button class="icon-button" type="button" title="查看发现运行" aria-label="查看发现运行" @click="inspectRun(item.id)"><Eye :size="16" aria-hidden="true" /></button><button class="icon-button" type="button" title="重试发现运行" aria-label="重试发现运行" :disabled="item.status !== 'failed' || actionId === -item.id" @click="retryRun(item)"><RotateCcw :size="16" aria-hidden="true" /></button></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <div v-if="selectedRun" class="quality-layout discovery-workspace">
      <section class="monitoring-section">
        <div class="section-heading"><div><h2>候选官方来源</h2><span>{{ candidates.length }} 个</span></div></div>
        <div v-if="detailLoading" class="state-panel">正在加载候选来源</div>
        <div v-else class="table-frame">
          <div class="table-scroll">
            <table class="data-table">
              <thead><tr><th>候选</th><th>官方性</th><th>质量</th><th>试抓</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="candidate in candidates" :key="candidate.id" :class="{ 'row-selected': selectedCandidate?.id === candidate.id }">
                  <td><button class="cell-link" type="button" @click="inspectCandidate(candidate.id)"><span class="cell-primary">{{ candidate.name }}</span><span class="cell-secondary">{{ candidate.domain }}</span></button></td>
                  <td><StatusBadge :status="candidate.official_status" /><span class="cell-secondary">{{ candidate.official_score === null ? '-' : formatPercent(candidate.official_score) }}</span></td>
                  <td>{{ candidate.quality_score === null ? '-' : formatPercent(candidate.quality_score) }}</td>
                  <td>{{ candidate.trial_success_count }} / {{ candidate.trial_document_count }}</td>
                  <td><StatusBadge :status="candidate.status" /></td>
                  <td><div class="inline-actions"><button class="icon-button success" type="button" title="批准候选" aria-label="批准候选" :disabled="candidate.status !== 'pending_approval' || actionId === candidate.id" @click="approve(candidate)"><Check :size="16" aria-hidden="true" /></button><button class="icon-button text-danger" type="button" title="拒绝候选" aria-label="拒绝候选" :disabled="candidate.status !== 'pending_approval' || actionId === candidate.id" @click="openReject(candidate)"><X :size="16" aria-hidden="true" /></button><button class="icon-button" type="button" title="激活来源" aria-label="激活来源" :disabled="candidate.status !== 'approved' || actionId === candidate.id" @click="activate(candidate)"><Zap :size="16" aria-hidden="true" /></button></div></td>
                </tr>
                <tr v-if="candidates.length === 0"><td colspan="6" class="muted">该运行尚无候选来源</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <aside class="quality-inspector panel discovery-inspector">
        <header class="panel-header"><h2>{{ selectedCandidate?.name ?? '候选证据' }}</h2><StatusBadge v-if="selectedCandidate" :status="selectedCandidate.status" /></header>
        <div v-if="candidateLoading" class="state-panel">正在加载候选证据</div>
        <div v-else-if="selectedCandidate" class="panel-body stack-list">
          <dl class="definition-grid definition-single">
            <div class="definition-item"><dt>主页</dt><dd><a :href="selectedCandidate.canonical_homepage_url" target="_blank" rel="noopener noreferrer">{{ selectedCandidate.domain }}</a></dd></div>
            <div class="definition-item"><dt>官方性 / 质量</dt><dd>{{ selectedCandidate.official_score === null ? '-' : formatPercent(selectedCandidate.official_score) }} / {{ candidateQuality }}</dd></div>
            <div class="definition-item"><dt>验证 HTTP</dt><dd>{{ selectedCandidate.validation_status_code ?? '-' }}</dd></div>
            <div class="definition-item"><dt>试抓成功 / 失败</dt><dd>{{ selectedCandidate.trial_success_count }} / {{ selectedCandidate.trial_failed_count }}</dd></div>
            <div class="definition-item"><dt>平均正文字符</dt><dd>{{ formatNumber(selectedCandidate.trial_average_chars) }}</dd></div>
            <div v-if="selectedCandidate.source_id" class="definition-item"><dt>已激活 Source ID</dt><dd>{{ selectedCandidate.source_id }}</dd></div>
            <div v-if="selectedCandidate.rejection_reason" class="definition-item"><dt>拒绝原因</dt><dd>{{ selectedCandidate.rejection_reason }}</dd></div>
          </dl>
          <JsonPanel label="官方验证证据" :value="selectedCandidate.official_evidence_json" />
          <JsonPanel label="质量拆分" :value="selectedCandidate.quality_breakdown_json" />
          <section class="discovery-inspector-section">
            <div class="section-heading"><div><h2>试抓栏目</h2><span>{{ selectedCandidate.columns.length }} 个</span></div></div>
            <div class="table-scroll"><table class="data-table"><thead><tr><th>栏目</th><th>成功 / 失败</th><th>质量</th></tr></thead><tbody><tr v-for="column in selectedCandidate.columns" :key="column.id"><td><a :href="column.column_url" target="_blank" rel="noopener noreferrer">{{ column.column_name }}</a><span class="cell-secondary">{{ column.parser_type }}</span></td><td>{{ column.trial_success_count }} / {{ column.trial_failed_count }}</td><td>{{ column.quality_score === null ? '-' : formatPercent(column.quality_score) }}</td></tr></tbody></table></div>
          </section>
        </div>
        <div v-else class="state-panel">选择候选来源查看证据</div>
      </aside>
    </div>

    <section v-if="selectedRun" class="monitoring-section">
      <div class="section-heading"><div><h2>发现事件</h2><span>{{ (selectedCandidate ? candidateEvents : runEvents).length }} 条</span></div></div>
      <div class="table-frame"><div class="table-scroll"><table class="data-table"><thead><tr><th>阶段</th><th>状态变化</th><th>说明</th><th>时间</th></tr></thead><tbody><tr v-for="event in (selectedCandidate ? candidateEvents : runEvents)" :key="event.id"><td>{{ event.stage }}</td><td><span class="mono">{{ event.from_status ?? '-' }} → {{ event.to_status }}</span></td><td>{{ event.message }}</td><td>{{ formatDateTime(event.created_at) }}</td></tr><tr v-if="(selectedCandidate ? candidateEvents : runEvents).length === 0"><td colspan="4" class="muted">暂无事件</td></tr></tbody></table></div></div>
    </section>
  </AsyncState>

  <ModalDialog :open="createOpen" title="新建来源发现" width="large" @close="createOpen = false">
    <form id="source-discovery-form" class="form-grid" @submit.prevent="createRun">
      <div class="form-field"><label for="discovery-topic">内容主题</label><input id="discovery-topic" v-model="form.topic" class="input" required maxlength="255" /></div>
      <div class="form-field"><label for="discovery-region">地区</label><input id="discovery-region" v-model="form.region" class="input" maxlength="128" /></div>
      <div class="form-field"><label for="discovery-level">机构层级</label><select id="discovery-level" v-model="form.organization_level" class="select"><option :value="null">不限</option><option value="national">国家级</option><option value="provincial">省级</option><option value="municipal">市级</option><option value="county">区县级</option></select></div>
      <div class="form-field"><label for="discovery-mode">执行方式</label><select id="discovery-mode" v-model="form.execution_mode" class="select"><option value="queued">后台队列</option><option value="inline">立即执行</option></select></div>
      <div class="form-field"><label for="discovery-source-count">目标来源数</label><input id="discovery-source-count" v-model.number="form.required_source_count" class="input" type="number" min="1" max="100" required /></div>
      <div class="form-field"><label for="discovery-document-count">目标文档数</label><input id="discovery-document-count" v-model.number="form.required_document_count" class="input" type="number" min="0" max="10000" required /></div>
      <div class="form-field"><label for="discovery-max-candidates">最多候选数</label><input id="discovery-max-candidates" v-model.number="form.max_candidates" class="input" type="number" min="1" max="100" /></div>
      <div class="form-field form-field-full"><label for="discovery-query">发现查询（可选）</label><textarea id="discovery-query" v-model="form.query_text" class="textarea" maxlength="1000" placeholder="留空时由主题、地区和机构层级生成" /></div>
      <div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div>
    </form>
    <template #footer><button class="button button-secondary" type="button" @click="createOpen = false">取消</button><button class="button" type="submit" form="source-discovery-form" :disabled="saving">{{ saving ? '创建中' : '创建运行' }}</button></template>
  </ModalDialog>

  <ModalDialog :open="rejectOpen" title="拒绝候选来源" @close="rejectOpen = false">
    <form id="source-candidate-reject-form" class="stack-list" @submit.prevent="rejectCandidate">
      <p>拒绝“{{ rejecting?.name }}”后，该候选不会被激活为正式来源。</p>
      <div class="form-field"><label for="source-candidate-reason">拒绝原因</label><textarea id="source-candidate-reason" v-model="rejectForm.reason" class="textarea" required maxlength="2000" /></div>
      <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
    </form>
    <template #footer><button class="button button-secondary" type="button" @click="rejectOpen = false">取消</button><button class="button button-danger" type="submit" form="source-candidate-reject-form" :disabled="saving || !rejectForm.reason.trim()">拒绝候选</button></template>
  </ModalDialog>
</template>
