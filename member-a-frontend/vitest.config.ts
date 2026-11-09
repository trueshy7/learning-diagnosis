import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.ts', 'tests/components/**/*.test.ts'],
    setupFiles: ['tests/setup.ts'],
    restoreMocks: true,
    env: {
      VITE_API_MODE: 'mock',
      VITE_API_BASE_URL: 'http://localhost/api/v1',
    },
  },
});
