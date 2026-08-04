<script setup lang="ts">
import { FileText, RefreshCw, Search } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '@/api/resources'
import type { DocumentSummary, Source } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDate, formatDateTime, formatNumber } from '@/utils/format'

const documents = ref<DocumentSummary[]>([])
const sources = ref<Source[]>([])
const filters = reactive({ q: '', final_status: '', index_status: '', source_id: '' })
const { loading, error, run } = useAsyncTask()

onMounted(async () => {
  sources.value = await api.sources().catch(() => [])
  await load()
})

async function load(): Promise<void> {
  await run(async () => {
    documents.value = await api.documents({
      q: filters.q || undefined,
      final_status: filters.final_status || undefined,
      index_status: filters.index_status || undefined,
      source_id: filters.source_id ? Number(filters.source_id) : undefined,
      limit: 300,
    })
  })
}

function reset(): void {
  filters.q = ''
  filters.final_status = ''
  filters.index_status = ''
  filters.source_id = ''
  void load()
}
</script>

<template>
  <PageHeader title="文档" :meta="`${documents.length} 篇文档`">
    <template #actions>
      <button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button>
    </template>
  </PageHeader>

  <form class="filter-bar" @submit.prevent="load">
    <div class="form-field">
      <label for="document-query">搜索</label>
      <div class="input-with-icon"><Search :size="16" aria-hidden="true" /><input id="document-query" v-model="filters.q" class="input" placeholder="标题、文号或正文" /></div>
    </div>
    <div class="form-field"><label for="document-source">来源</label><select id="document-source" v-model="filters.source_id" class="select"><option value="">全部</option><option v-for="source in sources" :key="source.id" :value="String(source.id)">{{ source.name }}</option></select></div>
    <div class="form-field"><label for="document-final">审核状态</label><select id="document-final" v-model="filters.final_status" class="select"><option value="">全部</option><option value="pending">待处理</option><option value="approved">已批准</option><option value="rejected">已拒绝</option></select></div>
    <div class="form-field"><label for="document-index">索引状态</label><select id="document-index" v-model="filters.index_status" class="select"><option value="">全部</option><option value="pending">待索引</option><option value="indexed">已索引</option><option value="stale">待更新</option><option value="failed">失败</option></select></div>
    <button class="button" type="submit"><Search :size="16" aria-hidden="true" />查询</button>
    <button class="button button-secondary" type="button" @click="reset">重置</button>
  </form>

  <AsyncState :loading="loading" :error="error" :empty="documents.length === 0" empty-text="没有匹配的文档" @retry="load">
    <div class="table-frame">
      <div class="table-scroll">
        <table class="data-table documents-table">
          <thead><tr><th>文档</th><th>来源</th><th>发布日期</th><th>地区 / 类型</th><th>审核</th><th>索引</th><th>版本</th><th>抓取时间</th></tr></thead>
          <tbody>
            <tr v-for="document in documents" :key="document.id">
              <td>
                <RouterLink class="cell-primary" :to="`/documents/${document.id}`"><FileText :size="14" aria-hidden="true" />{{ document.title }}</RouterLink>
                <span class="cell-secondary">{{ document.document_number ?? document.document_id }} · {{ formatNumber(document.word_count) }} 字</span>
              </td>
              <td><span class="cell-primary">{{ document.source?.name ?? '-' }}</span><span class="cell-secondary">{{ document.issuing_authority ?? document.source?.domain ?? '-' }}</span></td>
              <td>{{ formatDate(document.publish_date) }}</td>
              <td>{{ [document.region, document.city, document.document_type].filter(Boolean).join(' / ') || '-' }}</td>
              <td><StatusBadge :status="document.final_status" /></td>
              <td><StatusBadge :status="document.index_status" /></td>
              <td>v{{ document.version }}</td>
              <td>{{ formatDateTime(document.last_crawl_time) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </AsyncState>
</template>
