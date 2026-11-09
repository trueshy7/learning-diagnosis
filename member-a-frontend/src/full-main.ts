import { createApp } from 'vue';
import { createPinia } from 'pinia';
import ElementPlus from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/dist/index.css';
import './styles/main.css';
import App from './App.vue';
import { router } from './router';

// A document restored from the back-forward cache must revalidate its identity.
// Hide the frozen private DOM before the browser can paint an obsolete session.
window.addEventListener('pageshow', (event) => {
  if (event.persisted) {
    const root = document.getElementById('app');
    if (root) root.style.visibility = 'hidden';
    location.reload();
  }
});

async function main() {
  if (import.meta.env.VITE_API_MODE === 'mock') {
    const { startMock } = await import('./mocks/browser');
    await startMock();
  } else if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    for (const r of registrations) {
      const workerUrl =
        r.active?.scriptURL || r.waiting?.scriptURL || r.installing?.scriptURL;
      if (
        workerUrl ===
        new URL(
          `${import.meta.env.BASE_URL}mockServiceWorker.js`,
          location.origin,
        ).href
      )
        await r.unregister();
    }
    if (
      navigator.serviceWorker.controller?.scriptURL ===
      new URL(
        `${import.meta.env.BASE_URL}mockServiceWorker.js`,
        location.origin,
      ).href
    ) {
      if (!sessionStorage.getItem('learnmate-worker-reload')) {
        sessionStorage.setItem('learnmate-worker-reload', '1');
        location.reload();
        return;
      }
      throw new Error(
        '旧演示 worker 仍控制页面，请关闭本应用标签页后在真实模式端口重新打开',
      );
    }
    sessionStorage.removeItem('learnmate-worker-reload');
  }
  const app = createApp(App);
  app.use(createPinia());
  app.use(ElementPlus, { locale: zhCn });
  app.use(router);
  await router.isReady();
  app.mount('#app');
}
main().catch((error) => {
  const root = document.getElementById('app')!;
  root.textContent =
    import.meta.env.VITE_SHOW_DEV_TOOLS === 'true' &&
    import.meta.env.VITE_API_MODE === 'mock'
      ? `应用启动失败：${error instanceof Error ? error.message : String(error)}`
      : '应用暂时无法启动，请刷新重试或联系维护者。';
});
