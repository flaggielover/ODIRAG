import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Source } from '@/api/types'
import SourcesView from '@/views/SourcesView.vue'

const apiMocks = vi.hoisted(() => ({
  sources: vi.fn(),
  cozeStatus: vi.fn(),
  testSourceCoze: vi.fn(),
  testSourceLocal: vi.fn(),
  createSource: vi.fn(),
  updateSource: vi.fn(),
  deleteSource: vi.fn(),
}))

vi.mock('@/api/resources', () => ({ api: apiMocks }))

const source: Source = {
  id: 1,
  source_key: 'scsia',
  name: '四川省软件行业协会',
  domain: 'scsia.org',
  region: '四川',
  city: null,
  organization_level: null,
  organization_type: 'association',
  official_status: 'association',
  homepage_url: 'https://scsia.org/',
  enabled: true,
  priority: 10,
  crawl_frequency: 'daily',
  crawl_provider: 'coze',
  coze_contract_mode: 'batch_crawl',
  last_coze_status: null,
  last_coze_article_count: null,
  last_coze_error: null,
  last_crawl_time: null,
  created_at: '2026-08-04T00:00:00Z',
  updated_at: '2026-08-04T00:00:00Z',
  columns: [],
}

describe('SourcesView', () => {
  beforeEach(() => {
    apiMocks.sources.mockReset().mockResolvedValue([source])
    apiMocks.cozeStatus.mockReset().mockResolvedValue({ enabled: true, token_configured: true, legacy_workflow_configured: true, batch_workflow_configured: true, default_contract: 'batch_crawl' })
    apiMocks.testSourceCoze.mockReset().mockResolvedValue({ available: true, contract: 'batch_crawl', status_code: 200, latency_ms: 21, error_code: null })
    apiMocks.testSourceLocal.mockReset().mockResolvedValue({ reachable: false, status_code: null, latency_ms: 4, final_url: null, error_type: 'unsafe_url' })
  })

  it('shows Coze as the business provider and separates both connectivity checks', async () => {
    const wrapper = mount(SourcesView, {
      global: { stubs: { AsyncState: { template: '<div><slot /></div>' }, ModalDialog: true, PageHeader: { template: '<div><slot name="actions" /></div>' }, StatusBadge: { props: ['status'], template: '<span class="status-badge-stub">{{ status }}</span>' } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="coze-contract-status-batch"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="coze-contract-status-legacy"]').exists()).toBe(true)

    expect(wrapper.text()).toContain('业务抓取：Coze 工作流')
    expect(wrapper.text()).toContain('Coze 工作流')

    await wrapper.get('button[aria-label="测试 Coze 工作流"]').trigger('click')
    await flushPromises()
    expect(apiMocks.testSourceCoze).toHaveBeenCalledWith(1, 'batch_crawl')

    await wrapper.get('button[aria-label="测试本地连通性"]').trigger('click')
    await flushPromises()
    expect(apiMocks.testSourceLocal).toHaveBeenCalledWith(1)
  })

  it('reports legacy and batch configuration independently', async () => {
    apiMocks.cozeStatus.mockResolvedValueOnce({ enabled: true, token_configured: true, legacy_workflow_configured: true, batch_workflow_configured: false, default_contract: 'legacy_single_article' })

    const wrapper = mount(SourcesView, {
      global: { stubs: { AsyncState: { template: '<div><slot /></div>' }, ModalDialog: true, PageHeader: { template: '<div><slot name="actions" /></div>' }, StatusBadge: { props: ['status'], template: '<span>{{ status }}</span>' } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="coze-contract-status-batch"]').text()).toContain('unavailable')
    expect(wrapper.get('[data-testid="coze-contract-status-legacy"]').text()).toContain('healthy')
  })

  it('offers only implemented crawl providers when editing a source', async () => {
    const wrapper = mount(SourcesView, {
      global: {
        stubs: {
          AsyncState: { template: '<div><slot /></div>' },
          ModalDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          PageHeader: { template: '<div><slot name="actions" /></div>' },
          StatusBadge: true,
        },
      },
    })
    await flushPromises()

    const values = wrapper.findAll('#source-provider option').map((option) => option.attributes('value'))
    expect(values).toEqual(['coze', 'local'])
  })
})
