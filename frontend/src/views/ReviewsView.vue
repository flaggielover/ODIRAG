<script setup lang="ts">
import { Check, Eye, RefreshCw, Sparkles, X } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { DocumentDetail, PendingReviewDocument, ReviewPipelineResult } from '@/api/types'
import AsyncState from '@/components/AsyncState.vue'
import JsonPanel from '@/components/JsonPanel.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAsyncTask } from '@/composables/useAsync'
import { formatDateTime } from '@/utils/format'

const pending = ref<PendingReviewDocument[]>([])
const selected = ref<PendingReviewDocument | null>(null)
const detail = ref<DocumentDetail | null>(null)
const pipeline = ref<ReviewPipelineResult | null>(null)
const reviewOpen = ref(false)
const actionError = ref<string | null>(null)
const actionId = ref<number | null>(null)
const { loading, error, run } = useAsyncTask()
const reviewForm = reactive({ decision: 'approve' as 'approve' | 'reject', summary: '', reasons: '' })

onMounted(load)

async function load(): Promise<void> {
  await run(async () => {
    pending.value = await api.pendingReviews()
  })
}

async function inspect(item: PendingReviewDocument): Promise<void> {
  selected.value = item
  pipeline.value = null
  actionError.value = null
  detail.value = await api.document(item.id).catch((caught: unknown) => {
    actionError.value = caught instanceof Error ? caught.message : '文档详情加载失败'
    return null
  })
}

async function runPipeline(item: PendingReviewDocument): Promise<void> {
  actionId.value = item.id
  actionError.value = null
  try {
    pipeline.value = await api.runReview(item.id)
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '自动审核失败'
  } finally {
    actionId.value = null
  }
}

function openDecision(item: PendingReviewDocument, decision: 'approve' | 'reject'): void {
  selected.value = item
  reviewForm.decision = decision
  reviewForm.summary = ''
  reviewForm.reasons = ''
  reviewOpen.value = true
}

async function submitDecision(): Promise<void> {
  if (!selected.value) return
  actionId.value = selected.value.id
  actionError.value = null
  try {
    await api.manualReview(
      selected.value.id,
      reviewForm.decision,
      reviewForm.summary,
      reviewForm.reasons.split('\n').map((item) => item.trim()).filter(Boolean),
    )
    reviewOpen.value = false
    selected.value = null
    detail.value = null
    await load()
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : '审核提交失败'
  } finally {
    actionId.value = null
  }
}
</script>

<template>
  <PageHeader title="人工审核" :meta="`${pending.length} 篇待审文档`">
    <template #actions><button class="button button-secondary" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" aria-hidden="true" />刷新</button></template>
  </PageHeader>

  <div v-if="actionError" class="notice notice-error" role="alert">{{ actionError }}</div>

  <AsyncState :loading="loading" :error="error" :empty="pending.length === 0" empty-text="当前没有待审文档" @retry="load">
    <div class="review-layout">
      <section class="table-frame">
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>文档</th><th>规则</th><th>LLM</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in pending" :key="item.id" :class="{ 'row-selected': selected?.id === item.id }">
                <td><button class="cell-link" type="button" @click="inspect(item)"><span class="cell-primary">{{ item.title }}</span><span class="cell-secondary">{{ item.document_id }}</span></button></td>
                <td><StatusBadge :status="item.rule_filter_status" /></td>
                <td><StatusBadge :status="item.llm_review_status" /></td>
                <td>{{ formatDateTime(item.created_at) }}</td>
                <td><div class="inline-actions"><button class="icon-button" type="button" title="查看正文" aria-label="查看正文" @click="inspect(item)"><Eye :size="16" aria-hidden="true" /></button><button class="icon-button" type="button" title="运行自动审核" aria-label="运行自动审核" :disabled="actionId === item.id" @click="runPipeline(item)"><Sparkles :size="16" aria-hidden="true" /></button><button class="icon-button success" type="button" title="批准" aria-label="批准" @click="openDecision(item, 'approve')"><Check :size="16" aria-hidden="true" /></button><button class="icon-button text-danger" type="button" title="拒绝" aria-label="拒绝" @click="openDecision(item, 'reject')"><X :size="16" aria-hidden="true" /></button></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside class="review-inspector">
        <div v-if="!selected" class="state-panel"><Eye :size="20" aria-hidden="true" />选择一篇文档查看</div>
        <template v-else>
          <section class="panel">
            <header class="panel-header"><h2>{{ selected.title }}</h2><StatusBadge :status="selected.final_status" /></header>
            <div v-if="detail" class="panel-body review-content"><MarkdownContent :content="detail.content" /></div>
            <div v-else class="state-panel">正在加载正文</div>
          </section>
          <section v-if="pipeline" class="panel">
            <header class="panel-header"><h2>自动审核结果</h2><StatusBadge :status="pipeline.final_status" /></header>
            <div class="panel-body"><JsonPanel :value="pipeline" /></div>
          </section>
        </template>
      </aside>
    </div>
  </AsyncState>

  <ModalDialog :open="reviewOpen" :title="reviewForm.decision === 'approve' ? '批准文档' : '拒绝文档'" @close="reviewOpen = false">
    <form id="review-form" class="form-grid" @submit.prevent="submitDecision">
      <div class="form-field form-field-full"><label for="review-summary">审核摘要</label><textarea id="review-summary" v-model="reviewForm.summary" class="textarea" /></div>
      <div class="form-field form-field-full"><label for="review-reasons">理由（每行一项）</label><textarea id="review-reasons" v-model="reviewForm.reasons" class="textarea" /></div>
      <div v-if="actionError" class="notice notice-error form-field-full" role="alert">{{ actionError }}</div>
    </form>
    <template #footer><button class="button button-secondary" type="button" @click="reviewOpen = false">取消</button><button class="button" :class="{ 'button-danger': reviewForm.decision === 'reject' }" type="submit" form="review-form" :disabled="actionId !== null">提交</button></template>
  </ModalDialog>
</template>
