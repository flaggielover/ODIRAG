import { expect, type Page, type Route } from '@playwright/test'

import type {
  Alert,
  SourceCandidate,
  SourceCandidateColumn,
  SourceDiscoveryEvent,
  SourceDiscoveryRun,
} from '../src/api/types'

const now = '2026-08-04T00:00:00Z'

export const sourceFixture = {
  id: 1,
  source_key: 'demo-ministry',
  name: '示例官方来源',
  domain: 'example.gov.cn',
  region: '全国',
  city: null,
  organization_level: 'national',
  organization_type: 'government',
  official_status: 'official',
  homepage_url: 'https://example.gov.cn',
  enabled: true,
  priority: 10,
  crawl_frequency: 'daily',
  crawl_provider: 'coze',
  coze_contract_mode: 'batch_crawl',
  last_coze_status: 'completed',
  last_coze_article_count: 2,
  last_coze_error: null,
  last_crawl_time: now,
  created_at: now,
  updated_at: now,
  columns: [
    {
      id: 1,
      source_id: 1,
      column_key: 'policies',
      column_name: '政策文件',
      column_url: 'https://example.gov.cn/policies',
      parser_type: 'html',
      enabled: true,
      max_pages: 100,
      request_interval_seconds: 1,
      selectors_json: {},
      pagination_json: {},
      created_at: now,
      updated_at: now,
    },
  ],
}

export const documentFixture = {
  id: 1,
  document_id: 'doc-demo-001',
  title: '企业研发投入支持措施',
  source_url: 'https://example.gov.cn/policies/research-support',
  source_id: 1,
  source: {
    id: 1,
    source_key: sourceFixture.source_key,
    name: sourceFixture.name,
    domain: sourceFixture.domain,
    official_status: sourceFixture.official_status,
  },
  publish_date: '2026-07-01',
  issuing_authority: '示例部门',
  document_number: '示例〔2026〕1号',
  region: '全国',
  city: null,
  document_type: '政策',
  word_count: 320,
  language: 'zh-CN',
  quality_score: 0.96,
  rule_filter_status: 'passed',
  llm_review_status: 'passed',
  manual_review_status: 'approved',
  final_status: 'approved',
  index_status: 'indexed',
  version: 1,
  last_crawl_time: now,
  created_at: now,
  updated_at: now,
}

const tokens = {
  access_token: 'e2e-access-token',
  refresh_token: 'e2e-refresh-token',
  token_type: 'bearer',
  expires_in: 1800,
}

const user = {
  id: 1,
  username: 'admin',
  is_active: true,
  is_superuser: true,
  created_at: now,
  updated_at: now,
}

const health = {
  status: 'healthy',
  service: 'odirag-api',
  environment: 'test',
  checked_at: now,
  dependencies: {
    database: { status: 'healthy', latency_ms: 3, detail: 'fixture' },
    redis: { status: 'healthy', latency_ms: 2, detail: 'fixture' },
    qdrant: { status: 'healthy', latency_ms: 4, detail: 'fixture' },
  },
}

const trace = {
  trace_id: 'trace-e2e-001',
  user_query: '研发投入支持措施有哪些？',
  query_type: 'rag',
  parsed_filters_json: {},
  bm25_results_json: [{ chunk_id: 'chunk-demo-001', score: 0.93 }],
  vector_results_json: [{ chunk_id: 'chunk-demo-001', score: 0.91 }],
  fusion_results_json: [{ chunk_id: 'chunk-demo-001', score: 0.95 }],
  rerank_results_json: [{ chunk_id: 'chunk-demo-001', score: 0.97 }],
  final_context_json: [{ chunk_id: 'chunk-demo-001', content: '支持企业研发投入。' }],
  prompt_version: 'rag-v1',
  prompt_snapshot_json: { system: '仅根据引用回答。' },
  evidence_decision_json: {
    sufficient: true,
    confidence: 0.92,
    reason: 'evidence_covers_all_query_aspects',
    supported_chunk_ids: ['chunk-demo-001'],
    unsupported_aspects: [],
    status: 'passed',
  },
  model_name: 'deterministic-test-model',
  answer: '企业可按规定申请研发投入支持措施，具体条件以官方文件为准。',
  citations_json: [{ chunk_id: 'chunk-demo-001' }],
  refusal: false,
  latency_ms: 42,
  token_usage_json: { input_tokens: 20, output_tokens: 24 },
  cost: 0,
  created_at: now,
}

