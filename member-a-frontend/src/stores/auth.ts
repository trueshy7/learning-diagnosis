import { defineStore } from 'pinia'
import { api } from '../services/api'
import { getSession, saveSession } from '../services/session'
export const useAuthStore = defineStore('auth', {
  state: () => ({ session: getSession() }),
  getters: { user: state => state.session?.user ?? null },
  actions: {
    async login(username: string, password: string) { this.session = await api.login(username, password); saveSession(this.session) },
    logout() { this.session = null; saveSession(null) },
  },
})
