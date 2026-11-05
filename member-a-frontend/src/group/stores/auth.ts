import { defineStore } from 'pinia';
import { api } from '../services/api';
import { getSession, saveSession } from '../services/session';
export const useAuthStore = defineStore('group-auth', {
  state: () => ({ session: getSession() }),
  getters: { user: (state) => state.session?.user ?? null },
  actions: {
    async login(username: string, password: string) {
      saveSession(null);
      this.session = null;
      const result = await api.login(username, password);
      saveSession(result);
      this.session = result;
    },
    sync() {
      this.session = getSession();
    },
    async logout() {
      try {
        await api.logout();
      } finally {
        saveSession(null);
        this.session = null;
      }
    },
  },
});
