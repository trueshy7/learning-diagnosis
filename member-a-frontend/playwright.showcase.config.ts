import { defineConfig } from '@playwright/test';
export default defineConfig({
  outputDir: 'test-results/showcase',
  testDir: './tests/e2e-showcase',
  timeout: 40000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5182',
    browserName: 'chromium',
    viewport: { width: 1366, height: 768 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --mode mock --host 127.0.0.1 --port 5182 --strictPort`,
    url: 'http://127.0.0.1:5182',
    reuseExistingServer: false,
  },
});
