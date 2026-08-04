<script setup lang="ts">
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Filter,
  GitBranch,
  LoaderCircle,
  MessageSquareText,
  SearchCheck,
  Send,
  ThumbsDown,
  ThumbsUp,
  UserRound,
} from '@lucide/vue'
import { nextTick, reactive, ref } from 'vue'

import { api } from '@/api/resources'
import type { AnswerLineage, ChatResponse, FeedbackType, QueryTrace } from '@/api/types'
import JsonPanel from '@/components/JsonPanel.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatCost, formatDate, formatDuration } from '@/utils/format'

interface ConversationItem {
  id: string
  query: string
  response: ChatResponse | null
  error: string | null
}

const query = ref('')
const messages = ref<ConversationItem[]>([])
const sending = ref(false)
const showFilters = ref(false)
const trace = ref<QueryTrace | null>(null)
const lineage = ref<AnswerLineage | null>(null)
const inspectorTab = ref<'trace' | 'retrieval' | 'prompt' | 'lineage'>('trace')
const inspectorLoading = ref(false)
const feedbackStatus = reactive<Record<string, string>>({})
const conversationEnd = ref<HTMLElement | null>(null)
const filters = reactive({
  region: '',
  city: '',
  document_type: '',
  issuing_authority: '',
  publish_date_gte: '',
  publish_date_lte: '',
})

async function submit(): Promise<void> {
  const prompt = query.value.trim()
  if (!prompt || sending.value) return
  const item: ConversationItem = {
    id: crypto.randomUUID(),
    query: prompt,
    response: null,
    error: null,
  }
  messages.value.push(item)
  query.value = ''
  sending.value = true
  await nextTick()
  conversationEnd.value?.scrollIntoView({ behavior: 'smooth' })
  try {
    item.response = await api.chat(prompt, activeFilters())
    await openInspector(item.response.trace_id)
  } catch (caught) {
    item.error = caught instanceof Error ? caught.message : '问答请求失败'
  } finally {
    sending.value = false
    await nextTick()
    conversationEnd.value?.scrollIntoView({ behavior: 'smooth' })
  }
}

function activeFilters(): Record<string, unknown> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
}

async function openInspector(traceId: string): Promise<void> {
  inspectorLoading.value = true
  try {
    const [traceResult, lineageResult] = await Promise.all([api.trace(traceId), api.lineage(traceId)])
    trace.value = traceResult
    lineage.value = lineageResult
  } catch {
    trace.value = null
    lineage.value = null
  } finally {
    inspectorLoading.value = false
  }
}

async function sendFeedback(traceId: string, feedbackType: FeedbackType): Promise<void> {
  feedbackStatus[traceId] = '提交中'
  try {
    await api.createFeedback({
      trace_id: traceId,
      feedback_type: feedbackType,
      rating: feedbackType === 'helpful' ? 5 : 2,
    })
    feedbackStatus[traceId] = '已记录'
  } catch (caught) {
    feedbackStatus[traceId] = caught instanceof Error ? caught.message : '提交失败'
  }
}
</script>

