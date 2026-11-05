import { loginSchema } from './contracts';
import type { LoginResult } from '../types/api';
const SESSION_KEY = 'learnmate-group-session-v1';
export let sessionVersion = 0;
export function getSession(): LoginResult | null {
  try {
    const result = loginSchema.safeParse(
      JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null'),
    );
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}
export function saveSession(value: LoginResult | null) {
  sessionVersion++;
  Object.keys(sessionStorage)
    .filter((key) => key.startsWith('learnmate-group-draft:'))
    .forEach((key) => sessionStorage.removeItem(key));
  if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
  else sessionStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new Event('group-session-changed'));
}
