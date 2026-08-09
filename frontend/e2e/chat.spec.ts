import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('问答、引用与反馈关键旅程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page)
  })

  test('回答展示引用和 Trace，并可提交正向反馈', async ({ page }) => {
    await loginAsAdmin(page, '/chat')
    const feedbackRequest = page.waitForRequest((request) => request.url().endsWith('/api/feedback') && request.method() === 'POST')

    await page.locator('textarea[placeholder="输入查询"]').fill('研发投入支持措施有哪些？')
    await page.getByRole('button', { name: '发送' }).click()

    await expect(page.getByText('企业研发投入支持措施')).toBeVisible()
    await expect(page.getByText('支持企业研发投入，鼓励创新主体持续增加研发投入。')).toBeVisible()
    await expect(page.getByText('trace-e2e-001', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '检索' }).click()
    await expect(page.getByText('证据充分性')).toBeVisible()
    await expect(page.getByText('evidence_covers_all_query_aspects')).toBeVisible()
    await page.getByRole('button', { name: '有帮助', exact: true }).click()
    await expect(page.getByText('已记录')).toBeVisible()

    const request = await feedbackRequest
    expect(request.postDataJSON()).toMatchObject({ trace_id: 'trace-e2e-001', feedback_type: 'helpful', rating: 5 })
    await page.getByRole('button', { name: '血缘' }).click()
    await expect(page.getByText('引用 1')).toBeVisible()
  })
})
