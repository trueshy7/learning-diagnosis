import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';
import { getRepository, indexedRepository, setRepository } from './repository';
export const scenarios = [
  'normal',
  'weak-profile',
  'balanced-profile',
  'insufficient-coverage',
  'empty-history',
  'empty-recommendations',
  'retrieval-empty',
  'model-fallback',
  'diagnosis-failed',
  'diagnosis-stuck',
  'session-expired',
  'forbidden',
  'submit-committed-response-lost',
  'resource-removed',
  'upload-failed',
  'invalid-response',
  'long-content',
];
export const worker = setupWorker(...handlers);
export async function startMock() {
  setRepository(await indexedRepository());
  if (import.meta.env.VITE_SHOW_DEV_TOOLS !== 'true') {
    await getRepository().change((s) => {
      s.scenario = 'normal';
      s.delayMs = 0;
    });
  }
  await worker.start({
    quiet: true,
    onUnhandledRequest(request, print) {
      if (new URL(request.url).pathname.startsWith('/api/v1')) print.error();
    },
  });
  if (import.meta.env.VITE_SHOW_DEV_TOOLS === 'true')
    window.__LEARNMATE_DEMO__ = {
      async setScenario(scenario: string) {
        if (!scenarios.includes(scenario)) throw new Error('未知演示场景');
        await getRepository().change((s) => {
          s.scenario = scenario;
          if (scenario === 'session-expired')
            Object.values(s.tokens).forEach((t) => (t.expires = 0));
        });
      },
      async reset() {
        await getRepository().reset();
      },
      async setDelay(delayMs: number) {
        await getRepository().change((s) => {
          s.delayMs = Math.max(0, Math.min(15000, delayMs));
        });
      },
    };
}
