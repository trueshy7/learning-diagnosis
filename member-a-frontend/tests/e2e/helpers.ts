import { test as base, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
export const test = base.extend<{ allowConsole: (pattern: RegExp) => void }>({
  allowConsole: [
    async ({ page }, use) => {
      const allowed: RegExp[] = [],
        errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));
      page.on('console', (m) => {
        if (m.type() === 'error' && !allowed.some((p) => p.test(m.text())))
          errors.push(m.text());
      });
      await use((p) => allowed.push(p));
      expect(errors, '未预期的浏览器错误').toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };
export async function login(page: Page, who = 'student_a') {
  await page.goto('/login');
  await page
    .getByLabel('账号', { exact: true })
    .fill(`demo_${who === 'teacher' ? 'teacher' : who}`);
  await page.getByLabel('密码', { exact: true }).fill('Demo123!');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(
    who === 'teacher' ? /\/teacher\/overview$/ : /\/courses$/,
  );
}
export async function scenario(page: Page, name: string) {
  await page.evaluate(async (s) => {
    await window.__LEARNMATE_DEMO__!.setScenario(s);
  }, name);
}
export async function call(
  page: Page,
  path: string,
  method = 'GET',
  data?: unknown,
  headers: Record<string, string> = {},
) {
  return page.evaluate(
    async (args) => {
      const r = await fetch(`/api/v1${args.path}`, {
        method: args.method,
        headers: {
          Authorization: `Bearer ${sessionStorage.getItem('learnmate-token')}`,
          ...(args.data ? { 'Content-Type': 'application/json' } : {}),
          ...args.headers,
        },
        ...(args.data ? { body: JSON.stringify(args.data) } : {}),
      });
      return { status: r.status, body: await r.json() };
    },
    { path, method, data, headers },
  );
}
export async function submit(page: Page) {
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('未答');
  await page.getByRole('button', { name: '确认提交', exact: true }).click();
  await expect(page).toHaveURL(/\/diagnosis$/);
}
export async function shot(page: Page, name: string) {
  await expect(page.locator('.demo-badge')).toBeVisible();
  if (name === 'login')
    await expect(page.getByLabel('账号', { exact: true })).toBeVisible();
  else if (name === 'course')
    await expect(page.locator('.course-hero')).toBeVisible();
  else if (name.startsWith('quiz'))
    await expect(page.locator('.question-card')).toBeVisible();
  else if (name === 'teacher-questions')
    await expect(page.locator('table tbody tr').first()).toBeVisible();
  else await expect(page.locator('main h1').first()).toBeVisible();
  const dir = resolve('docs/testing/frontend/screenshots');
  await page.evaluate(() => window.scrollTo(0, 0));
  await mkdir(dir, { recursive: true });
  await page.screenshot({
    path: resolve(
      dir,
      `${name}-${page.viewportSize()!.width}x${page.viewportSize()!.height}.png`,
    ),
    fullPage: true,
  });
}
