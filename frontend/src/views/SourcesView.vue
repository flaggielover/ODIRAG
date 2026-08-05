<script setup lang="ts">
import { FlaskConical, Pencil, Plus, RefreshCw, Trash2 } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { CozeConnectionResult, CozeContract, CozeStatus, CrawlProvider, Source, SourceInput, SourceTestResult } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime, formatDuration } from '@/utils/format'

const sources = ref<Source[]>([])
const enabledFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const modalOpen = ref(false)
const editing = ref<Source | null>(null)
const deleting = ref<Source | null>(null)
type ConnectivityState = { provider: 'coze' | 'local'; result: SourceTestResult | CozeConnectionResult }
const tests = reactive<Record<number, ConnectivityState>>({})
const testing = ref<{ id: number; provider: 'coze' | 'local' } | null>(null)
const cozeStatus = ref<CozeStatus | null>(null)
const actionError = ref<string | null>(null)
const saving = ref(false)
const { loading, error, run } = useAsyncTask()

const form = reactive<SourceInput>(newForm())
const visibleSources = computed(() => {
  if (enabledFilter.value === 'all') return sources.value
  return sources.value.filter((source) => source.enabled === (enabledFilter.value === 'enabled'))
})

onMounted(load)

function newForm(): SourceInput {
  return {
    source_key: '',
    name: '',
    domain: '',
    region: null,
    city: null,
    organization_level: null,
    organization_type: null,
    official_status: 'official',
    homepage_url: '',
    enabled: true,
    priority: 0,
    crawl_frequency: 'daily',
    crawl_provider: 'coze',
    coze_contract_mode: 'batch_crawl',
    columns: [
      {
        column_key: 'policies',
        column_name: '政策文件',
        column_url: '',
        parser_type: 'html',
        enabled: true,
        max_pages: 100,
        request_interval_seconds: 1,
        selectors_json: {},
        pagination_json: {},
      },
    ],
  }
}

async function load(): Promise<void> {
  await run(async () => {
    const [sourceResult, statusResult] = await Promise.allSettled([api.sources(), api.cozeStatus()])
    if (sourceResult.status === 'rejected') throw sourceResult.reason
    sources.value = sourceResult.value
    cozeStatus.value = statusResult.status === 'fulfilled' ? statusResult.value : null
  })
}

function openCreate(): void {
  Object.assign(form, newForm())
  editing.value = null
  actionError.value = null
  modalOpen.value = true
}

function openEdit(source: Source): void {
  editing.value = source
  actionError.value = null
  Object.assign(form, {
    source_key: source.source_key,
    name: source.name,
    domain: source.domain,
    region: source.region,
    city: source.city,
    organization_level: source.organization_level,
    organization_type: source.organization_type,
    official_status: source.official_status,
    homepage_url: source.homepage_url,
    enabled: source.enabled,
    priority: source.priority,
    crawl_frequency: source.crawl_frequency,
    crawl_provider: source.crawl_provider ?? 'coze',
    coze_contract_mode: source.coze_contract_mode ?? 'batch_crawl',
    columns: [],
  })
  modalOpen.value = true
}

