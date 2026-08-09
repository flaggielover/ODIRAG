import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CrawlTaskDetailView from '@/views/CrawlTaskDetailView.vue'

const apiMocks = vi.hoisted(() => ({
  crawlTask: vi.fn(),
  crawlTaskAcceptanceSummary: vi.fn(),
  crawlInvocations: vi.fn(),
  crawlTaskFailures: vi.fn(),
  crawlTaskResults: vi.fn(),
  retryCrawlTaskFailure: vi.fn(),
}))

vi.mock('@/api/resources', () => ({ api: apiMocks }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '9' } }) }))

const task = {
  id: 9,
  source_column_id: 1,
  task_type: 'incremental',
  trigger_type: 'manual',
  status: 'completed',
  started_at: '2026-08-04T00:00:00Z',
  finished_at: '2026-08-04T00:01:00Z',
  discovered_count: 5,
  fetched_count: 5,
  success_count: 3,
  url_duplicate_count: 0,
  content_duplicate_count: 0,
  semantic_duplicate_count: 0,
  failed_count: 2,
  retry_count: 1,
  error_message: null,
  created_at: '2026-08-04T00:00:00Z',
  crawl_provider: 'coze' as const,
  provider_contract: 'batch_crawl' as const,
  coze_execution_id: 'exec-9',
  current_stage: 'saving_documents',
  stage_counts: { discovered: 5, accepted: 3 },
  accepted_count: 3,
  rejected_count: 0,
  pending_review_count: 0,
  provider_status: 'completed',
  provider_error_code: null,
  provider_error_message: null,
}

function mountView() {
  return mount(CrawlTaskDetailView, {
    global: {
      stubs: {
        AsyncState: { template: '<div><slot /></div>' },
        PageHeader: { template: '<div><slot name="actions" /></div>' },
        RouterLink: { template: '<a><slot /></a>' },
        StatusBadge: { props: ['status'], template: '<span>{{ status }}</span>' },
      },
    },
  })
}

describe('CrawlTaskDetailView', () => {
  beforeEach(() => {
    apiMocks.crawlTask.mockReset().mockResolvedValue(task)
    apiMocks.crawlTaskAcceptanceSummary.mockReset().mockResolvedValue({
      crawl_task_id: 9,
      database_document_count: 3,
      chunk_count: 8,
      qdrant_collection_exists: true,
      qdrant_point_count: 8,
    })
    apiMocks.crawlInvocations.mockReset().mockResolvedValue([])
    apiMocks.crawlTaskFailures.mockReset().mockResolvedValue([])
    apiMocks.crawlTaskResults.mockReset().mockResolvedValue([])
    apiMocks.retryCrawlTaskFailure.mockReset().mockResolvedValue({})
  })

  it('loads and displays persisted database, chunk, and Qdrant acceptance counts', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(apiMocks.crawlTaskAcceptanceSummary).toHaveBeenCalledWith(9)
    expect(wrapper.text()).toContain('验收摘要')
    expect(wrapper.text()).toContain('数据库文档')
    expect(wrapper.text()).toContain('Qdrant 向量点')
    expect(wrapper.text()).toContain('已创建')
    expect(wrapper.text()).toContain('8')
  })

  it('shows an absent Qdrant collection without hiding database counts', async () => {
    apiMocks.crawlTaskAcceptanceSummary.mockResolvedValueOnce({
      crawl_task_id: 9,
      database_document_count: 3,
      chunk_count: 0,
      qdrant_collection_exists: false,
      qdrant_point_count: 0,
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('未创建')
    expect(wrapper.text()).toContain('3')
  })

  it('keeps task details visible and surfaces an acceptance-summary failure', async () => {
    apiMocks.crawlTaskAcceptanceSummary.mockRejectedValueOnce(new Error('Qdrant unavailable'))

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('exec-9')
    expect(wrapper.text()).toContain('验收摘要不可用：Qdrant unavailable')
  })
})
