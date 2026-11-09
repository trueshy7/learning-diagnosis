import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import { unlinkSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), '');
  if (!['mock', 'real'].includes(env.VITE_API_MODE))
    throw new Error('VITE_API_MODE 必须为 mock 或 real');
  if (
    env.VITE_SHOW_DEV_TOOLS &&
    !['true', 'false'].includes(env.VITE_SHOW_DEV_TOOLS)
  )
    throw new Error('VITE_SHOW_DEV_TOOLS 必须为 true 或 false');
  if (env.VITE_API_MODE === 'real' && env.VITE_SHOW_DEV_TOOLS === 'true')
    throw new Error('真实模式禁止启用开发控制');
  if (command === 'build' && env.VITE_SHOW_DEV_TOOLS === 'true')
    throw new Error('对外构建禁止携带开发控制，请使用 mock 或 real 模式构建');
  if (env.VITE_BACKEND_CONTRACT === 'group-v0' && env.VITE_API_MODE !== 'real')
    throw new Error('组协议入口必须使用真实API模式');
  const outDir =
    env.VITE_BACKEND_CONTRACT === 'group-v0'
      ? 'dist/group'
      : env.VITE_API_MODE === 'mock'
        ? 'dist/mock'
        : 'dist/real';
  return {
    plugins: [
      vue(),
      {
        name: 'isolate-real-artifacts',
        closeBundle() {
          const worker = resolve(outDir, 'mockServiceWorker.js');
          if (env.VITE_API_MODE === 'real' && existsSync(worker))
            unlinkSync(worker);
        },
      },
    ],
    build: { outDir, chunkSizeWarningLimit: 1800 },
    preview: {
      proxy:
        env.VITE_API_MODE === 'real'
          ? { '/api': { target: env.BACKEND_PROXY_TARGET, changeOrigin: true } }
          : undefined,
    },
    server: {
      proxy:
        env.VITE_API_MODE === 'real'
          ? { '/api': { target: env.BACKEND_PROXY_TARGET, changeOrigin: true } }
          : undefined,
    },
  };
});
