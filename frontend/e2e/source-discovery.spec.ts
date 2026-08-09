import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('来源发现审批关键旅程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page)
  })

  test('可创建内容缺口发现运行', async ({ page }) => {
    await loginAsAdmin(page, '/source-discovery')
    const createRequest = page.waitForRequest(
      (request) => request.url().endsWith('/api/source-discovery/runs') && request.method() === 'POST',
    )

    await page.getByRole('button', { name: '新建发现' }).click()
    await page.getByLabel('内容主题').fill('绿色制造政策')
    await page.getByLabel('地区').fill('江苏')
    await page.getByLabel('目标来源数').fill('2')
    await page.getByLabel('目标文档数').fill('8')
    await page.getByRole('button', { name: '创建运行' }).click()

    const request = await createRequest
    expect(request.postDataJSON()).toMatchObject({
      topic: '绿色制造政策',
      region: '江苏',
      required_source_count: 2,
      required_document_count: 8,
      execution_mode: 'queued',
    })
    await expect(page.getByText('绿色制造政策')).toBeVisible()
    await expect(page.locator('.discovery-runs-table').getByText('待处理')).toBeVisible()
  })

  test('人工批准后才能激活，另一候选可带原因拒绝', async ({ page }) => {
    await loginAsAdmin(page, '/source-discovery')
    const approvedRow = page.getByRole('row').filter({ hasText: '示例创新政策来源' })
    const rejectedRow = page.getByRole('row').filter({ hasText: '示例待复核来源' })

    await expect(page.getByText('待审批', { exact: true }).first()).toBeVisible()
    await approvedRow.getByRole('button', { name: '示例创新政策来源' }).click()
    await expect(page.getByText('官方验证证据', { exact: true })).toBeVisible()
    await expect(page.locator('.json-panel').filter({ hasText: 'gov.cn' })).toBeVisible()
    await approvedRow.getByRole('button', { name: '批准候选' }).click()
    await expect(approvedRow.getByText('已批准', { exact: true })).toBeVisible()
    await approvedRow.getByRole('button', { name: '激活来源' }).click()
    await expect(approvedRow.getByText('已激活', { exact: true })).toBeVisible()

    await rejectedRow.getByRole('button', { name: '拒绝候选' }).click()
    await page.getByLabel('拒绝原因').fill('栏目内容与目标主题相关性不足')
    await page
      .getByRole('dialog', { name: '拒绝候选来源' })
      .getByRole('button', { name: '拒绝候选', exact: true })
      .click()
    await expect(rejectedRow.getByText('已拒绝', { exact: true })).toBeVisible()
    await rejectedRow.getByRole('button', { name: '示例待复核来源' }).click()
    await expect(page.getByText('栏目内容与目标主题相关性不足')).toBeVisible()
  })
})
