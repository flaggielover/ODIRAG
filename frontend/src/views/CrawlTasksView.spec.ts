import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CrawlTasksView from '@/views/CrawlTasksView.vue'

const apiMocks = vi.hoisted(() => ({
  crawlTasks: vi.fn(),
  sources: vi.fn(),
  createCrawlTask: vi.fn(),
  retryCrawlTask: vi.fn(),
  cancelCrawlTask: vi.fn(),
}))

vi.mock('@/api/resources', () => ({ api: apiMocks }))

describe('CrawlTasksView', () => {
  beforeEach(() => {
    apiMocks.crawlTasks.mockReset().mockResolvedValue([{ id: 9, source_column_id: 1, task_type: 'incremental', trigger_type: 'manual', status: 'coze_running', crawl_provider: 'coze', provider_contract: 'batch_crawl', coze_execution_id: 'exec-fixture-9', current_stage: 'fetching_articles', stage_counts: { discovered: 5, accepted: 2 }, accepted_count: 2, rejected_count: 0, pending_review_count: 0, started_at: '2026-08-04T00:00:00Z', finished_at: null, discovered_count: 5, fetched_count: 3, success_count: 2, url_duplicate_count: 0, content_duplicate_count: 0, semantic_duplicate_count: 0, failed_count: 1, retry_count: 0, error_message: null, provider_error_code: null, created_at: '2026-08-04T00:00:00Z' }])
    apiMocks.sources.mockReset().mockResolvedValue([])
  })

  it('renders the granular Coze state, stage counts and detail link', async () => {
    const wrapper = mount(CrawlTasksView, {
      global: { stubs: { AsyncState: { template: '<div><slot /></div>' }, ModalDialog: true, PageHeader: { template: '<div><slot name="actions" /></div>' }, StatusBadge: { props: ['status'], template: '<span>{{ status }}</span>' }, RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } }, mocks: { $router: { push: vi.fn() } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('coze_running')
    expect(wrapper.text()).toContain('discovered:5')
    expect(wrapper.text()).toContain('exec-fixture-9')
    expect(wrapper.get('a[href="/crawl-tasks/9"]').exists()).toBe(true)
  })
})
