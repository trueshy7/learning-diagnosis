import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { User } from '../api/contracts';
import { api } from '../api/services';
import { ApiError, clearPrivateSession, generation } from '../api/client';
export const useAuth = defineStore('auth', () => {
  const user = ref<User | null>(null);
  const initialized = ref(false);
  let pending: Promise<void> | null = null;
  function clear() {
    clearPrivateSession();
    user.value = null;
    initialized.value = true;
    pending = null;
  }
  async function bootstrap() {
    if (initialized.value) return;
    if (pending) return pending;
    const epoch = generation;
    pending = (async () => {
      try {
        if (sessionStorage.getItem('learnmate-token')) {
          const me = await api.me();
          if (epoch === generation) user.value = me;
        }
      } catch (error) {
        if (error instanceof ApiError && error.httpStatus === 401) clear();
        else if (!(
          error instanceof ApiError && error.code === 'REQUEST_CANCELLED'
        ))
          throw error;
      } finally {
        if (epoch === generation) initialized.value = true;
        pending = null;
      }
    })();
    return pending;
  }
  async function login(username: string, password: string) {
    clear();
    const result = await api.login(username, password);
    sessionStorage.setItem('learnmate-token', result.access_token);
    const me = await api.me();
    user.value = me;
    initialized.value = true;
    sessionStorage.removeItem('learnmate-expired');
  }
  async function logout() {
    try {
      await api.logout();
    } finally {
      clear();
    }
  }
  return { user, initialized, bootstrap, login, logout, clear };
});
