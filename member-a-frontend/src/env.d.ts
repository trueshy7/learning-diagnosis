/// <reference types="vite/client" />
interface Window {
  __LEARNMATE_DEMO__?: {
    setScenario(s: string): Promise<void>;
    reset(): Promise<void>;
    setDelay(ms: number): Promise<void>;
  };
}
