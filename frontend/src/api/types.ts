export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject
export type JsonObject = { [key: string]: JsonValue }

export interface ApiErrorPayload {
  error?: {
    code?: string
    message?: string
    details?: unknown
    request_id?: string
  }
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: number
  username: string
  is_active: boolean
  is_superuser: boolean
  created_at: string
  updated_at: string
}

export interface SourceColumn {
  id: number
  source_id: number
  column_key: string
  column_name: string
  column_url: string
  parser_type: string
  enabled: boolean
  max_pages: number
  request_interval_seconds: number
  selectors_json: Record<string, unknown>
  pagination_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Source {
  id: number
  source_key: string
  name: string
  domain: string
  region: string | null
  city: string | null
  organization_level: string | null
  organization_type: string | null
  official_status: string
  homepage_url: string
  enabled: boolean
  priority: number
  crawl_frequency: string
  crawl_provider?: CrawlProvider
  coze_contract_mode?: CozeContract
  last_coze_status?: string | null
  last_coze_article_count?: number | null
  last_coze_error?: string | null
  last_coze_test_at?: string | null
  last_successful_crawl_at?: string | null
  last_crawl_time: string | null
  created_at: string
  updated_at: string
  columns: SourceColumn[]
}

export interface SourceInput {
  source_key: string
  name: string
  domain: string
  region?: string | null
  city?: string | null
  organization_level?: string | null
  organization_type?: string | null
  official_status: string
  homepage_url: string
  enabled: boolean
  priority: number
  crawl_frequency: string
  crawl_provider?: SupportedCrawlProvider
  coze_contract_mode?: CozeContract
  columns: Array<{
    column_key: string
    column_name: string
    column_url: string
    parser_type: string
    enabled: boolean
    max_pages: number
    request_interval_seconds: number
    selectors_json: Record<string, unknown>
    pagination_json: Record<string, unknown>
  }>
}

export interface SourceTestResult {
  reachable: boolean
  status_code: number | null
  latency_ms: number
  final_url: string | null
  error_type: string | null
}

export type SupportedCrawlProvider = 'coze' | 'local'
export type CrawlProvider = SupportedCrawlProvider | 'playwright'
export type CozeContract = 'legacy_single_article' | 'batch_crawl'

export interface CozeStatus {
  enabled: boolean
  token_configured: boolean
  legacy_workflow_configured: boolean
  batch_workflow_configured: boolean
  default_contract: CozeContract
}

export interface CozeConnectionResult {
  available: boolean
  reachable?: boolean
  contract: CozeContract
  status_code: number | null
  latency_ms: number
  error_code: string | null
  final_url?: string | null
  error_type?: string | null
  provider?: 'coze'
  status?: string
  message?: string | null
  checked_at?: string
}

export interface SourceDiscoveryRunInput {
  topic: string
  region?: string | null
  organization_level?: string | null
  query_text?: string | null
  required_source_count: number
  required_document_count: number
  max_candidates?: number | null
  execution_mode: 'queued' | 'inline'
}

export interface SourceDiscoveryRun {
  id: number
  topic: string
  region: string | null
  organization_level: string | null
  query_text: string
  required_source_count: number
  required_document_count: number
  existing_source_count: number
  existing_document_count: number
  gap_detected: boolean
  gap_evidence_json: Record<string, unknown>
  status: string
  discovery_provider: string
  max_candidates: number
  candidate_count: number
  approved_count: number
  activated_count: number
  attempt_count: number
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface SourceCandidateColumn {
  id: number
  candidate_id: number
  column_key: string
  column_name: string
  column_url: string
  parser_type: string
  selectors_json: Record<string, unknown>
  pagination_json: Record<string, unknown>
  discovery_evidence_json: Record<string, unknown>
  status: string
  trial_discovered_count: number
  trial_fetched_count: number
  trial_success_count: number
  trial_failed_count: number
  trial_average_chars: number
  quality_score: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface SourceCandidate {
  id: number
  run_id: number
  canonical_homepage_url: string
  domain: string
  name: string
  snippet: string | null
  search_rank: number | null
  discovery_provider: string
  discovery_query: string
  official_status: string
  official_score: number | null
  official_evidence_json: Record<string, unknown>
  validation_status_code: number | null
  validation_final_url: string | null
  status: string
  quality_score: number | null
  quality_breakdown_json: Record<string, unknown>
  trial_column_count: number
  trial_document_count: number
  trial_success_count: number
  trial_failed_count: number
  trial_average_chars: number
  rejection_reason: string | null
  approved_by: string | null
  approved_at: string | null
  source_id: number | null
  created_at: string
  updated_at: string
  columns: SourceCandidateColumn[]
}

export interface SourceDiscoveryEvent {
  id: number
  run_id: number
  candidate_id: number | null
  stage: string
  from_status: string | null
  to_status: string
  message: string
  details_json: Record<string, unknown>
  created_at: string
}

export interface SourceDiscoveryMetrics {
  run_status_counts: Record<string, number>
  candidate_status_counts: Record<string, number>
  column_status_counts: Record<string, number>
  pending_approval_count: number
  activated_source_count: number
  average_quality_score: number
  last_run_at: string | null
}

export interface CrawlTask {
  id: number
  source_column_id: number
  task_type: string
  trigger_type: string
  status: string
  started_at: string | null
  finished_at: string | null
  discovered_count: number
  fetched_count: number
  success_count: number
  url_duplicate_count: number
  content_duplicate_count: number
  semantic_duplicate_count: number
  failed_count: number
  retry_count: number
  error_message: string | null
  created_at: string
  crawl_provider?: CrawlProvider
  provider?: CrawlProvider
  provider_contract?: CozeContract | null
  contract_mode?: CozeContract | null
  provider_task_id?: string | null
  coze_execution_id?: string | null
  current_stage?: string | null
  stage?: string | null
  stage_counts?: Record<string, number>
  provider_status?: string | null
  provider_error_code?: string | null
  provider_error_message?: string | null
  accepted_count?: number
  rejected_count?: number
  pending_review_count?: number
  max_articles?: number
  max_pages?: number
  raw_result_available?: boolean
  next_retry_at?: string | null
  completed_at?: string | null
}

export interface CrawlTaskAcceptanceSummary {
  crawl_task_id: number
  database_document_count: number
  chunk_count: number
  qdrant_point_count: number
}

export interface CrawlTaskInput {
  source_column_id: number
  task_type: 'full' | 'incremental'
  trigger_type: 'manual' | 'schedule' | 'retry'
  execution_mode: 'queued' | 'inline'
  provider_contract?: CozeContract | null
  max_articles?: number
  max_pages?: number
}

export interface CozeInvocation {
  id: number
  crawl_task_id: number
  contract: CozeContract
  endpoint_url: string
  deployment_identifier?: string
  source_id?: number
  status: string
  request_json: unknown
  raw_response_json: unknown | null
  normalized_response_json: unknown | null
  http_status_code: number | null
  attempt_count: number
  retry_count: number
  duration_ms: number | null
  token_usage_json: Record<string, unknown>
  error_code: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface CrawlTaskFailure {
  id: number
  crawl_task_id: number
  url: string
  stage: string
  error_code: string
  error_message: string
  retryable: boolean
  status: string
  retry_count: number
  last_attempt_at: string | null
  next_retry_at: string | null
  resolved_at: string | null
  created_at: string
  updated_at: string
}

export interface CrawlTaskResult {
  id: number
  document_id: string
  title: string
  source_url: string
  decision: string
  quality_score: number | null
  final_status: string
  review_reason: string | null
}

export interface DocumentSummary {
  id: number
  document_id: string
  title: string
  source_url: string
  source_id: number | null
  source: {
    id: number
    source_key: string
    name: string
    domain: string
    official_status: string
  } | null
  publish_date: string | null
  issuing_authority: string | null
  document_number: string | null
  region: string | null
  city: string | null
  document_type: string | null
  word_count: number
  language: string | null
  quality_score: string | number | null
  rule_filter_status: string
  llm_review_status: string
  manual_review_status: string
  final_status: string
  index_status: string
  version: number
  last_crawl_time: string | null
  created_at: string
  updated_at: string
}

export interface DocumentVersion {
  id: number
  document_id: number
  version: number
  content_hash: string
  content: string
  metadata_json: Record<string, unknown>
  changed_fields_json: string[]
  created_at: string
}

export interface Attachment {
  id: number
  document_id: number
  attachment_name: string
  source_url: string
  local_path: string | null
  mime_type: string | null
  file_extension: string | null
  file_size: number | null
  file_hash: string | null
  download_status: string
  parse_status: string
  parsed_text: string | null
  page_count: number | null
  requires_ocr: boolean
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentReview {
  id: number
  document_id: number
  review_type: string
  reviewer: string
  decision: string
  quality_score: string | number | null
  document_type: string | null
  topics_json: string[]
  summary: string | null
  reasons_json: string[]
  extracted_fields_json: Record<string, unknown>
  model_name: string | null
  prompt_name: string | null
  prompt_version: string | null
  raw_response: string | null
  created_at: string
}

export interface DocumentDetail extends DocumentSummary {
  source_column_id: number | null
  subtitle: string | null
  canonical_url: string | null
  author: string | null
  content: string
  raw_content: string | null
  content_hash: string | null
  simhash: string | null
  parent_document_id: number | null
  duplicate_of_document_id: number | null
  first_crawl_time: string | null
  last_crawl_time: string | null
  versions: DocumentVersion[]
  attachments: Attachment[]
  reviews: DocumentReview[]
}

export interface Chunk {
  id: number
  chunk_id: string
  document_id: number
  attachment_id: number | null
  chunk_index: number
  section_path: string | null
  section_title: string | null
  page_number: number | null
  content: string
  content_hash: string
  char_count: number
  token_count: number
  embedding_model: string | null
  embedding_version: string | null
  vector_status: string
  created_at: string
  updated_at: string
}

export interface IndexResult {
  document_id: number
  document_version: number
  chunk_count: number
  cache_hits: number
  embedded_count: number
  embedding_model: string
  embedding_version: string
  estimated_cost: number
  vector_point_ids: string[]
  bm25_document_count: number
}

export interface PendingReviewDocument {
  id: number
  document_id: string
  title: string
  source_url: string
  rule_filter_status: string
  llm_review_status: string
  manual_review_status: string
  final_status: string
  created_at: string
}

export interface ReviewPipelineResult {
  document_id: number
  rule_decision: string
  rule_score: number
  llm_decision: string | null
  final_status: string
  extracted_fields: Record<string, unknown>
}

export interface Citation {
  document_id: string
  chunk_id: string
  title: string
  source: string
  publication_date: string | null
  url: string
  page: number | null
  quote: string
}

export interface ChatResponse {
  trace_id: string
  query_type: 'sql' | 'rag' | 'sql+rag'
  answer: string
  refusal: boolean
  refusal_reasons: string[]
  conflicts: string[]
  outdated: string[]
  citations: Citation[]
  filters: Record<string, unknown>
  structured_count: number | null
}

export interface QueryTrace {
  trace_id: string
  user_query: string
  query_type: string
  parsed_filters_json: Record<string, unknown>
  bm25_results_json: Array<Record<string, unknown>>
  vector_results_json: Array<Record<string, unknown>>
  fusion_results_json: Array<Record<string, unknown>>
  rerank_results_json: Array<Record<string, unknown>>
  final_context_json: Array<Record<string, unknown>>
  prompt_version: string | null
  prompt_snapshot_json: Record<string, unknown>
  model_name: string | null
  answer: string | null
  citations_json: Array<Record<string, unknown>>
  refusal: boolean
  latency_ms: number
  token_usage_json: Record<string, unknown>
  cost: string | number
  created_at: string
}

export interface CitationLineage {
  citation: Record<string, unknown>
  chunk: Record<string, unknown> | null
  document: Record<string, unknown> | null
  document_version: Record<string, unknown> | null
  crawl_task: Record<string, unknown> | null
  source: Record<string, unknown> | null
  lineage_ids: string[]
  complete: boolean
  missing_steps: string[]
}

export interface AnswerLineage {
  trace_id: string
  answer: string | null
  prompt_version: string | null
  prompt_snapshot: Record<string, unknown>
  citations: CitationLineage[]
}

export interface EvaluationRun {
  id: number
  run_name: string
  experiment_id: number | null
  retrieval_version: string | null
  prompt_version: string | null
  embedding_model: string | null
  rerank_model: string | null
  top_k: number
  started_at: string | null
  finished_at: string | null
  question_count: number
  recall_at_1: string | number | null
  recall_at_5: string | number | null
  recall_at_10: string | number | null
  mrr: string | number | null
  ndcg: string | number | null
  citation_accuracy: string | number | null
  refusal_accuracy: string | number | null
  hallucination_rate: string | number | null
  average_latency: string | number | null
  p95_latency: string | number | null
  average_cost: string | number | null
  result_path: string | null
  created_at: string
}

export interface EvaluationQuestionInput {
  question_id: string
  question: string
  query_type: 'sql' | 'rag' | 'sql+rag'
  expected_document_ids: string[]
  expected_chunk_ids: string[]
  expected_answer_points: string[]
  expected_filters: Record<string, unknown>
  should_refuse: boolean
  difficulty?: string | null
  category?: string | null
  created_by?: string | null
  verified: boolean
}

export interface EvaluationRunInput {
  run_name: string
  question_ids: string[]
  questions: EvaluationQuestionInput[]
  category?: string | null
  retrieval_version?: string | null
  prompt_version?: string | null
  top_k: number
}

export interface EvaluationReport {
  run_id: number
  run_name: string
  aggregate: Record<string, number>
  questions?: Array<Record<string, unknown>>
  cases?: Array<Record<string, unknown>>
  artifacts: Record<string, string>
  measurement_notes?: string[]
}

export interface Experiment {
  id: number
  experiment_name: string
  experiment_type: string
  baseline_config_json: Record<string, unknown>
  candidate_config_json: Record<string, unknown>
  status: string
  started_at: string | null
  finished_at: string | null
  conclusion: string | null
  artifact_path: string | null
  created_at: string
}

export interface ExperimentComparison {
  experiment_id?: number
  experiment_name?: string
  conclusion: string
  regressions: Array<Record<string, unknown>>
  comparisons: Array<Record<string, unknown>>
  failed_cases: Array<Record<string, unknown>>
  artifacts: Record<string, string>
  [key: string]: unknown
}

export interface DependencyHealth {
  status: 'healthy' | 'unavailable' | 'disabled'
  latency_ms: number | null
  detail: string | null
}

export interface HealthResponse {
  status: 'healthy' | 'degraded'
  service: string
  environment: string
  checked_at: string
  dependencies: Record<string, DependencyHealth>
}

export interface MetricsResponse {
  uptime_seconds: number
  requests_total: number
  requests_by_status_class: Record<string, number>
  routes: Array<{
    method: string
    path: string
    status_code: number
    count: number
    sample_count: number
    average_latency_ms: number
    p50_latency_ms: number
    p95_latency_ms: number
    p99_latency_ms: number
  }>
  database_latency: {
    sample_count: number
    average_latency_ms: number
    p50_latency_ms: number
    p95_latency_ms: number
    p99_latency_ms: number
  }
  crawler: {
    window_hours: number
    task_count: number
    status_counts: Record<string, number>
    task_failure_rate: number
    discovered_count: number
    fetched_count: number
    success_count: number
    failed_count: number
    item_failure_rate: number
  }
  knowledge: {
    document_count: number
    final_status_counts: Record<string, number>
    index_status_counts: Record<string, number>
    approved_count: number
    indexed_count: number
    index_failure_count: number
    stale_count: number
    chunk_count: number
  }
  rag: {
    window_hours: number
    query_count: number
    refusal_count: number
    refusal_rate: number
    average_latency_ms: number
    p50_latency_ms: number
    p95_latency_ms: number
    total_tokens: number
    measured_token_trace_count: number
    total_cost: string | number
    average_cost: string | number
    trace_completeness_rate: number
    evaluation_regression_count: number
  }
  dependencies: Record<string, DependencyHealth>
}

export type AlertStatus = 'open' | 'acknowledged' | 'resolved'
export type AlertSeverity = 'info' | 'warning' | 'high' | 'critical'

export interface Alert {
  id: number
  alert_key: string
  alert_type: string
  severity: AlertSeverity
  status: AlertStatus
  component: string
  message: string
  observed_value: string | number | null
  threshold_value: string | number | null
  details_json: Record<string, unknown>
  occurrence_count: number
  first_seen_at: string
  last_seen_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  created_at: string
  updated_at: string
}

export type FeedbackType =
  | 'helpful'
  | 'not_helpful'
  | 'incorrect_citation'
  | 'missing_document'
  | 'incomplete_answer'
  | 'should_refuse'
  | 'should_not_refuse'

export interface Feedback {
  id: number
  trace_id: string
  rating: number | null
  feedback_type: FeedbackType
  comment: string | null
  expected_document_id: number | null
  resolved: boolean
  converted_to_evaluation: boolean
  created_at: string
}
