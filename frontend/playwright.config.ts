import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'

const externalBaseUrl = process.env.E2E_BASE_URL
const baseURL = externalBaseUrl ?? 'http://127.0.0.1:5173'
const systemChromeAvailable =
  process.platform === 'win32' &&
  existsSync('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')

/**
 * The default suite uses deterministic API fixtures, so it can run without
 * PostgreSQL, Redis, Qdrant, or a model provider. Set E2E_BASE_URL to point at
 * a deployed frontend for a smoke run against a real stack.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    testIdAttribute: 'data-testid',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: systemChromeAvailable ? 'chrome' : undefined,
      },
    },
  ],
  webServer: externalBaseUrl
    ? undefined
    : {
        command: 'npm run dev -- --host 127.0.0.1 --port 5173',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: 'ignore',
        stderr: 'pipe',
      },
})
