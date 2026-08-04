import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MarkdownContent from '@/components/MarkdownContent.vue'

describe('MarkdownContent', () => {
  it('renders Markdown while removing executable HTML and unsafe URLs', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '**可信内容**\n\n<script>alert(1)</script>\n\n[危险链接](javascript:alert(1))',
      },
    })

    expect(wrapper.html()).toContain('<strong>可信内容</strong>')
    expect(wrapper.html()).not.toContain('<script')
    expect(wrapper.html()).not.toContain('javascript:')
  })
})