const chatResponse = {
  trace_id: trace.trace_id,
  query_type: 'rag',
  answer: trace.answer,
  refusal: false,
  refusal_reasons: [],
  conflicts: [],
  outdated: [],
  citations: [
    {
      document_id: documentFixture.document_id,
      chunk_id: 'chunk-demo-001',
      title: documentFixture.title,
      source: sourceFixture.name,
      publication_date: documentFixture.publish_date,
      url: documentFixture.source_url,
      page: 1,
      quote: '支持企业研发投入，鼓励创新主体持续增加研发投入。',
    },
  ],
  filters: {},
  structured_count: null,
  evidence_sufficiency: {
    sufficient: true,
    confidence: 0.92,
    reason: 'evidence_covers_all_query_aspects',
    supported_chunk_ids: ['chunk-demo-001'],
    unsupported_aspects: [],
  },
}

const lineage = {
  trace_id: trace.trace_id,
  answer: chatResponse.answer,
  prompt_version: trace.prompt_version,
  prompt_snapshot: trace.prompt_snapshot_json,
  citations: [
    {
      citation: chatResponse.citations[0],
      chunk: { id: 1, chunk_id: 'chunk-demo-001' },
      document: { id: 1, document_id: documentFixture.document_id },
      document_version: { id: 1, version: 1 },
      crawl_task: { id: 1, status: 'succeeded' },
      source: { id: sourceFixture.id, source_key: sourceFixture.source_key },
      lineage_ids: ['source:1', 'task:1', 'document:1', 'version:1', 'chunk:1'],
      complete: true,
      missing_steps: [],
    },
  ],
}

const evaluationRun = {
  id: 1,
  run_name: 'fixture-evaluation',
  experiment_id: null,
  retrieval_version: 'hybrid-v1',
  prompt_version: 'rag-v1',
  embedding_model: 'deterministic-test-embedding',
  rerank_model: 'deterministic-test-reranker',
  top_k: 5,
  started_at: now,
  finished_at: now,
  question_count: 1,
  recall_at_1: 1,
  recall_at_5: 1,
  recall_at_10: 1,
  mrr: 1,
  ndcg: 1,
  citation_accuracy: 1,
  refusal_accuracy: 1,
  hallucination_rate: 0,
  average_latency: 42,
  p95_latency: 42,
  average_cost: 0,
  result_path: null,
  created_at: now,
}

const metrics = {
  uptime_seconds: 120,
  requests_total: 18,
  requests_by_status_class: { '2xx': 18 },
  routes: [
    {
      method: 'GET',
      path: '/api/system/health',
      status_code: 200,
      count: 4,
      sample_count: 4,
      average_latency_ms: 3,
      p50_latency_ms: 3,
      p95_latency_ms: 5,
      p99_latency_ms: 6,
    },
  ],
  database_latency: {
    sample_count: 12,
    average_latency_ms: 3,
    p50_latency_ms: 2,
    p95_latency_ms: 8,
    p99_latency_ms: 12,
  },
  crawler: {
    window_hours: 24,
    task_count: 1,
    status_counts: { succeeded: 1 },
    task_failure_rate: 0,
    discovered_count: 1,
    fetched_count: 1,
    success_count: 1,
    failed_count: 0,
    item_failure_rate: 0,
  },
  knowledge: {
    document_count: 1,
    final_status_counts: { approved: 1 },
    index_status_counts: { indexed: 1 },
    approved_count: 1,
    indexed_count: 1,
    index_failure_count: 0,
    stale_count: 0,
    chunk_count: 1,
  },
  rag: {
    window_hours: 24,
    query_count: 1,
    refusal_count: 0,
    refusal_rate: 0,
    average_latency_ms: 42,
    p50_latency_ms: 42,
    p95_latency_ms: 42,
    total_tokens: 44,
    measured_token_trace_count: 1,
    total_cost: 0,
    average_cost: 0,
    trace_completeness_rate: 1,
    evaluation_regression_count: 0,
    evidence_assessed_count: 1,
    evidence_sufficient_count: 1,
    evidence_insufficient_count: 0,
    evidence_sufficiency_rate: 1,
    average_evidence_gate_latency_ms: 1.2,
    grounding_failure_count: 0,
    citation_answer_count: 1,
    citation_rate: 1,
    refusal_citation_violation_count: 0,
  },
  dependencies: health.dependencies,
}

