import { onScopeDispose, shallowRef, ref, watch } from 'vue';
import type { Task } from '../api/contracts';
import { api } from '../api/services';
import { config } from '../config';
export class TaskPoller {
  private seq = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private deadline: ReturnType<typeof setTimeout> | undefined;
  private controller: AbortController | undefined;
  constructor(
    private load: (id: string, signal: AbortSignal) => Promise<Task>,
    private emit: (t: Task) => void,
    private finish: (reason: string, error?: Error) => void,
    private options = {
      interval: config.pollInterval,
      max: config.pollMax,
      duration: config.pollDuration,
    },
  ) {}
  stop() {
    this.seq++;
    clearTimeout(this.timer);
    clearTimeout(this.deadline);
    this.controller?.abort();
  }
  start(id: string) {
    this.stop();
    const seq = this.seq,
      started = Date.now();
    let count = 0;
    this.deadline = setTimeout(() => {
      if (seq === this.seq) {
        this.stop();
        this.finish('limit');
      }
    }, this.options.duration);
    const step = async () => {
      if (seq !== this.seq) return;
      if (
        count >= this.options.max ||
        Date.now() - started >= this.options.duration
      ) {
        this.stop();
        this.finish('limit');
        return;
      }
      this.controller = new AbortController();
      count++;
      try {
        const t = await this.load(id, this.controller.signal);
        if (seq !== this.seq) return;
        this.emit(t);
        if (t.status === 'completed' || t.status === 'failed') {
          clearTimeout(this.deadline);
          this.finish(t.status);
          return;
        }
        this.timer = setTimeout(step, this.options.interval);
      } catch (e) {
        if (seq === this.seq) {
          clearTimeout(this.deadline);
          this.finish('error', e instanceof Error ? e : new Error(String(e)));
        }
      }
    };
    void step();
  }
}
export function useTaskPolling(
  id: () => string | null,
  completed?: (t: Task) => void | Promise<void>,
) {
  const task = shallowRef<Task | null>(null),
    error = shallowRef<Error | null>(null),
    reason = ref('idle');
  const poller = new TaskPoller(
    api.task,
    (t) => {
      task.value = t;
      if (t.status === 'completed') void completed?.(t);
    },
    (r, e) => {
      reason.value = r;
      error.value = e || null;
    },
  );
  function restart() {
    error.value = null;
    reason.value = 'polling';
    const value = id();
    if (value) poller.start(value);
  }
  watch(
    id,
    () => {
      poller.stop();
      task.value = null;
      if (id()) restart();
    },
    { immediate: true },
  );
  onScopeDispose(() => poller.stop());
  return { task, error, reason, restart, stop: () => poller.stop() };
}
