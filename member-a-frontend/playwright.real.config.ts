import { defineConfig } from '@playwright/test';
export default defineConfig({
  outputDir: 'test-results/real',
  testDir: './tests/e2e-real',
  timeout: 30000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    browserName: 'chromium',
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js preview --mode real --outDir dist/real --host 127.0.0.1 --port 4173 --strictPort`,
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
  },
});
