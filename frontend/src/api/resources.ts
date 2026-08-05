import { apiRequest } from '@/api/client'
import type {
  Alert,
  AlertSeverity,
  AlertStatus,
  AnswerLineage,
  ChatResponse,
  Chunk,
  CrawlTask,
  CrawlTaskInput,
  DocumentDetail,
  DocumentSummary,
  EvaluationReport,
  EvaluationRun,
  EvaluationRunInput,
  Experiment,
  ExperimentComparison,
  Feedback,
  FeedbackType,
  HealthResponse,
  IndexResult,
  MetricsResponse,
  PendingReviewDocument,
  QueryTrace,
  ReviewPipelineResult,
  Source,
  SourceCandidate,
  SourceDiscoveryEvent,
  SourceDiscoveryMetrics,
  SourceDiscoveryRun,
  SourceDiscoveryRunInput,
  SourceInput,
  SourceTestResult,
  CozeStatus,
  CozeConnectionResult,
  CozeContract,
  CozeInvocation,
  CrawlTaskFailure,
  CrawlTaskResult,
  CrawlTaskAcceptanceSummary,
} from '@/api/types'

function queryString(values: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}

export const api = {
  health: () => apiRequest<HealthResponse>('/system/health', {}, { auth: false }),
  metrics: () => apiRequest<MetricsResponse>('/system/metrics'),
  cozeStatus: () => apiRequest<CozeStatus>('/system/coze/status'),
  alerts: (filters: { status?: AlertStatus; severity?: AlertSeverity; refresh?: boolean } = {}) =>
    apiRequest<Alert[]>(`/system/alerts${queryString(filters)}`),
  acknowledgeAlert: (id: number) =>
    apiRequest<Alert>(`/system/alerts/${id}/acknowledge`, { method: 'POST' }),
  resolveAlert: (id: number) =>
    apiRequest<Alert>(`/system/alerts/${id}/resolve`, { method: 'POST' }),

  sources: (enabled?: boolean) =>
    apiRequest<Source[]>(`/sources${queryString({ enabled })}`),
  source: (id: number) => apiRequest<Source>(`/sources/${id}`),
  createSource: (payload: SourceInput) =>
    apiRequest<Source>('/sources', { method: 'POST', body: JSON.stringify(payload) }),
  updateSource: (id: number, payload: Partial<Omit<SourceInput, 'columns' | 'source_key'>>) =>
    apiRequest<Source>(`/sources/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteSource: (id: number) => apiRequest<void>(`/sources/${id}`, { method: 'DELETE' }),
  testSource: (id: number) => apiRequest<SourceTestResult>(`/sources/${id}/connectivity-tests/local`, { method: 'POST' }),
  testSourceCoze: (id: number, contract: CozeContract) =>
    apiRequest<CozeConnectionResult>(`/sources/${id}/connectivity-tests/coze${queryString({ contract })}`, { method: 'POST' }),
  testSourceLocal: (id: number) =>
    apiRequest<SourceTestResult>(`/sources/${id}/connectivity-tests/local`, { method: 'POST' }),

  sourceDiscoveryMetrics: () => apiRequest<SourceDiscoveryMetrics>('/source-discovery/metrics'),
  sourceDiscoveryRuns: (limit = 100) =>
    apiRequest<SourceDiscoveryRun[]>(`/source-discovery/runs${queryString({ limit })}`),
  sourceDiscoveryRun: (id: number) =>
    apiRequest<SourceDiscoveryRun>(`/source-discovery/runs/${id}`),
  createSourceDiscoveryRun: (payload: SourceDiscoveryRunInput) =>
    apiRequest<SourceDiscoveryRun>('/source-discovery/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  retrySourceDiscoveryRun: (id: number) =>
    apiRequest<SourceDiscoveryRun>(`/source-discovery/runs/${id}/retry`, { method: 'POST' }),
  sourceDiscoveryCandidates: (runId: number) =>
    apiRequest<SourceCandidate[]>(`/source-discovery/runs/${runId}/candidates`),
  sourceDiscoveryRunEvents: (runId: number, limit = 500) =>
    apiRequest<SourceDiscoveryEvent[]>(
      `/source-discovery/runs/${runId}/events${queryString({ limit })}`,
    ),
  sourceCandidate: (id: number) =>
    apiRequest<SourceCandidate>(`/source-discovery/candidates/${id}`),
  sourceCandidateEvents: (id: number, limit = 500) =>
    apiRequest<SourceDiscoveryEvent[]>(
      `/source-discovery/candidates/${id}/events${queryString({ limit })}`,
    ),
  approveSourceCandidate: (id: number) =>
    apiRequest<SourceCandidate>(`/source-discovery/candidates/${id}/approve`, { method: 'POST' }),
  rejectSourceCandidate: (id: number, reason: string) =>
    apiRequest<SourceCandidate>(`/source-discovery/candidates/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  activateSourceCandidate: (id: number) =>
    apiRequest<SourceCandidate>(`/source-discovery/candidates/${id}/activate`, { method: 'POST' }),

  crawlTasks: (status?: string) =>
    apiRequest<CrawlTask[]>(`/crawl-tasks${queryString({ status })}`),
  crawlTask: (id: number) => apiRequest<CrawlTask>(`/crawl-tasks/${id}`),
  crawlTaskAcceptanceSummary: (id: number) =>
    apiRequest<CrawlTaskAcceptanceSummary>(`/crawl-tasks/${id}/acceptance-summary`),
  crawlInvocations: (id: number) => apiRequest<CozeInvocation[]>(`/crawl-tasks/${id}/invocations`),
  crawlTaskFailures: (id: number) => apiRequest<CrawlTaskFailure[]>(`/crawl-tasks/${id}/failed-urls`),
  retryCrawlTaskFailure: (taskId: number, failureId: number) =>
    apiRequest<CrawlTaskFailure>(`/crawl-tasks/${taskId}/failed-urls/${failureId}/retry`, { method: 'POST' }),
  crawlTaskResults: (id: number, decision?: string) =>
    apiRequest<CrawlTaskResult[]>(`/crawl-tasks/${id}/results${queryString({ decision })}`),
  createCrawlTask: (payload: CrawlTaskInput) =>
    apiRequest<CrawlTask>('/crawl-tasks', { method: 'POST', body: JSON.stringify(payload) }),
  retryCrawlTask: (id: number) =>
    apiRequest<CrawlTask>(`/crawl-tasks/${id}/retry`, { method: 'POST' }),
  cancelCrawlTask: (id: number) =>
    apiRequest<CrawlTask>(`/crawl-tasks/${id}/cancel`, { method: 'POST' }),

  documents: (filters: Record<string, string | number | undefined> = {}) =>
    apiRequest<DocumentSummary[]>(`/documents${queryString(filters)}`),
  document: (id: number) => apiRequest<DocumentDetail>(`/documents/${id}`),
  documentChunks: (id: number) => apiRequest<Chunk[]>(`/documents/${id}/chunks`),
  reindexDocument: (id: number) =>
    apiRequest<IndexResult>(`/documents/${id}/reindex`, { method: 'POST' }),

  pendingReviews: () => apiRequest<PendingReviewDocument[]>('/reviews/pending'),
  runReview: (id: number) =>
    apiRequest<ReviewPipelineResult>(`/reviews/${id}/run`, { method: 'POST' }),
  manualReview: (id: number, decision: 'approve' | 'reject', summary: string, reasons: string[]) =>
    apiRequest<{ document_id: number; decision: string; final_status: string }>(
      `/reviews/${id}/manual-review`,
      { method: 'POST', body: JSON.stringify({ decision, summary, reasons }) },
    ),

  chat: (query: string, filters: Record<string, unknown>) =>
    apiRequest<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ query, filters }),
    }),
  trace: (traceId: string) => apiRequest<QueryTrace>(`/chat/traces/${traceId}`),
  traces: (filters: { limit?: number; query_type?: string; refusal?: boolean } = {}) =>
    apiRequest<QueryTrace[]>(`/chat/traces${queryString({ limit: 100, ...filters })}`),
  lineage: (traceId: string) =>
    apiRequest<AnswerLineage>(`/chat/traces/${traceId}/lineage`),

  evaluations: (limit = 100) =>
    apiRequest<EvaluationRun[]>(`/evaluations${queryString({ limit })}`),
  runEvaluation: (payload: EvaluationRunInput) =>
    apiRequest<EvaluationRun>('/evaluations/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  evaluationReport: (id: number) => apiRequest<EvaluationReport>(`/evaluations/${id}/report`),

  experiments: (limit = 100) =>
    apiRequest<Experiment[]>(`/experiments${queryString({ limit })}`),
  createExperiment: (payload: {
    experiment_name: string
    experiment_type: string
    baseline_config: Record<string, unknown>
    candidate_config: Record<string, unknown>
  }) =>
    apiRequest<Experiment>('/experiments', { method: 'POST', body: JSON.stringify(payload) }),
  runExperiment: (id: number, payload: Record<string, unknown>) =>
    apiRequest<Experiment>(`/experiments/${id}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  experimentComparison: (id: number) =>
    apiRequest<ExperimentComparison>(`/experiments/${id}/compare`),

  feedback: (filters: { resolved?: boolean; feedback_type?: FeedbackType } = {}) =>
    apiRequest<Feedback[]>(`/feedback${queryString(filters)}`),
  createFeedback: (payload: {
    trace_id: string
    feedback_type: FeedbackType
    rating?: number | null
    comment?: string | null
    expected_document_id?: number | null
  }) => apiRequest<Feedback>('/feedback', { method: 'POST', body: JSON.stringify(payload) }),
  convertFeedback: (id: number) =>
    apiRequest<Feedback>(`/feedback/${id}/convert-to-evaluation`, { method: 'POST' }),
}
