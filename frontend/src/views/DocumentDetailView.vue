<script setup lang="ts">
import { ArrowLeft, ExternalLink, FileArchive, RefreshCw, RotateCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '@/api/resources'
import type { Chunk, DocumentDetail, IndexResult } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatCost, formatDate, formatDateTime, formatNumber } from '@/utils/format'

type Tab = 'overview' | 'content' | 'chunks' | 'versions' | 'attachments' | 'reviews'

const route = useRoute()
const document = ref<DocumentDetail | null>(null)
const chunks = ref<Chunk[]>([])
const activeTab = ref<Tab>('overview')
const reindexing = ref(false)
const actionError = ref<string | null>(null)
const indexResult = ref<IndexResult | null>(null)
const { loading, error, run } = useAsyncTask()
const documentId = computed(() => Number(route.params.id))

const tabs = computed(() => [
  { id: 'overview' as const, label: '概览' },
  { id: 'content' as const, label: '正文' },
  { id: 'chunks' as const, label: `分块 ${chunks.value.length}` },
  { id: 'versions' as const, label: `版本 ${document.value?.versions.length ?? 0}` },
  { id: 'attachments' as const, label: `附件 ${document.value?.attachments.length ?? 0}` },
  { id: 'reviews' as const, label: `审核 ${document.value?.reviews.length ?? 0}` },
])

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    const [detail, chunkResult] = await Promise.all([
      api.document(documentId.value),
      api.documentChunks(documentId.value),
    ])
    document.value = detail
    chunks.value = chunkResult
  })
}

async function reindex(): Promise<void> {
  reindexing.value = true
  actionError.value = null
  indexResult.value = null
  try {
    indexResult.value = await api.reindexDocument(documentId.value)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '重建索引失败'
  } finally {
    reindexing.value = false
  }
}
</script>

