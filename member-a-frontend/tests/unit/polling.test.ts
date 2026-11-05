import { afterEach, it, expect, vi } from 'vitest';
import { TaskPoller } from '../../src/composables/useTaskPolling';
import { createSeed } from '../../src/mocks/repository';
const task = () => ({
  ...createSeed().tasks['task-a-001'],
  status: 'running' as const,
  report_id: null,
});
afterEach(() => vi.useRealTimers());
it.each(['completed', 'failed'] as const)('轮询遇 %s 停止', async (status) => {
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValue({
    ...task(),
    status,
    report_id: status === 'completed' ? 'report-a-001' : null,
  });
  const emit = vi.fn(),
    finish = vi.fn();
  const p = new TaskPoller(load, emit, finish, {
    interval: 10,
    max: 3,
    duration: 100,
  });
  p.start('a');
  await vi.runAllTimersAsync();
  expect(load).toHaveBeenCalledTimes(1);
  expect(finish).toHaveBeenCalledWith(status);
  p.stop();
});
it('到达次数上限，手动刷新重启单条链', async () => {
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValue(task()),
    finish = vi.fn();
  const p = new TaskPoller(load, vi.fn(), finish, {
    interval: 10,
    max: 3,
    duration: 100,
  });
  p.start('a');
  await vi.runAllTimersAsync();
  expect(load).toHaveBeenCalledTimes(3);
  expect(finish).toHaveBeenCalledWith('limit');
  p.start('a');
  p.start('a');
  await vi.runAllTimersAsync();
  expect(load.mock.calls.length).toBeLessThanOrEqual(7);
  p.stop();
});
it('到达时间上限但不伪造失败', async () => {
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValue(task()),
    finish = vi.fn();
  const p = new TaskPoller(load, vi.fn(), finish, {
    interval: 30,
    max: 100,
    duration: 50,
  });
  p.start('a');
  await vi.runAllTimersAsync();
  expect(load).toHaveBeenCalledTimes(2);
  expect(finish).toHaveBeenCalledWith('limit');
  p.stop();
});
it('慢请求不重叠，stop 取消在途请求并丢弃旧 task 响应', async () => {
  vi.useFakeTimers();
  let resolve!: (value: unknown) => void;
  const load = vi.fn(
    (_id: string, _signal: AbortSignal) =>
      new Promise<ReturnType<typeof task>>((r) => {
        resolve = r as typeof resolve;
      }),
  );
  const emit = vi.fn();
  const p = new TaskPoller(load, emit, vi.fn(), {
    interval: 10,
    max: 4,
    duration: 1000,
  });
  p.start('old');
  await vi.advanceTimersByTimeAsync(200);
  expect(load).toHaveBeenCalledTimes(1);
  const signal = load.mock.calls[0][1];
  p.stop();
  expect(signal.aborted).toBe(true);
  resolve(task());
  await vi.advanceTimersByTimeAsync(100);
  expect(emit).not.toHaveBeenCalled();
});
it('网络错误停止自动查询', async () => {
  vi.useFakeTimers();
  const load = vi.fn().mockRejectedValue(new Error('offline')),
    finish = vi.fn();
  const p = new TaskPoller(load, vi.fn(), finish, {
    interval: 10,
    max: 3,
    duration: 100,
  });
  p.start('x');
  await vi.runAllTimersAsync();
  expect(load).toHaveBeenCalledTimes(1);
  expect(finish).toHaveBeenCalledWith('error', expect.any(Error));
  p.stop();
});
it('总等待时限取消尚未返回的请求', async () => {
  vi.useFakeTimers();
  const load = vi.fn(
    (_id: string, _signal: AbortSignal) =>
      new Promise<ReturnType<typeof task>>(() => undefined),
  );
  const finish = vi.fn();
  const p = new TaskPoller(load, vi.fn(), finish, {
    interval: 10,
    max: 10,
    duration: 50,
  });
  p.start('slow');
  await vi.advanceTimersByTimeAsync(50);
  expect(load.mock.calls[0][1].aborted).toBe(true);
  expect(finish).toHaveBeenCalledWith('limit');
});