<template>
  <PageHeader title="问答与证据" :meta="trace ? `Trace ${trace.trace_id}` : '新会话'">
    <template #actions>
      <button class="button button-secondary" type="button" @click="showFilters = !showFilters"><Filter :size="16" aria-hidden="true" />筛选条件<ChevronDown :size="14" :class="{ rotate: showFilters }" aria-hidden="true" /></button>
    </template>
  </PageHeader>

  <section v-if="showFilters" class="chat-filters panel">
    <div class="panel-body form-grid">
      <div class="form-field"><label for="chat-region">地区</label><input id="chat-region" v-model="filters.region" class="input" /></div>
      <div class="form-field"><label for="chat-city">城市</label><input id="chat-city" v-model="filters.city" class="input" /></div>
      <div class="form-field"><label for="chat-type">文档类型</label><input id="chat-type" v-model="filters.document_type" class="input" /></div>
      <div class="form-field"><label for="chat-authority">发布机构</label><input id="chat-authority" v-model="filters.issuing_authority" class="input" /></div>
      <div class="form-field"><label for="chat-date-from">发布日期起</label><input id="chat-date-from" v-model="filters.publish_date_gte" class="input" type="date" /></div>
      <div class="form-field"><label for="chat-date-to">发布日期止</label><input id="chat-date-to" v-model="filters.publish_date_lte" class="input" type="date" /></div>
    </div>
  </section>

  <div class="chat-layout">
    <section class="chat-main panel">
      <div class="chat-stream" aria-live="polite">
        <div v-if="messages.length === 0" class="chat-empty">
          <MessageSquareText :size="30" aria-hidden="true" />
          <strong>开始查询</strong>
        </div>

        <article v-for="item in messages" :key="item.id" class="conversation-turn">
          <div class="message message-user"><div class="message-avatar"><UserRound :size="17" aria-hidden="true" /></div><div class="message-body"><p>{{ item.query }}</p></div></div>

          <div v-if="item.error" class="message message-assistant"><div class="message-avatar"><AlertTriangle :size="17" aria-hidden="true" /></div><div class="message-body"><div class="notice notice-error">{{ item.error }}</div></div></div>

          <div v-else-if="item.response" class="message message-assistant">
            <div class="message-avatar"><Bot :size="17" aria-hidden="true" /></div>
            <div class="message-body">
              <div class="answer-meta"><StatusBadge :status="item.response.refusal ? 'rejected' : 'completed'" /><span>{{ item.response.query_type }}</span><button class="text-button" type="button" @click="openInspector(item.response!.trace_id)">查看 Trace</button></div>
              <div v-if="item.response.refusal_reasons.length" class="notice"><AlertTriangle :size="16" aria-hidden="true" /><span>{{ item.response.refusal_reasons.join('；') }}</span></div>
              <div v-if="item.response.conflicts.length" class="notice notice-error"><GitBranch :size="16" aria-hidden="true" /><span>{{ item.response.conflicts.join('；') }}</span></div>
              <MarkdownContent :content="item.response.answer" />

              <section v-if="item.response.citations.length" class="evidence-section">
                <h3><SearchCheck :size="16" aria-hidden="true" />引用证据</h3>
                <div class="evidence-grid">
                  <article v-for="(citation, index) in item.response.citations" :key="citation.chunk_id" class="evidence-card">
                    <header><span class="evidence-index">{{ index + 1 }}</span><div><strong>{{ citation.title }}</strong><span>{{ citation.source }} · {{ formatDate(citation.publication_date) }}</span></div><a class="icon-button" :href="citation.url" target="_blank" rel="noopener noreferrer" title="打开原文" aria-label="打开原文"><ExternalLink :size="15" aria-hidden="true" /></a></header>
                    <blockquote>{{ citation.quote }}</blockquote>
                    <footer><span class="mono">{{ citation.chunk_id }}</span><span v-if="citation.page">第 {{ citation.page }} 页</span></footer>
                  </article>
                </div>
              </section>

              <div class="answer-feedback"><span>本次回答</span><button class="icon-button" type="button" title="有帮助" aria-label="有帮助" @click="sendFeedback(item.response.trace_id, 'helpful')"><ThumbsUp :size="15" aria-hidden="true" /></button><button class="icon-button" type="button" title="没有帮助" aria-label="没有帮助" @click="sendFeedback(item.response.trace_id, 'not_helpful')"><ThumbsDown :size="15" aria-hidden="true" /></button><span v-if="feedbackStatus[item.response.trace_id]" class="muted">{{ feedbackStatus[item.response.trace_id] }}</span></div>
            </div>
          </div>
        </article>

        <div v-if="sending" class="message message-assistant"><div class="message-avatar"><Bot :size="17" aria-hidden="true" /></div><div class="message-body chat-thinking"><LoaderCircle class="spin" :size="18" aria-hidden="true" /><span>正在检索与校验证据</span></div></div>
        <div ref="conversationEnd" />
      </div>

      <form class="chat-composer" @submit.prevent="submit">
        <textarea v-model="query" class="textarea" rows="2" maxlength="4000" placeholder="输入查询" @keydown.ctrl.enter.prevent="submit" />
        <button class="button" type="submit" :disabled="sending || !query.trim()" title="发送" aria-label="发送"><Send :size="17" aria-hidden="true" /></button>
      </form>
    </section>

    <aside class="trace-inspector panel">
      <header class="panel-header"><h2>查询检查器</h2><span v-if="inspectorLoading" class="muted">加载中</span></header>
      <div v-if="!trace" class="state-panel"><SearchCheck :size="20" aria-hidden="true" />选择一条回答查看</div>
      <template v-else>
        <div class="tabs inspector-tabs" role="tablist">
          <button type="button" :class="{ active: inspectorTab === 'trace' }" @click="inspectorTab = 'trace'">概览</button>
          <button type="button" :class="{ active: inspectorTab === 'retrieval' }" @click="inspectorTab = 'retrieval'">检索</button>
          <button type="button" :class="{ active: inspectorTab === 'prompt' }" @click="inspectorTab = 'prompt'">Prompt</button>
          <button type="button" :class="{ active: inspectorTab === 'lineage' }" @click="inspectorTab = 'lineage'">血缘</button>
        </div>
        <div class="inspector-body">
          <dl v-if="inspectorTab === 'trace'" class="definition-grid definition-single">
            <div class="definition-item"><dt>Trace ID</dt><dd class="mono">{{ trace.trace_id }}</dd></div>
            <div class="definition-item"><dt>查询类型</dt><dd>{{ trace.query_type }}</dd></div>
            <div class="definition-item"><dt>模型</dt><dd>{{ trace.model_name ?? '-' }}</dd></div>
            <div class="definition-item"><dt>Prompt 版本</dt><dd>{{ trace.prompt_version ?? '-' }}</dd></div>
            <div class="definition-item"><dt>延迟</dt><dd>{{ formatDuration(trace.latency_ms) }}</dd></div>
            <div class="definition-item"><dt>成本</dt><dd>{{ formatCost(trace.cost) }}</dd></div>
            <div class="definition-item"><dt>拒答</dt><dd><StatusBadge :status="trace.refusal ? 'rejected' : 'completed'" /></dd></div>
            <div class="definition-item"><dt>Token</dt><dd><JsonPanel :value="trace.token_usage_json" /></dd></div>
          </dl>
          <div v-else-if="inspectorTab === 'retrieval'" class="stack-list"><JsonPanel label="解析过滤条件" :value="trace.parsed_filters_json" /><JsonPanel label="BM25" :value="trace.bm25_results_json" /><JsonPanel label="向量" :value="trace.vector_results_json" /><JsonPanel label="融合" :value="trace.fusion_results_json" /><JsonPanel label="重排" :value="trace.rerank_results_json" /><JsonPanel label="最终上下文" :value="trace.final_context_json" /></div>
          <JsonPanel v-else-if="inspectorTab === 'prompt'" label="Prompt 快照" :value="trace.prompt_snapshot_json" />
          <div v-else class="stack-list">
            <article v-for="(citation, index) in lineage?.citations ?? []" :key="index" class="lineage-card">
              <header><strong>引用 {{ index + 1 }}</strong><StatusBadge :status="citation.complete ? 'completed' : 'warning'" /></header>
              <div class="lineage-chain"><span><CheckCircle2 :size="14" />来源</span><span>抓取</span><span>版本</span><span>文档</span><span>分块</span></div>
              <JsonPanel :value="citation" />
            </article>
            <div v-if="!lineage?.citations.length" class="muted">没有引用血缘</div>
          </div>
        </div>
      </template>
    </aside>
  </div>
</template>
