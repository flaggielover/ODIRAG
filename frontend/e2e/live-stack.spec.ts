import { expect, test } from '@playwright/test'

const liveEnabled = process.env.E2E_LIVE === '1'

function requiredEnvironment(name: 'E2E_BASE_URL' | 'E2E_USERNAME' | 'E2E_PASSWORD'): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required when E2E_LIVE=1`)
  return value
}

test.describe('真实栈生产验收（live-stack）', () => {
  test.skip(!liveEnabled, 'Set E2E_LIVE=1 with an external base URL and credentials to run live integration checks.')

  test('登录后可达核心页面并完成带引用问答', async ({ page }) => {
    test.setTimeout(90_000)
    const username = requiredEnvironment('E2E_USERNAME')
    const password = requiredEnvironment('E2E_PASSWORD')
    requiredEnvironment('E2E_BASE_URL')

    await page.goto('/login')
    await page.locator('#username').fill(username)
    await page.locator('#password').fill(password)
    await page.locator('.login-submit').click()
    await expect(page).not.toHaveURL(/\/login(?:\?|$)/)
    await expect(page.locator('.user-chip')).toContainText(username)
    await expect(page.getByRole('heading', { name: '仪表盘', exact: true })).toBeVisible()

    await page.goto('/sources')
    await expect(page.getByRole('heading', { name: '来源', exact: true })).toBeVisible()
    await expect(page.locator('.state-panel, .table-frame').first()).toBeVisible()

    await page.goto('/documents')
    await expect(page.getByRole('heading', { name: '文档', exact: true })).toBeVisible()
    await expect(page.locator('.state-panel, .table-frame').first()).toBeVisible()

    await page.goto('/chat')
    const query =
      process.env.E2E_QUERY ??
      '存量APP备案阶段是什么时间？已完成网站备案手续的APP是否需要重复填报主办者真实身份信息？'
    await page.locator('textarea[placeholder="输入查询"]').fill(query)
    await page.getByRole('button', { name: '发送' }).click()
    await expect(page.locator('.evidence-card').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.trace-inspector').getByText(/Trace ID/)).toBeVisible()

    await page.goto('/monitoring')
    await expect(page.getByRole('heading', { name: '监控与告警', exact: true })).toBeVisible()
    await expect(page.getByText('DB P95', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '依赖健康', exact: true })).toBeVisible()
  })
})
