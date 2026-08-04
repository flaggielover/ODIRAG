import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StatusBadge from '@/components/StatusBadge.vue'

describe('StatusBadge', () => {
  it('shows semantic labels and tones without relying on color alone', () => {
    const completed = mount(StatusBadge, { props: { status: 'completed' } })
    expect(completed.text()).toContain('已完成')
    expect(completed.classes()).toContain('status-success')

    const failed = mount(StatusBadge, { props: { status: 'failed' } })
    expect(failed.text()).toContain('失败')
    expect(failed.classes()).toContain('status-danger')
  })

  it.each([
    ['pending_approval', '待审批', 'status-info'],
    ['activated', '已激活', 'status-success'],
    ['validation_failed', '验证失败', 'status-danger'],
    ['no_gap', '无缺口', 'status-success'],
    ['gap_detected', '检测到缺口', 'status-warning'],
  ])('maps source discovery status %s to an accessible label and tone', (status, label, tone) => {
    const wrapper = mount(StatusBadge, { props: { status } })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.classes()).toContain(tone)
  })
})
