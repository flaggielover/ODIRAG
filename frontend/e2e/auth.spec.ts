import { expect, test } from '@playwright/test'

import { installApiFixtures, loginAsAdmin } from './fixtures'

test.describe('认证关键旅程（fixture-backed）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page)
  })

  test('管理员可以登录并完成服务端注销', async ({ page }) => {
    await loginAsAdmin(page)
    await expect(page.locator('.user-chip')).toContainText('admin')

    await page.getByRole('button', { name: /退出登录/ }).click()
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.locator('#login-title')).toBeVisible()
    await expect(page.evaluate(() => sessionStorage.getItem('odirag.session'))).resolves.toBeNull()
  })
})
