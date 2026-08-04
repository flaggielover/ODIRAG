import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('评估与监控关键旅程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page)
  })

  test('可查看评估报告及逐题结果', async ({ page }) => {
    await loginAsAdmin(page, '/evaluations')
    await expect(page.getByRole('heading', { name: '评估', exact: true })).toBeVisible()
    await expect(page.getByText('fixture-evaluation')).toBeVisible()
    await page.getByRole('button', { name: '查看报告' }).click()
    await expect(page.getByText('Recall@1')).toBeVisible()
    await expect(page.locator('.json-panel').last()).toContainText('q-1')
  })

  test('监控页展示健康依赖、DB P95 和告警动作', async ({ page }) => {
    await loginAsAdmin(page, '/monitoring')
    await expect(page.getByRole('heading', { name: '监控与告警' })).toBeVisible()
    await expect(page.getByText('DB P95')).toBeVisible()
    await expect(page.getByText('8 ms', { exact: true })).toBeVisible()
    await expect(page.getByText('示例延迟告警')).toBeVisible()

    await page.getByRole('button', { name: '确认', exact: true }).click()
    await expect(page.locator('tbody .status-badge').filter({ hasText: '已确认' })).toBeVisible()
    await page.getByRole('button', { name: '解决', exact: true }).click()
    await expect(page.locator('tbody .status-badge').filter({ hasText: '已解决' })).toBeVisible()
  })
})