const alert: Alert = {
  id: 1,
  alert_key: 'fixture-alert',
  alert_type: 'latency',
  severity: 'warning',
  status: 'open',
  component: 'rag',
  message: '示例延迟告警',
  observed_value: 42,
  threshold_value: 500,
  details_json: {},
  occurrence_count: 1,
  first_seen_at: now,
  last_seen_at: now,
  acknowledged_at: null,
  resolved_at: null,
  created_at: now,
  updated_at: now,
}

const discoveryRun: SourceDiscoveryRun = {
  id: 1,
  topic: '企业研发投入',
  region: '全国',
  organization_level: 'national',
  query_text: '企业研发投入 官方 政府 网站',
  required_source_count: 2,
  required_document_count: 5,
  existing_source_count: 0,
  existing_document_count: 0,
  gap_detected: true,
  gap_evidence_json: { source_gap: 2, document_gap: 5 },
  status: 'awaiting_approval',
  discovery_provider: 'fixture-search',
  max_candidates: 10,
  candidate_count: 2,
  approved_count: 0,
  activated_count: 0,
  attempt_count: 1,
  started_at: now,
  finished_at: now,
  error_message: null,
  created_by: 'admin',
  created_at: now,
  updated_at: now,
}

const discoveryColumn: SourceCandidateColumn = {
  id: 1,
  candidate_id: 1,
  column_key: 'policies',
  column_name: '政策文件',
  column_url: 'https://innovation.example.gov.cn/policies',
  parser_type: 'html',
  selectors_json: {},
  pagination_json: {},
  discovery_evidence_json: { anchor_text: '政策文件' },
  status: 'trial_crawled',
  trial_discovered_count: 3,
  trial_fetched_count: 3,
  trial_success_count: 3,
  trial_failed_count: 0,
  trial_average_chars: 1200,
  quality_score: 0.91,
  error_message: null,
  created_at: now,
  updated_at: now,
}

const discoveryCandidate: SourceCandidate = {
  id: 1,
  run_id: 1,
  canonical_homepage_url: 'https://innovation.example.gov.cn',
  domain: 'innovation.example.gov.cn',
  name: '示例创新政策来源',
  snippet: '官方创新政策与研发支持信息。',
  search_rank: 1,
  discovery_provider: 'fixture-search',
  discovery_query: discoveryRun.query_text,
  official_status: 'official',
  official_score: 0.98,
  official_evidence_json: { trusted_suffix: '.gov.cn' },
  validation_status_code: 200,
  validation_final_url: 'https://innovation.example.gov.cn',
  status: 'pending_approval',
  quality_score: 0.93,
  quality_breakdown_json: {
    official_component: 0.98,
    trial_success_ratio: 1,
    threshold: 0.7,
  },
  trial_column_count: 1,
  trial_document_count: 3,
  trial_success_count: 3,
  trial_failed_count: 0,
  trial_average_chars: 1200,
  rejection_reason: null,
  approved_by: null,
  approved_at: null,
  source_id: null,
  created_at: now,
  updated_at: now,
  columns: [discoveryColumn],
}

const rejectableDiscoveryCandidate: SourceCandidate = {
  ...discoveryCandidate,
  id: 2,
  canonical_homepage_url: 'https://notice.example.gov.cn',
  domain: 'notice.example.gov.cn',
  name: '示例待复核来源',
  search_rank: 2,
  quality_score: 0.78,
  columns: [
    {
      ...discoveryColumn,
      id: 2,
      candidate_id: 2,
      column_url: 'https://notice.example.gov.cn/notices',
      quality_score: 0.76,
    },
  ],
}

