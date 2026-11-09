import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
const python =
  process.env.GROUP_PYTHON ||
  resolve(
    '../.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
  );
export default defineConfig({
  outputDir: 'test-results/group',
  testDir: './tests/e2e-group',
  timeout: 45000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5183',
    browserName: 'chromium',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `"${python}" scripts/test-group-services.py`,
      url: 'http://127.0.0.1:19280/health',
      reuseExistingServer: false,
      timeout: 60000,
    },
    {
      command: `"${process.execPath}" node_modules/vite/bin/vite.js --mode group --host 127.0.0.1 --port 5183 --strictPort`,
      url: 'http://127.0.0.1:5183',
      reuseExistingServer: false,
      env: { BACKEND_PROXY_TARGET: 'http://127.0.0.1:19280' },
    },
  ],
});
