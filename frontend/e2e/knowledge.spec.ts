import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('来源与文档关键旅程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page)
  })

  test('可创建来源并在文档页检索已索引文档', async ({ page }) => {
    await loginAsAdmin(page, '/sources')
    await expect(page.getByRole('heading', { name: '来源' })).toBeVisible()

    await page.getByRole('button', { name: '新增来源' }).click()
    await page.getByLabel('来源键').fill('e2e-source')
    await page.getByLabel('名称', { exact: true }).fill('E2E 官方来源')
    await page.getByLabel('域名').fill('e2e.example.gov.cn')
    await page.getByLabel('主页 URL').fill('https://e2e.example.gov.cn')
    await page.getByLabel('栏目 URL').fill('https://e2e.example.gov.cn/policies')
    await page.getByRole('button', { name: '保存', exact: true }).click()

    await expect(page.getByText('E2E 官方来源')).toBeVisible()
    await page.locator('a[href="/documents"]').click()
    await expect(page).toHaveURL(/\/documents$/)
    await expect(page.getByRole('heading', { name: '文档' })).toBeVisible()
    await expect(page.getByText('企业研发投入支持措施')).toBeVisible()
    await expect(page.getByRole('table').getByText('已索引', { exact: true })).toBeVisible()
  })
})
