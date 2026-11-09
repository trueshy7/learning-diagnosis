import { afterAll, afterEach, beforeAll } from 'vitest';
import { serialize, deserialize } from 'node:v8';
import { Blob as NodeBlob } from 'node:buffer';
import { server } from '../src/mocks/node';
import { memoryRepository, setRepository } from '../src/mocks/repository';
globalThis.structuredClone ||= <T>(value: T): T =>
  deserialize(serialize(value));
Object.defineProperty(globalThis, 'Blob', {
  value: NodeBlob,
  configurable: true,
});
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  setRepository(memoryRepository());
  sessionStorage.clear();
});
afterAll(() => server.close());
