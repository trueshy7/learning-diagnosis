import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import './style.css';

async function start() {
  // Remove only this application's old mock worker before real API requests.
  const worker = new URL(
    `${import.meta.env.BASE_URL}mockServiceWorker.js`,
    location.origin,
  ).href;
  if ('serviceWorker' in navigator) {
    for (const registration of await navigator.serviceWorker.getRegistrations()) {
      if (
        (registration.active?.scriptURL || registration.waiting?.scriptURL) ===
        worker
      )
        await registration.unregister();
    }
    if (navigator.serviceWorker.controller?.scriptURL === worker) {
      if (!sessionStorage.getItem('group-worker-reload')) {
        sessionStorage.setItem('group-worker-reload', '1');
        location.reload();
        return;
      }
      throw new Error('旧模拟服务仍控制页面');
    }
    sessionStorage.removeItem('group-worker-reload');
  }
  const app = createApp(App);
  app.use(createPinia()).use(router);
  window.addEventListener('group-session-expired', () => {
    void router.replace('/login');
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) location.reload();
  });
  await router.isReady();
  app.mount('#app');
}
await start();
