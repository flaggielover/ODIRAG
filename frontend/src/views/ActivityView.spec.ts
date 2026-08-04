import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Feedback } from '@/api/types'
import ActivityView from '@/views/ActivityView.vue'

const apiMocks = vi.hoisted(() => ({
  traces: vi.fn(),
  feedback: vi.fn(),
  convertFeedback: vi.fn(),
}))

vi.mock('@/api/resources', () => ({ api: apiMocks }))

const feedbackItems: Feedback[] = [
  {
    id: 1,
    trace_id: 'trace-helpful',
    rating: 5,
    feedback_type: 'helpful',
    comment: null,
    expected_document_id: null,
    resolved: false,
    converted_to_evaluation: false,
    created_at: '2026-08-03T00:00:00Z',
  },
  {
    id: 2,
    trace_id: 'trace-incomplete',
    rating: 3,
    feedback_type: 'incomplete_answer',
    comment: '需要补充申报期限',
    expected_document_id: null,
    resolved: false,
    converted_to_evaluation: false,
    created_at: '2026-08-03T00:00:00Z',
  },
]

describe('ActivityView', () => {
  beforeEach(() => {
    apiMocks.traces.mockReset().mockResolvedValue([])
    apiMocks.feedback.mockReset().mockResolvedValue(feedbackItems)
    apiMocks.convertFeedback.mockReset().mockResolvedValue(feedbackItems[1])
  })

  it('only allows actionable feedback to become an evaluation case', async () => {
    const wrapper = mount(ActivityView, {
      global: {
        stubs: {
          AsyncState: { template: '<div><slot /></div>' },
          JsonPanel: true,
          ModalDialog: true,
          PageHeader: true,
          StatusBadge: true,
        },
      },
    })

    await flushPromises()

    const convertButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('转为评估'))

    expect(convertButtons).toHaveLength(2)
    expect(convertButtons[0]!.attributes('disabled')).toBeDefined()
    expect(convertButtons[0]!.attributes('title')).toBe('正向反馈无需转为评估')
    expect(convertButtons[1]!.attributes('disabled')).toBeUndefined()

    await convertButtons[1]!.trigger('click')
    await flushPromises()

    expect(apiMocks.convertFeedback).toHaveBeenCalledOnce()
    expect(apiMocks.convertFeedback).toHaveBeenCalledWith(2)
  })
})
