import { defineConfig } from '@playwright/test';
export default defineConfig({
  outputDir: 'test-results/mock',
  testDir: './tests/e2e',
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5180',
    browserName: 'chromium',
    viewport: { width: 1366, height: 768 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'zh-CN',
  },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --mode e2e --host 127.0.0.1 --port 5180 --strictPort`,
    url: 'http://127.0.0.1:5180',
    reuseExistingServer: false,
    timeout: 60000,
  },
});
