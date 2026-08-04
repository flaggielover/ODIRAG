import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('Coze 抓取关键流程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => { await installApiFixtures(page) })

  test('来源页区分 Coze 业务测试与 Local 诊断测试', async ({ page }) => {
    await loginAsAdmin(page, '/sources')
    await expect(page.getByText('业务抓取：Coze 工作流')).toBeVisible()
    await page.getByRole('button', { name: '测试 Coze 工作流' }).click()
    await expect(page.getByText(/Coze ·/)).toBeVisible()
    await page.getByRole('button', { name: '测试本地连通性' }).click()
    await expect(page.getByText(/Local ·/)).toBeVisible()
  })

  test('任务列表可进入 Coze 任务详情并查看执行元数据', async ({ page }) => {
    await loginAsAdmin(page, '/crawl-tasks')
    await expect(page.getByText('exec-fixture-1')).toBeVisible()
    await page.locator('a[href="/crawl-tasks/1"]').click()
    await expect(page).toHaveURL(/\/crawl-tasks\/1$/)
    await expect(page.getByText('exec-fixture-1')).toBeVisible()
    await expect(page.getByText('阶段计数')).toBeVisible()
    await expect(page.getByText('Coze 调用记录')).toBeVisible()
    await expect(page.getByText('Coze 批量抓取结果')).toBeVisible()
  })
})