async function save(): Promise<void> {
  saving.value = true
  actionError.value = null
  try {
    if (editing.value) {
      await api.updateSource(editing.value.id, {
        name: form.name,
        domain: form.domain,
        region: form.region,
        city: form.city,
        organization_level: form.organization_level,
        organization_type: form.organization_type,
        official_status: form.official_status,
        homepage_url: form.homepage_url,
        enabled: form.enabled,
        priority: form.priority,
        crawl_frequency: form.crawl_frequency,
        crawl_provider: form.crawl_provider,
        coze_contract_mode: form.coze_contract_mode,
      })
    } else {
      await api.createSource(form)
    }
    modalOpen.value = false
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function testProvider(source: Source, provider: 'coze' | 'local'): Promise<void> {
  testing.value = { id: source.id, provider }
  actionError.value = null
  try {
    const contract: CozeContract = source.coze_contract_mode ?? cozeStatus.value?.default_contract ?? 'batch_crawl'
    tests[source.id] = provider === 'coze'
      ? { provider, result: await api.testSourceCoze(source.id, contract) }
      : { provider, result: await api.testSourceLocal(source.id) }
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '连通性测试失败'
  } finally {
    testing.value = null
  }
}

async function remove(): Promise<void> {
  if (!deleting.value) return
  saving.value = true
  actionError.value = null
  try {
    await api.deleteSource(deleting.value.id)
    deleting.value = null
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '删除失败'
  } finally {
    saving.value = false
  }
}

function providerLabel(provider: CrawlProvider | undefined): string {
  return provider === 'local' ? 'Local 调试' : provider === 'playwright' ? 'Playwright' : 'Coze 工作流'
}

function connectivityAvailable(state: ConnectivityState): boolean {
  return state.provider === 'coze' ? state.result.available : state.result.reachable
}

function connectivityLatency(state: ConnectivityState): number {
  return state.result.latency_ms
}

function connectivityError(state: ConnectivityState): string | null {
  return state.provider === 'coze' ? state.result.error_code : state.result.error_type
}

function isCozeContractConfigured(contract: CozeContract): boolean {
  const status = cozeStatus.value
  if (!status) return false
  return status.enabled && status.token_configured && (contract === 'batch_crawl' ? status.batch_workflow_configured : status.legacy_workflow_configured)
}
</script>

<template>
  <PageHeader title="来源" :meta="`${visibleSources.length} 个来源`">
    <template #actions>
      <button class="button button-secondary" type="button" :disabled="loading" @click="load">
        <RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新
      </button>
      <button class="button" type="button" @click="openCreate">
        <Plus :size="16" aria-hidden="true" />新增来源
      </button>
    </template>
  </PageHeader>

  <div class="dependency-strip" role="status">
    <div v-if="cozeStatus" class="coze-contract-statuses">
      <span data-testid="coze-contract-status-batch"><span class="cell-secondary">Coze 批量工作流</span><StatusBadge :status="isCozeContractConfigured('batch_crawl') ? 'healthy' : 'unavailable'" /></span>
      <span data-testid="coze-contract-status-legacy"><span class="cell-secondary">Coze 单篇筛选工作流</span><StatusBadge :status="isCozeContractConfigured('legacy_single_article') ? 'healthy' : 'unavailable'" /></span>
    </div>
    <span>业务抓取：Coze 工作流</span>
    <StatusBadge v-if="cozeStatus" :status="isCozeContractConfigured(cozeStatus.default_contract) ? 'healthy' : 'unavailable'" />
    <span v-if="cozeStatus" class="cell-secondary">{{ cozeStatus.batch_workflow_configured ? '批量工作流已配置' : '批量工作流未配置' }} · 默认 {{ cozeStatus.default_contract }}</span>
    <span v-else class="cell-secondary">配置状态暂不可用</span>
  </div>

  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>

  <div class="filter-bar">
    <div class="segmented" aria-label="启用状态筛选">
      <button type="button" :class="{ active: enabledFilter === 'all' }" @click="enabledFilter = 'all'">全部</button>
      <button type="button" :class="{ active: enabledFilter === 'enabled' }" @click="enabledFilter = 'enabled'">启用</button>
      <button type="button" :class="{ active: enabledFilter === 'disabled' }" @click="enabledFilter = 'disabled'">停用</button>
    </div>
  </div>

  <AsyncState :loading="loading" :error="error" :empty="visibleSources.length === 0" empty-text="没有配置的来源" @retry="load">
    <div class="table-frame">
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>来源</th><th>状态</th><th>抓取 Provider</th><th>地区</th><th>栏目</th><th>最近抓取</th><th>连通性</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="source in visibleSources" :key="source.id">
              <td><a class="cell-primary" :href="source.homepage_url" target="_blank" rel="noopener noreferrer">{{ source.name }}</a><span class="cell-secondary">{{ source.domain }} · {{ source.source_key }}</span></td>
              <td><StatusBadge :status="source.enabled" /></td>
              <td><StatusBadge :status="source.crawl_provider === 'coze' || !source.crawl_provider ? 'coze' : source.crawl_provider" /><span class="cell-secondary">{{ providerLabel(source.crawl_provider) }}<template v-if="source.coze_contract_mode"> · {{ source.coze_contract_mode }}</template></span></td>
              <td>{{ [source.region, source.city].filter(Boolean).join(' / ') || '-' }}</td>
              <td>{{ source.columns.length }}</td>
              <td>{{ formatDateTime(source.last_crawl_time) }}</td>
              <td>
                <span v-if="testing?.id === source.id" class="muted">测试中...</span>
                <template v-else-if="tests[source.id]"><StatusBadge :status="connectivityAvailable(tests[source.id]!) ? 'reachable' : 'unavailable'" /><span class="cell-secondary">{{ tests[source.id]!.provider === 'local' ? 'Local' : 'Coze' }} · {{ formatDuration(connectivityLatency(tests[source.id]!)) }}</span><span v-if="connectivityError(tests[source.id]!)" class="cell-secondary danger">{{ connectivityError(tests[source.id]!) }}</span></template>
                <template v-else-if="source.last_coze_status"><StatusBadge :status="source.last_coze_status" /><span class="cell-secondary">Coze · {{ source.last_coze_article_count ?? 0 }} 篇</span><span v-if="source.last_coze_error" class="cell-secondary danger">{{ source.last_coze_error }}</span></template>
                <span v-else class="muted">未测试</span>
              </td>
              <td><div class="inline-actions"><button class="icon-button" type="button" title="测试 Coze 工作流" aria-label="测试 Coze 工作流" :disabled="Boolean(testing)" @click="testProvider(source, 'coze')"><FlaskConical :size="16" aria-hidden="true" /></button><button class="icon-button" type="button" title="测试本地连通性" aria-label="测试本地连通性" :disabled="Boolean(testing)" @click="testProvider(source, 'local')"><span class="provider-local-dot" aria-hidden="true">L</span></button><button class="icon-button" type="button" title="编辑" aria-label="编辑" @click="openEdit(source)"><Pencil :size="16" aria-hidden="true" /></button><button class="icon-button text-danger" type="button" title="删除" aria-label="删除" @click="deleting = source"><Trash2 :size="16" aria-hidden="true" /></button></div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </AsyncState>

  <ModalDialog :open="modalOpen" :title="editing ? '编辑来源' : '新增来源'" width="large" @close="modalOpen = false">
    <form id="source-form" class="form-grid" @submit.prevent="save">
      <div class="form-field"><label for="source-key">来源键</label><input id="source-key" v-model="form.source_key" class="input" required :disabled="Boolean(editing)" pattern="[a-zA-Z0-9_-]+" /></div>
      <div class="form-field"><label for="source-name">名称</label><input id="source-name" v-model="form.name" class="input" required /></div>
      <div class="form-field"><label for="source-domain">域名</label><input id="source-domain" v-model="form.domain" class="input" required /></div>
      <div class="form-field"><label for="source-homepage">主页 URL</label><input id="source-homepage" v-model="form.homepage_url" class="input" type="url" required /></div>
      <div class="form-field"><label for="source-provider">抓取 Provider</label><select id="source-provider" v-model="form.crawl_provider" class="select"><option value="coze">Coze 工作流（默认）</option><option value="local">Local（调试/兜底）</option><option value="playwright">Playwright</option></select></div>
      <div class="form-field"><label for="source-contract">Coze 契约</label><select id="source-contract" v-model="form.coze_contract_mode" class="select"><option value="batch_crawl">批量抓取</option><option value="legacy_single_article">单篇筛选（兼容）</option></select></div>
      <div class="form-field"><label for="source-region">地区</label><input id="source-region" v-model="form.region" class="input" /></div>
      <div class="form-field"><label for="source-city">城市</label><input id="source-city" v-model="form.city" class="input" /></div>
      <div class="form-field"><label for="source-frequency">抓取频率</label><select id="source-frequency" v-model="form.crawl_frequency" class="select"><option value="hourly">每小时</option><option value="daily">每天</option><option value="weekly">每周</option><option value="manual">手动</option></select></div>
      <div class="form-field"><label for="source-priority">优先级</label><input id="source-priority" v-model.number="form.priority" class="input" type="number" min="0" max="10000" /></div>
      <label class="checkbox-row"><input v-model="form.enabled" type="checkbox" />启用来源</label>
      <template v-if="!editing"><div class="form-field form-field-full"><span class="field-label">初始栏目</span></div><div class="form-field"><label for="column-key">栏目键</label><input id="column-key" v-model="form.columns[0]!.column_key" class="input" required /></div><div class="form-field"><label for="column-name">栏目名称</label><input id="column-name" v-model="form.columns[0]!.column_name" class="input" required /></div><div class="form-field form-field-full"><label for="column-url">栏目 URL</label><input id="column-url" v-model="form.columns[0]!.column_url" class="input" type="url" required /></div></template>
      <div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div>
    </form>
    <template #footer><button class="button button-secondary" type="button" @click="modalOpen = false">取消</button><button class="button" type="submit" form="source-form" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button></template>
  </ModalDialog>

  <ModalDialog :open="Boolean(deleting)" title="删除来源" width="small" @close="deleting = null"><p>确认删除“{{ deleting?.name }}”？有关联数据时后端会拒绝该操作。</p><template #footer><button class="button button-secondary" type="button" @click="deleting = null">取消</button><button class="button button-danger" type="button" :disabled="saving" @click="remove">删除</button></template></ModalDialog>
</template>

<style scoped>
.dependency-strip { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.coze-contract-statuses { display: flex; flex-wrap: wrap; gap: 10px; }
.coze-contract-statuses > span { display: inline-flex; align-items: center; gap: 6px; }
.provider-local-dot { display: inline-grid; place-items: center; width: 16px; height: 16px; border: 1px solid currentColor; border-radius: 50%; font-size: 10px; font-weight: 700; }
</style>
