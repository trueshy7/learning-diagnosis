import { onScopeDispose, ref, shallowRef, watch } from 'vue';
import { ApiError, generation } from '../api/client';
export function useLoad<T>(key: () => string, loader: () => Promise<T>) {
  const data = shallowRef<T | null>(null),
    error = shallowRef<Error | null>(null),
    loading = ref(false);
  let seq = 0;
  async function reload() {
    const n = ++seq,
      epoch = generation;
    data.value = null;
    error.value = null;
    loading.value = true;
    try {
      const value = await loader();
      if (seq === n && epoch === generation) data.value = value;
    } catch (e) {
      if (
        seq === n &&
        epoch === generation &&
        !(e instanceof ApiError && e.code === 'REQUEST_CANCELLED')
      )
        error.value = e instanceof Error ? e : new Error(String(e));
    } finally {
      if (seq === n) loading.value = false;
    }
  }
  watch(key, reload, { immediate: true });
  onScopeDispose(() => seq++);
  return { data, error, loading, reload };
}