const discoveryEvents: SourceDiscoveryEvent[] = [
  {
    id: 1,
    run_id: 1,
    candidate_id: null,
    stage: 'content_gap_detection',
    from_status: null,
    to_status: 'pending',
    message: 'Content gap detected; discovery queued.',
    details_json: discoveryRun.gap_evidence_json,
    created_at: now,
  },
  {
    id: 2,
    run_id: 1,
    candidate_id: 1,
    stage: 'quality_scoring',
    from_status: 'columns_discovered',
    to_status: 'pending_approval',
    message: 'Candidate quality was calculated from trial-crawl evidence.',
    details_json: { quality_score: 0.93 },
    created_at: now,
  },
]

function jsonBody(route: Route): Record<string, unknown> {
  try {
    return (route.request().postDataJSON() as Record<string, unknown>) ?? {}
  } catch {
    return {}
  }
}

async function fulfill(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

export async function installApiFixtures(page: Page): Promise<void> {
  let sources = [structuredClone(sourceFixture)]
  let feedbackId = 1
  let latestAlert = structuredClone(alert)
  let discoveryRuns: SourceDiscoveryRun[] = [structuredClone(discoveryRun)]
  const discoveryCandidates: SourceCandidate[] = [
    structuredClone(discoveryCandidate),
    structuredClone(rejectableDiscoveryCandidate),
  ]
  let latestDiscoveryEvents: SourceDiscoveryEvent[] = structuredClone(discoveryEvents)

  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const method = request.method()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api/, '')

    if (path === '/auth/login' && method === 'POST') return fulfill(route, tokens)
    if (path === '/auth/me' && method === 'GET') return fulfill(route, user)
    if (path === '/auth/logout' && method === 'POST') return route.fulfill({ status: 204 })
    if (path === '/auth/refresh' && method === 'POST') return fulfill(route, tokens)
    if (path === '/system/health' && method === 'GET') return fulfill(route, health)
    if (path === '/system/coze/status' && method === 'GET') return fulfill(route, { enabled: true, token_configured: true, legacy_workflow_configured: true, batch_workflow_configured: true, default_contract: 'batch_crawl' })
    if (path === '/system/metrics' && method === 'GET') return fulfill(route, metrics)
    if (path === '/system/alerts' && method === 'GET') return fulfill(route, [latestAlert])
    if (path === '/system/alerts/1/acknowledge' && method === 'POST') {
      latestAlert = { ...latestAlert, status: 'acknowledged', acknowledged_at: now }
      return fulfill(route, latestAlert)
    }
    if (path === '/system/alerts/1/resolve' && method === 'POST') {
      latestAlert = { ...latestAlert, status: 'resolved', resolved_at: now }
      return fulfill(route, latestAlert)
    }

    if (path === '/sources' && method === 'GET') return fulfill(route, sources)
    if (path === '/sources' && method === 'POST') {
      const payload = jsonBody(route)
      const created = {
        ...structuredClone(sourceFixture),
        id: sources.length + 1,
        source_key: String(payload.source_key ?? 'new-source'),
        name: String(payload.name ?? '新来源'),
      }
      sources = [...sources, created]
      return fulfill(route, created, 201)
    }
    if (path.match(/^\/sources\/\d+\/connectivity-tests\/coze$/) && method === 'POST') {
      return fulfill(route, { available: true, reachable: true, contract: url.searchParams.get('contract') ?? 'batch_crawl', status_code: 200, latency_ms: 25, error_code: null, final_url: sourceFixture.homepage_url, error_type: null, provider: 'coze', status: 'healthy', message: null, checked_at: now })
    }
    if (path.match(/^\/sources\/\d+\/connectivity-tests\/local$/) && method === 'POST') {
      return fulfill(route, {
        provider: 'local',
        reachable: true,
        status_code: 200,
        latency_ms: 11,
        final_url: sourceFixture.homepage_url,
        error_type: null,
      })
    }
    if (path.match(/^\/sources\/\d+\/test$/) && method === 'POST') {
      return fulfill(route, { provider: 'local', reachable: true, status_code: 200, latency_ms: 11, final_url: sourceFixture.homepage_url, error_type: null })
    }
    if (path.match(/^\/sources\/\d+$/) && method === 'GET') return fulfill(route, sources[0])

    if (path === '/source-discovery/metrics' && method === 'GET') {
      const pending = discoveryCandidates.filter((item) => item.status === 'pending_approval').length
      const activated = discoveryCandidates.filter((item) => item.status === 'activated').length
      const scores = discoveryCandidates.map((item) => item.quality_score).filter((score) => score !== null)
      return fulfill(route, {
        run_status_counts: Object.fromEntries(discoveryRuns.map((item) => [item.status, 1])),
        candidate_status_counts: Object.fromEntries(
          discoveryCandidates.map((item) => [item.status, discoveryCandidates.filter((other) => other.status === item.status).length]),
        ),
        column_status_counts: { trial_crawled: 2 },
        pending_approval_count: pending,
        activated_source_count: activated,
        average_quality_score: scores.reduce((sum, score) => sum + score, 0) / Math.max(scores.length, 1),
        last_run_at: now,
      })
    }
    if (path === '/source-discovery/runs' && method === 'GET') return fulfill(route, discoveryRuns)
    if (path === '/source-discovery/runs' && method === 'POST') {
      const payload = jsonBody(route)
      const created: SourceDiscoveryRun = {
        ...structuredClone(discoveryRun),
        id: 2,
        topic: String(payload.topic ?? '新主题'),
        region: typeof payload.region === 'string' ? payload.region : null,
        organization_level:
          typeof payload.organization_level === 'string' ? payload.organization_level : null,
        query_text: String(payload.query_text ?? payload.topic ?? ''),
        required_source_count: Number(payload.required_source_count ?? 1),
        required_document_count: Number(payload.required_document_count ?? 3),
        existing_source_count: 0,
        existing_document_count: 0,
        status: 'pending',
        discovery_provider: 'fixture-search',
        max_candidates: Number(payload.max_candidates ?? 10),
        candidate_count: 0,
        approved_count: 0,
        activated_count: 0,
        attempt_count: 0,
        started_at: null,
        finished_at: null,
      }
      discoveryRuns = [created, ...discoveryRuns]
      return fulfill(route, created, 201)
    }
    const runMatch = path.match(/^\/source-discovery\/runs\/(\d+)$/)
    if (runMatch && method === 'GET') {
      return fulfill(route, discoveryRuns.find((item) => item.id === Number(runMatch[1])) ?? discoveryRuns[0])
    }
    const runCandidateMatch = path.match(/^\/source-discovery\/runs\/(\d+)\/candidates$/)
    if (runCandidateMatch && method === 'GET') {
      return fulfill(route, discoveryCandidates.filter((item) => item.run_id === Number(runCandidateMatch[1])))
    }
    const runEventMatch = path.match(/^\/source-discovery\/runs\/(\d+)\/events$/)
    if (runEventMatch && method === 'GET') {
      return fulfill(route, latestDiscoveryEvents.filter((item) => item.run_id === Number(runEventMatch[1])))
    }
    const candidateMatch = path.match(/^\/source-discovery\/candidates\/(\d+)$/)
    if (candidateMatch && method === 'GET') {
      return fulfill(route, discoveryCandidates.find((item) => item.id === Number(candidateMatch[1])))
    }
    const candidateEventMatch = path.match(/^\/source-discovery\/candidates\/(\d+)\/events$/)
    if (candidateEventMatch && method === 'GET') {
      return fulfill(route, latestDiscoveryEvents.filter((item) => item.candidate_id === Number(candidateEventMatch[1])))
    }
    const candidateActionMatch = path.match(/^\/source-discovery\/candidates\/(\d+)\/(approve|reject|activate)$/)
    if (candidateActionMatch && method === 'POST') {
      const candidateId = Number(candidateActionMatch[1])
      const action = candidateActionMatch[2]
      const candidate = discoveryCandidates.find((item) => item.id === candidateId)
      if (!candidate) return fulfill(route, { error: { message: 'Candidate not found' } }, 404)
      const fromStatus = candidate.status
      if (action === 'approve') {
        candidate.status = 'approved'
        candidate.approved_by = 'admin'
        candidate.approved_at = now
      } else if (action === 'activate') {
        candidate.status = 'activated'
        candidate.source_id = 2
      } else {
        candidate.status = 'rejected'
        candidate.rejection_reason = String(jsonBody(route).reason ?? 'Rejected in fixture')
      }
      const run = discoveryRuns.find((item) => item.id === candidate.run_id)
      if (run) {
        run.approved_count = discoveryCandidates.filter((item) => item.run_id === run.id && ['approved', 'activated'].includes(item.status)).length
        run.activated_count = discoveryCandidates.filter((item) => item.run_id === run.id && item.status === 'activated').length
        if (run.activated_count > 0) run.status = 'activated'
      }
      latestDiscoveryEvents = [
        ...latestDiscoveryEvents,
        {
          id: latestDiscoveryEvents.length + 1,
          run_id: candidate.run_id,
          candidate_id: candidate.id,
          stage: action === 'activate' ? 'source_activation' : 'manual_approval',
          from_status: fromStatus,
          to_status: candidate.status,
          message: `Candidate ${action} completed.`,
          details_json: {},
          created_at: now,
        },
      ]
      return fulfill(route, candidate)
    }

    if (path === '/documents' && method === 'GET') return fulfill(route, [documentFixture])
    if (path === '/documents/1' && method === 'GET') {
      return fulfill(route, {
        ...documentFixture,
        source_column_id: 1,
        subtitle: null,
        canonical_url: documentFixture.source_url,
        author: null,
        content: '企业可按规定申请研发投入支持措施。',
        raw_content: null,
        content_hash: 'hash-demo-001',
        simhash: null,
        parent_document_id: null,
        duplicate_of_document_id: null,
        first_crawl_time: now,
        versions: [],
        attachments: [],
        reviews: [],
      })
    }
    if (path === '/documents/1/chunks' && method === 'GET') {
      return fulfill(route, [{ id: 1, chunk_id: 'chunk-demo-001', document_id: 1, attachment_id: null, chunk_index: 0, section_path: null, section_title: null, page_number: 1, content: '支持企业研发投入。', content_hash: 'chunk-hash', char_count: 10, token_count: 5, embedding_model: 'deterministic-test-embedding', embedding_version: 'v1', vector_status: 'indexed', created_at: now, updated_at: now }])
    }
    if (path === '/documents/1/reindex' && method === 'POST') return fulfill(route, { document_id: 1, document_version: 1, chunk_count: 1, cache_hits: 1, embedded_count: 0, embedding_model: 'deterministic-test-embedding', embedding_version: 'v1', estimated_cost: 0, vector_point_ids: ['chunk-demo-001'], bm25_document_count: 1 })

    if (path === '/crawl-tasks' && method === 'GET') return fulfill(route, [{ id: 1, source_column_id: 1, task_type: 'incremental', trigger_type: 'schedule', status: 'completed', crawl_provider: 'coze', provider_contract: 'batch_crawl', coze_execution_id: 'exec-fixture-1', provider_task_id: 'exec-fixture-1', current_stage: 'saving_documents', stage_counts: { discovered: 3, accepted: 2 }, accepted_count: 2, rejected_count: 0, pending_review_count: 0, started_at: now, finished_at: now, discovered_count: 3, fetched_count: 3, success_count: 2, url_duplicate_count: 0, content_duplicate_count: 0, semantic_duplicate_count: 0, failed_count: 1, retry_count: 0, error_message: null, provider_error_code: null, provider_error_message: null, created_at: now }])
    if (path.match(/^\/crawl-tasks\/\d+\/acceptance-summary$/) && method === 'GET') return fulfill(route, { crawl_task_id: 1, database_document_count: 2, chunk_count: 4, qdrant_collection_exists: true, qdrant_point_count: 4 })
    if (path.match(/^\/crawl-tasks\/\d+\/invocations$/) && method === 'GET') return fulfill(route, [{ id: 1, crawl_task_id: 1, contract: 'batch_crawl', endpoint_url: 'https://fixture.invalid/run', status: 'completed', request_json: {}, raw_response_json: {}, normalized_response_json: {}, http_status_code: 200, attempt_count: 1, retry_count: 0, duration_ms: 120, token_usage_json: {}, error_code: null, error_message: null, started_at: now, finished_at: now, created_at: now }])
    if (path.match(/^\/crawl-tasks\/\d+\/failed-urls$/) && method === 'GET') return fulfill(route, [])
    if (path.match(/^\/crawl-tasks\/\d+\/results$/) && method === 'GET') return fulfill(route, [{ id: 1, document_id: 'doc-coze-1', title: 'Coze 批量抓取结果', source_url: 'https://example.gov.cn/policies/1', decision: 'accepted', quality_score: 92, final_status: 'pending_review', review_reason: 'Fixture-verified' }])
    const crawlTaskMatch = path.match(/^\/crawl-tasks\/(\d+)$/)
    if (crawlTaskMatch && method === 'GET') return fulfill(route, { id: Number(crawlTaskMatch[1]), source_column_id: 1, task_type: 'incremental', trigger_type: 'schedule', status: 'completed', crawl_provider: 'coze', provider_contract: 'batch_crawl', coze_execution_id: 'exec-fixture-1', provider_task_id: 'exec-fixture-1', current_stage: 'saving_documents', stage_counts: { discovered: 3, accepted: 2 }, accepted_count: 2, rejected_count: 0, pending_review_count: 0, started_at: now, finished_at: now, discovered_count: 3, fetched_count: 3, success_count: 2, url_duplicate_count: 0, content_duplicate_count: 0, semantic_duplicate_count: 0, failed_count: 1, retry_count: 0, error_message: null, provider_error_code: null, provider_error_message: null, created_at: now })
    if (path === '/reviews/pending' && method === 'GET') return fulfill(route, [])

    if (path === '/chat' && method === 'POST') return fulfill(route, chatResponse)
    if (path === `/chat/traces/${trace.trace_id}` && method === 'GET') return fulfill(route, trace)
    if (path === `/chat/traces/${trace.trace_id}/lineage` && method === 'GET') return fulfill(route, lineage)
    if (path === '/chat/traces' && method === 'GET') return fulfill(route, [trace])
    if (path === '/feedback' && method === 'GET') return fulfill(route, [])
    if (path === '/feedback' && method === 'POST') {
      const payload = jsonBody(route)
      return fulfill(route, { id: feedbackId++, trace_id: String(payload.trace_id ?? trace.trace_id), rating: payload.rating ?? 5, feedback_type: payload.feedback_type ?? 'helpful', comment: null, expected_document_id: null, resolved: false, converted_to_evaluation: false, created_at: now }, 201)
    }

    if (path === '/evaluations' && method === 'GET') return fulfill(route, [evaluationRun])
    if (path === '/evaluations/run' && method === 'POST') return fulfill(route, { ...evaluationRun, id: 2, run_name: 'new-evaluation' }, 201)
    if (path.match(/^\/evaluations\/\d+\/report$/) && method === 'GET') return fulfill(route, { run_id: evaluationRun.id, run_name: evaluationRun.run_name, aggregate: { recall_at_1: 1, mrr: 1, ndcg: 1, citation_accuracy: 1, refusal_accuracy: 1, hallucination_rate: 0 }, questions: [{ question_id: 'q-1', passed: true }], artifacts: {}, measurement_notes: ['fixture-backed'] })
    if (path === '/experiments' && method === 'GET') return fulfill(route, [])

    if (method === 'GET') return fulfill(route, [])
    if (method === 'DELETE') return route.fulfill({ status: 204 })
    return fulfill(route, {})
  })
}

export async function loginAsAdmin(page: Page, redirect = '/'): Promise<void> {
  const query = redirect === '/' ? '' : `?redirect=${encodeURIComponent(redirect)}`
  await page.goto(`/login${query}`)
  await page.locator('#username').fill('admin')
  await page.locator('#password').fill('odirag-demo-admin')
  await Promise.all([
    page.waitForURL((url) => url.pathname === redirect),
    page.locator('.login-submit').click(),
  ])
  await expect(page.locator('.topbar')).toBeVisible()
}