<template>
  <AsyncState :loading="loading" :error="error" :empty="!document" empty-text="文档不存在" @retry="load">
    <template v-if="document">
      <RouterLink class="back-link" to="/documents"><ArrowLeft :size="15" aria-hidden="true" />返回文档列表</RouterLink>
      <PageHeader :title="document.title" :meta="document.document_number ?? document.document_id">
        <template #actions>
          <a class="button button-secondary" :href="document.source_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" aria-hidden="true" />原文</a>
          <button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" aria-hidden="true" />刷新</button>
          <button class="button" type="button" :disabled="reindexing || document.final_status !== 'approved'" @click="reindex"><RotateCw :size="16" :class="{ spin: reindexing }" aria-hidden="true" />{{ reindexing ? '索引中' : '重建索引' }}</button>
        </template>
      </PageHeader>

      <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>
      <div v-if="indexResult" class="notice notice-success" role="status">索引完成：{{ indexResult.chunk_count }} 个分块，{{ indexResult.embedded_count }} 个新嵌入，估算成本 {{ formatCost(indexResult.estimated_cost) }}</div>

      <div class="document-status-strip">
        <StatusBadge :status="document.final_status" />
        <StatusBadge :status="document.index_status" />
        <span>{{ document.source?.name ?? '未知来源' }}</span>
        <span>{{ formatDate(document.publish_date) }}</span>
        <span>v{{ document.version }}</span>
      </div>

      <div class="tabs" role="tablist" aria-label="文档详情视图">
        <button v-for="tab in tabs" :key="tab.id" type="button" role="tab" :aria-selected="activeTab === tab.id" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.label }}</button>
      </div>

      <section v-if="activeTab === 'overview'" class="content-grid content-grid-wide">
        <div class="panel">
          <header class="panel-header"><h2>文档信息</h2></header>
          <dl class="definition-grid">
            <div class="definition-item"><dt>发布机构</dt><dd>{{ document.issuing_authority ?? '-' }}</dd></div>
            <div class="definition-item"><dt>文号</dt><dd>{{ document.document_number ?? '-' }}</dd></div>
            <div class="definition-item"><dt>地区</dt><dd>{{ [document.region, document.city].filter(Boolean).join(' / ') || '-' }}</dd></div>
            <div class="definition-item"><dt>文档类型</dt><dd>{{ document.document_type ?? '-' }}</dd></div>
            <div class="definition-item"><dt>作者</dt><dd>{{ document.author ?? '-' }}</dd></div>
            <div class="definition-item"><dt>语言</dt><dd>{{ document.language ?? '-' }}</dd></div>
            <div class="definition-item"><dt>字数</dt><dd>{{ formatNumber(document.word_count) }}</dd></div>
            <div class="definition-item"><dt>质量分</dt><dd>{{ document.quality_score ?? '-' }}</dd></div>
            <div class="definition-item"><dt>首次抓取</dt><dd>{{ formatDateTime(document.first_crawl_time) }}</dd></div>
            <div class="definition-item"><dt>最近抓取</dt><dd>{{ formatDateTime(document.last_crawl_time) }}</dd></div>
          </dl>
        </div>
        <div>
          <div class="panel">
            <header class="panel-header"><h2>处理状态</h2></header>
            <div class="panel-body stack-list">
              <div class="list-row"><span>规则过滤</span><StatusBadge :status="document.rule_filter_status" /></div>
              <div class="list-row"><span>LLM 审核</span><StatusBadge :status="document.llm_review_status" /></div>
              <div class="list-row"><span>人工审核</span><StatusBadge :status="document.manual_review_status" /></div>
              <div class="list-row"><span>最终状态</span><StatusBadge :status="document.final_status" /></div>
              <div class="list-row"><span>索引状态</span><StatusBadge :status="document.index_status" /></div>
            </div>
          </div>
          <div class="panel">
            <header class="panel-header"><h2>数据身份</h2></header>
            <div class="panel-body"><JsonPanel :value="{ document_id: document.document_id, content_hash: document.content_hash, simhash: document.simhash, parent_document_id: document.parent_document_id, duplicate_of_document_id: document.duplicate_of_document_id }" /></div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'content'" class="panel"><header class="panel-header"><h2>规范化正文</h2></header><div class="panel-body document-content"><MarkdownContent :content="document.content" /></div></section>

      <section v-else-if="activeTab === 'chunks'" class="chunk-grid">
        <article v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
          <header><div><strong>#{{ chunk.chunk_index }} {{ chunk.section_title ?? '未命名分块' }}</strong><span>{{ chunk.section_path ?? chunk.chunk_id }}</span></div><StatusBadge :status="chunk.vector_status" /></header>
          <p>{{ chunk.content }}</p>
          <footer><span>{{ formatNumber(chunk.char_count) }} 字符</span><span>{{ formatNumber(chunk.token_count) }} tokens</span><span v-if="chunk.page_number">第 {{ chunk.page_number }} 页</span></footer>
        </article>
        <div v-if="chunks.length === 0" class="state-panel">暂无分块</div>
      </section>

      <section v-else-if="activeTab === 'versions'" class="stack-list">
        <article v-for="version in document.versions" :key="version.id" class="panel">
          <header class="panel-header"><h2>版本 {{ version.version }}</h2><span class="muted">{{ formatDateTime(version.created_at) }}</span></header>
          <div class="panel-body"><p class="mono truncate">{{ version.content_hash }}</p><div class="inline-actions"><span v-for="field in version.changed_fields_json" :key="field" class="status-badge">{{ field }}</span></div></div>
        </article>
        <div v-if="document.versions.length === 0" class="state-panel">暂无版本快照</div>
      </section>

      <section v-else-if="activeTab === 'attachments'" class="stack-list">
        <article v-for="attachment in document.attachments" :key="attachment.id" class="panel">
          <header class="panel-header"><h2><FileArchive :size="16" aria-hidden="true" />{{ attachment.attachment_name }}</h2><div class="inline-actions"><StatusBadge :status="attachment.download_status" /><StatusBadge :status="attachment.parse_status" /></div></header>
          <dl class="definition-grid"><div class="definition-item"><dt>类型</dt><dd>{{ attachment.mime_type ?? attachment.file_extension ?? '-' }}</dd></div><div class="definition-item"><dt>大小</dt><dd>{{ attachment.file_size ? `${formatNumber(attachment.file_size / 1024, 1)} KB` : '-' }}</dd></div><div class="definition-item"><dt>页数</dt><dd>{{ attachment.page_count ?? '-' }}</dd></div><div class="definition-item"><dt>OCR</dt><dd>{{ attachment.requires_ocr ? '需要' : '不需要' }}</dd></div></dl>
        </article>
        <div v-if="document.attachments.length === 0" class="state-panel">暂无附件</div>
      </section>

      <section v-else class="stack-list">
        <article v-for="review in document.reviews" :key="review.id" class="panel">
          <header class="panel-header"><h2>{{ review.review_type }} · {{ review.reviewer }}</h2><StatusBadge :status="review.decision" /></header>
          <div class="panel-body"><p>{{ review.summary ?? '无摘要' }}</p><div class="inline-actions"><span v-for="reason in review.reasons_json" :key="reason" class="status-badge">{{ reason }}</span></div><p class="cell-secondary">{{ review.model_name ?? '人工' }} · {{ review.prompt_version ?? '-' }} · {{ formatDateTime(review.created_at) }}</p></div>
        </article>
        <div v-if="document.reviews.length === 0" class="state-panel">暂无审核记录</div>
      </section>
    </template>
  </AsyncState>
</template>
