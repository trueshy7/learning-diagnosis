import type { LoginResult } from '../types/api'
const SESSION_KEY = 'learning-demo-session-v1'
export function getSession(): LoginResult | null {
  try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? 'null') as LoginResult | null }
  catch { sessionStorage.removeItem(SESSION_KEY); return null }
}
export function saveSession(value: LoginResult | null) {
  if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value))
  else sessionStorage.removeItem(SESSION_KEY)
}
