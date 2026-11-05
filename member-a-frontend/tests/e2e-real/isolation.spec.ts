import { test, expect } from '@playwright/test';
test('真实构建无模拟入口；缺少后端时显示失败且不回落演示数据', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/login');
  expect(await page.evaluate(() => window.__LEARNMATE_DEMO__)).toBeUndefined();
  await expect(
    page.getByText('演示数据 / 模拟服务', { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByText('demo_student_a')).toHaveCount(0);
  await page.getByLabel('账号', { exact: true }).fill('unknown-account');
  await page.getByLabel('密码', { exact: true }).fill('wrong');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('.course-entry')).toHaveCount(0);
  expect(errors).toEqual([]);
});
test('真实适配器契约测试：配置地址、Bearer、me角色与解析；不代表B/C/D联调', async ({
  page,
}) => {
  const calls: { path: string; auth: string | undefined }[] = [];
  const user = {
    user_id: 'contract-user',
    username: 'contract-user',
    display_name: '契约测试用户',
    role: 'student',
  };
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    calls.push({ path, auth: req.headers().authorization });
    const data = path.endsWith('/auth/login')
      ? {
          access_token: 'contract-only-token',
          token_type: 'Bearer',
          expires_at: '2030-01-01T00:00:00Z',
          user,
        }
      : path.endsWith('/auth/me')
        ? user
        : [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'OK',
        message: '',
        data,
        request_id: 'contract-test',
      }),
    });
  });
  await page.goto('/login');
  await page.getByLabel('账号', { exact: true }).fill('contract-user');
  await page.getByLabel('密码', { exact: true }).fill('contract-test-only');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/courses$/);
  await expect(page.getByText('暂无课程', { exact: true })).toBeVisible();
  expect(calls.find((c) => c.path === '/api/v1/auth/me')?.auth).toBe(
    'Bearer contract-only-token',
  );
  expect(calls.some((c) => c.path === '/api/v1/courses')).toBe(true);
  expect(
    await page.evaluate(() => navigator.serviceWorker.controller),
  ).toBeNull();
});
