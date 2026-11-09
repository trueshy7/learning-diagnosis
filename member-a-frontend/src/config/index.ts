function positive(value: string | undefined, fallback: number) {
  const n = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(n) || n <= 0) throw new Error('时间/次数配置必须是正数');
  return n;
}
export const config = {
  mode: import.meta.env.VITE_API_MODE,
  debug:
    import.meta.env.VITE_API_MODE === 'mock' &&
    import.meta.env.VITE_SHOW_DEV_TOOLS === 'true',
  apiBase: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timezone: import.meta.env.VITE_APP_TIME_ZONE || 'Asia/Shanghai',
  pollInterval: positive(import.meta.env.VITE_POLL_INTERVAL_MS, 1500),
  pollMax: positive(import.meta.env.VITE_POLL_MAX_ATTEMPTS, 40),
  pollDuration: positive(import.meta.env.VITE_POLL_MAX_DURATION_MS, 60000),
  mockTaskMs: positive(import.meta.env.VITE_MOCK_TASK_MS, 3000),
  uploadLimit: 10 * 1024 * 1024,
};
export const statusLabels: Record<string, string> = {
  weak: '薄弱',
  consolidating: '待巩固',
  mastered: '已掌握',
  insufficient_evidence: '证据不足',
  queued: '等待处理',
  running: '处理中',
  completed: '已完成',
  failed: '处理失败',
  initial: '前测',
  practice: '练习',
  retest: '复测',
  in_progress: '作答中',
  submitted: '已提交',
  easy: '基础',
  medium: '中等',
  hard: '较难',
  note: '文本资料',
  document: '上传文档',
  external: '外部链接',
  available: '可用',
  processing: '处理中',
  removed: '已停用',
  unknown: '状态待确认',
};
